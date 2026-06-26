import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, readFile, unlink } from "fs/promises";
import path from "path";
import os from "os";

export const maxDuration = 120;

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const file = formData.get("file") as File | null;

  if (!file) {
    return NextResponse.json({ error: "No file provided" }, { status: 400 });
  }

  const id = `mirror_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const ext = path.extname(file.name) || ".jpg";
  const imagePath = path.join(os.tmpdir(), `${id}${ext}`);
  const jsonPath = path.join(os.tmpdir(), `${id}.json`);
  const xlsxPath = path.join(os.tmpdir(), `${id}.xlsx`);

  try {
    await writeFile(imagePath, Buffer.from(await file.arrayBuffer()));

    await runPython(process.cwd(), [
      "pipeline/JSONgen.py",
      imagePath,
      jsonPath,
    ]);
    await runPython(process.cwd(), ["pipeline/XLSXgen.py", jsonPath, xlsxPath]);

    // Read raw response if it exists (written by JSONgen on JSON parse errors)
    const rawPath = `${imagePath}.raw_response.txt`;
    const xlsxData = await readFile(xlsxPath).catch(async () => {
      const raw = await readFile(rawPath, "utf-8").catch(() => "");
      unlink(rawPath).catch(() => {});
      throw new Error(
        `XLSX not produced. Raw Claude response:\n${raw.slice(0, 2000)}`,
      );
    });
    const outName = `${path.basename(file.name, ext)}.xlsx`;

    return new NextResponse(xlsxData, {
      status: 200,
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": `attachment; filename="${outName}"`,
      },
    });
  } catch (err) {
    console.error("Conversion error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Conversion failed" },
      { status: 500 },
    );
  } finally {
    for (const p of [imagePath, jsonPath, xlsxPath]) {
      unlink(p).catch(() => {});
    }
  }
}

function runPython(cwd: string, args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const proc = spawn("python", args, { cwd, env: { ...process.env } });
    const stderr: string[] = [];
    proc.stderr.on("data", (d: Buffer) => stderr.push(d.toString()));
    proc.on("close", (code: number) => {
      if (code === 0) resolve();
      else
        reject(new Error(stderr.join("") || `Python exited with code ${code}`));
    });
  });
}
