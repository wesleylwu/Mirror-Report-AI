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

async function getHtmlFromPython(jsonPath: string): Promise<string> {
  const pythonCmd = await getPythonCommand();
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonCmd, [
      "-c",
      "import sys, json; sys.path.append('pipeline'); from HTMLgen import get_html_content; data=json.load(open(sys.argv[1], encoding='utf-8')); print(get_html_content(data['pages'][0]))",
      jsonPath,
    ]);
    const stdout: string[] = [];
    const stderr: string[] = [];
    proc.stdout.on("data", (d: Buffer) => stdout.push(d.toString()));
    proc.stderr.on("data", (d: Buffer) => stderr.push(d.toString()));
    proc.on("close", (code: number) => {
      if (code === 0) resolve(stdout.join(""));
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
    const parsedData = JSON.parse(jsonContent);

    const pagesList = parsedData.pages || [];
    const pageData = pagesList[0];
    if (!pageData) {
      return NextResponse.json(
        { error: "No page data extracted" },
        { status: 500 },
      );
    }

    interface CellData {
      r: number;
      c: number;
      v: string;
    }

    let extractedData: CellData[] = [];

    try {
      const pool = await sql.connect(config);

      const mapping = pageData.mapping || {};
      const matchedTable = mapping.matched_table || "取引データ";
      const rawFieldsMapping =
        mapping.fields && typeof mapping.fields === "object"
          ? mapping.fields
          : mapping;

      const fieldsMapping: Record<
        string,
        { r?: number; c?: number; rows?: number[] }
      > = {};
      for (const [k, v] of Object.entries(rawFieldsMapping || {})) {
        if (k !== "matched_table" && v && typeof v === "object") {
          fieldsMapping[k] = v as { r?: number; c?: number; rows?: number[] };
        }
      }

      const colsToQuery = Object.keys(fieldsMapping);
      if (colsToQuery.length === 0) {
        colsToQuery.push(
          "伝票日付",
          "伝票Ｎｏ",
          "商品名",
          "数量",
          "単価",
          "金額",
        );
      }
      const colsStr = colsToQuery.map((c) => `[${c}]`).join(", ");
      const query = `SELECT ${colsStr} FROM [${matchedTable}]`;

      const mfgRes = await pool.request().query(query);
      const dbRows = mfgRes.recordset || [];

      if (dbRows.length > 0) {
        const firstRow = dbRows[0];
        const colnames = Object.keys(firstRow);

        const formatDate = (val: unknown) => {
          if (val instanceof Date) {
            return val.toISOString().split("T")[0];
          }
          return val !== null && val !== undefined ? String(val) : "";
        };

        for (const field of colnames) {
          const coord = fieldsMapping[field];
          if (coord && typeof coord === "object") {
            const r = coord.r;
            const c = coord.c;
            const rows = coord.rows;
            if (r !== undefined && c !== undefined) {
              let val = firstRow[field];
              if (val instanceof Date) {
                val = formatDate(val);
              }
              extractedData.push({
                r: Number(r),
                c: Number(c),
                v: String(val),
              });
            } else if (c !== undefined && Array.isArray(rows)) {
              for (let idx = 0; idx < dbRows.length; idx++) {
                if (idx < rows.length) {
                  let val = dbRows[idx][field];
                  if (val instanceof Date) {
                    val = formatDate(val);
                  }
                  extractedData.push({
                    r: Number(rows[idx]),
                    c: Number(c),
                    v: String(val),
                  });
                }
              }
            }
          }
        }
      }
    } catch (dbErr) {
      console.warn(
        "SQL Server query skipped/failed (falling back to extracted data):",
        dbErr,
      );
      extractedData = Array.isArray(pageData.data) ? pageData.data : [];
    }

    pageData.data = extractedData;
    await writeFile(jsonPath, JSON.stringify(parsedData), "utf-8");

    const html = await getHtmlFromPython(jsonPath);

    interface DBDoc {
      id: string;
      filename: string;
      template_schema: unknown;
      extracted_data: Array<{
        r?: number;
        c?: number;
        row?: number;
        col?: number;
        v?: string | number;
        value?: string | number;
      }>;
      code: string;
    }

    // Save to local JSON database instead of writing to SQL Server
    const docId = `mirror_doc_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const localDbPath = path.join(process.cwd(), "parsed_documents.json");
    let docs: Record<string, DBDoc> = {};
    try {
      const existing = await readFile(localDbPath, "utf-8");
      docs = JSON.parse(existing);
    } catch {}

    docs[docId] = {
      id: docId,
      filename: pageData.filename || "document",
      template_schema: pageData.template || {},
      extracted_data: extractedData,
      code: pageData.code || "",
    };
    await writeFile(localDbPath, JSON.stringify(docs, null, 2), "utf-8");

    return NextResponse.json(
      {
        id: docId,
        html: html,
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
