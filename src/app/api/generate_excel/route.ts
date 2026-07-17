import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, readFile, unlink, stat } from "fs/promises";
import path from "path";
import os from "os";
import sql from "mssql";

const config: sql.config = {
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  server: process.env.DB_HOST || "",
  port: parseInt(process.env.DB_PORT || "51399"),
  database: process.env.DB_NAME,
  options: {
    encrypt: false,
    trustServerCertificate: true,
  },
};

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

    const pool = await sql.connect(config);

    if (extractedData) {
      const selectRes = await pool
        .request()
        .input("id", sql.UniqueIdentifier, id)
        .query("SELECT extracted_data FROM parsed_documents WHERE id = @id");
      if (selectRes.recordset.length > 0) {
        let currentData = selectRes.recordset[0].extracted_data || [];
        if (typeof currentData === "string") {
          currentData = JSON.parse(currentData);
        }
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
        await pool
          .request()
          .input("data", sql.NVarChar(sql.MAX), JSON.stringify(mergedData))
          .input("id", sql.UniqueIdentifier, id)
          .query("UPDATE parsed_documents SET extracted_data = @data WHERE id = @id");
      }
    }

    const dbRes = await pool
      .request()
      .input("id", sql.UniqueIdentifier, id)
      .query("SELECT template_schema, extracted_data, code FROM parsed_documents WHERE id = @id");

    if (dbRes.recordset.length === 0) {
      return NextResponse.json(
        { error: "Document not found" },
        { status: 404 },
      );
    }

    const row = dbRes.recordset[0];
    const templateSchema = typeof row.template_schema === "string" ? JSON.parse(row.template_schema) : row.template_schema;
    const extractedDataObj = typeof row.extracted_data === "string" ? JSON.parse(row.extracted_data) : row.extracted_data;

    const payload = {
      pages: [
        {
          template: templateSchema,
          data: extractedDataObj,
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
