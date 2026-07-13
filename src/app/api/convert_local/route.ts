import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, readFile, unlink, stat } from "fs/promises";
import path from "path";
import os from "os";
import { Client } from "pg";

export const maxDuration = 120;

async function getPythonCommand(): Promise<string> {
  const candidates = [
    "/Users/wesleywu/.pyenv/shims/python3",
    "/Users/wesleywu/.pyenv/shims/python",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
  ];
  for (const pathStr of candidates) {
    try {
      await stat(pathStr);
      return pathStr;
    } catch {}
  }
  return process.platform === "win32" ? "python" : "python3";
}

async function runPython(cwd: string, args: string[]): Promise<void> {
  const pythonCmd = await getPythonCommand();
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonCmd, args, {
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

export async function POST(req: NextRequest) {
  const contentType = req.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    const body = await req.json();
    const { extractedData } = body;
    if (!extractedData) {
      return NextResponse.json(
        { error: "No extractedData provided" },
        { status: 400 },
      );
    }
    const id = `mirror_edit_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const jsonPath = path.join(os.tmpdir(), `${id}.json`);
    const xlsxPath = path.join(os.tmpdir(), `${id}.xlsx`);
    try {
      await writeFile(
        jsonPath,
        JSON.stringify(extractedData, null, 2),
        "utf-8",
      );
      await runPython(process.cwd(), [
        "pipeline/XLSXgen.py",
        jsonPath,
        xlsxPath,
      ]);
      const xlsxData = await readFile(xlsxPath);
      const base64xlsx = xlsxData.toString("base64");
      return NextResponse.json({ xlsx: base64xlsx }, { status: 200 });
    } catch (err) {
      return NextResponse.json(
        { error: err instanceof Error ? err.message : "Regeneration failed" },
        { status: 500 },
      );
    } finally {
      unlink(jsonPath).catch(() => {});
      unlink(xlsxPath).catch(() => {});
    }
  }

  const formData = await req.formData();
  const files = formData.getAll("file") as File[];

  if (files.length === 0) {
    return NextResponse.json({ error: "No files provided" }, { status: 400 });
  }

  const id = `mirror_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const tempFiles: string[] = [];
  const jsonPath = path.join(os.tmpdir(), `${id}.json`);

  try {
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const filePath = path.join(os.tmpdir(), `${id}_${i}_${file.name}`);
      await writeFile(filePath, Buffer.from(await file.arrayBuffer()));
      tempFiles.push(filePath);
    }

    await runPython(process.cwd(), [
      "pipeline/JSONgen.py",
      ...tempFiles,
      jsonPath,
    ]);

    const jsonContent = await readFile(jsonPath, "utf-8");
    const extractedData = JSON.parse(jsonContent);

    const pagesList = extractedData.pages || [];
    const pageData = pagesList[0];
    if (!pageData) {
      return NextResponse.json(
        { error: "No page data extracted" },
        { status: 500 },
      );
    }

    const client = new Client({
      connectionString: process.env.DATABASE_URL,
    });
    await client.connect();
    const dbRes = await client.query(
      "INSERT INTO parsed_documents (filename, template_schema, extracted_data, code) VALUES ($1, $2, $3, $4) RETURNING id",
      [
        pageData.filename || "document",
        JSON.stringify(pageData.template || {}),
        JSON.stringify(pageData.data || []),
        pageData.code || "",
      ],
    );
    await client.end();

    const docId = dbRes.rows[0].id;

    return NextResponse.json(
      {
        id: docId,
        html: pageData.html,
      },
      { status: 200 },
    );
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Conversion failed" },
      { status: 500 },
    );
  } finally {
    unlink(jsonPath).catch(() => {});
    for (const p of tempFiles) {
      unlink(p).catch(() => {});
    }
  }
}
