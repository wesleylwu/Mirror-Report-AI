import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, readFile, unlink, readdir } from "fs/promises";
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

    const jsonContent = await readFile(jsonPath, "utf-8");
    const extractedData = JSON.parse(jsonContent);

    const templatesDir = path.join(process.cwd(), "pipeline", "templates");
    const templateFiles = await readdir(templatesDir);
    let matchedTemplate: any = null;
    const templates: any[] = [];

    for (const f of templateFiles) {
      if (f.endsWith(".json")) {
        const fileContent = await readFile(path.join(templatesDir, f), "utf-8");
        templates.push(JSON.parse(fileContent));
      }
    }

    const title = (extractedData.title || "").trim();
    const section = (extractedData.section_header || "").trim();

    for (const tmpl of templates) {
      const m = tmpl.match || {};
      if (
        (m.title || "").trim() === title &&
        (m.section_header || "").trim() === section
      ) {
        matchedTemplate = tmpl;
        break;
      }
    }

    if (!matchedTemplate) {
      for (const tmpl of templates) {
        const m = tmpl.match || {};
        if ((m.title || "").trim() === title) {
          matchedTemplate = tmpl;
          break;
        }
      }
    }

    if (!matchedTemplate && templates.length > 0) {
      matchedTemplate = templates[0];
    }

    const rawPath = `${imagePath}.raw_response.txt`;
    const xlsxData = await readFile(xlsxPath).catch(async () => {
      const raw = await readFile(rawPath, "utf-8").catch(() => "");
      unlink(rawPath).catch(() => {});
      throw new Error(
        `XLSX not produced. Raw Claude response:\n${raw.slice(0, 2000)}`,
      );
    });
    const outName = `${path.basename(file.name, ext)}.xlsx`;

    const base64xlsx = xlsxData.toString("base64");

    return NextResponse.json(
      {
        extractedData,
        template: matchedTemplate,
        xlsx: base64xlsx,
        filename: outName,
      },
      { status: 200 },
    );
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
    const proc = spawn("python", args, {
      cwd,
      env: { ...process.env, ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY },
    });
    const stderr: string[] = [];
    proc.stderr.on("data", (d: Buffer) => stderr.push(d.toString()));
    proc.on("close", (code: number) => {
      if (code === 0) resolve();
      else
        reject(new Error(stderr.join("") || `Python exited with code ${code}`));
    });
  });
}
