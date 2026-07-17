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
  try {
    const body = await req.json();
    const { id, extractedData } = body;
    if (!id) {
      return NextResponse.json({ error: "Missing ID" }, { status: 400 });
    }

    const client = new Client({
      connectionString: process.env.DATABASE_URL,
    });
    await client.connect();

    if (extractedData) {
      const selectRes = await client.query(
        "SELECT extracted_data FROM parsed_documents WHERE id = $1",
        [id],
      );
      if (selectRes.rows.length > 0) {
        const currentData = selectRes.rows[0].extracted_data || [];
        const edits = extractedData.data || [];
        const mergedMap = new Map();
        for (const item of currentData) {
          const r = item.r !== undefined ? item.r : item.row;
          const c = item.c !== undefined ? item.c : item.col;
          const v = item.v !== undefined ? item.v : item.value;
          mergedMap.set(`${r}_${c}`, { r, c, v });
        }
        for (const item of edits) {
          const r = item.r !== undefined ? item.r : item.row;
          const c = item.c !== undefined ? item.c : item.col;
          const v = item.v !== undefined ? item.v : item.value;
          mergedMap.set(`${r}_${c}`, { r, c, v });
        }
        const mergedData = Array.from(mergedMap.values());
        await client.query(
          "UPDATE parsed_documents SET extracted_data = $1 WHERE id = $2",
          [JSON.stringify(mergedData), id],
        );
      }
    }

    const dbRes = await client.query(
      "SELECT template_schema, extracted_data, code FROM parsed_documents WHERE id = $1",
      [id],
    );
    await client.end();

    if (dbRes.rows.length === 0) {
      return NextResponse.json(
        { error: "Document not found" },
        { status: 404 },
      );
    }

    const row = dbRes.rows[0];
    const payload = {
      pages: [
        {
          template: row.template_schema,
          data: row.extracted_data,
          code: row.code,
        },
      ],
    };

    const tempId = `db_${id}_${Date.now()}`;
    const jsonPath = path.join(os.tmpdir(), `${tempId}.json`);
    const xlsxPath = path.join(os.tmpdir(), `${tempId}.xlsx`);

    await writeFile(jsonPath, JSON.stringify(payload), "utf-8");
    await runPython(process.cwd(), ["pipeline/XLSXgen.py", jsonPath, xlsxPath]);

    const xlsxData = await readFile(xlsxPath);
    const base64xlsx = xlsxData.toString("base64");

    await unlink(jsonPath);
    await unlink(xlsxPath);

    return NextResponse.json({ xlsx: base64xlsx }, { status: 200 });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal Server Error" },
      { status: 500 },
    );
  }
}
