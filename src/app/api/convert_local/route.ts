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

    const client = new Client({
      connectionString: process.env.DATABASE_URL,
    });
    await client.connect();

    let query = "";
    const sheetName = pageData.template?.sheet_name || "";

    if (sheetName.includes("売上") || sheetName.includes("実績")) {
      query =
        "SELECT month, category, last_year_actual, last_year_total, achievement_rate, target, this_year_actual, this_year_total FROM sales_performance";
    } else if (
      (sheetName.includes("工事") ||
        sheetName.includes("費用") ||
        sheetName.includes("明細")) &&
      !sheetName.includes("業務")
    ) {
      query =
        "SELECT code, company_name, prev_month_balance, this_month_billed, this_month_received, this_month_adjusted, this_month_paid_construction, this_month_paid_management, this_month_balance, next_month_balance FROM construction_costs";
    } else if (
      sheetName.includes("業務") ||
      sheetName.includes("賃料") ||
      sheetName.includes("物件")
    ) {
      query =
        "SELECT no, property_name, building_no, room_no, contract_type, start_date, end_date, rent, common_fee, parking_fee, other_fee, total, amount_received, difference, cumulative_received, cumulative_difference, management_fee, repair_fee, remarks FROM rent_details";
    } else {
      query =
        "SELECT order_no, issue_date, item_name, ingredient_name, unit_requirement, total_quantity, supplier, order_content, lot_no, due_date, order_qty, control_no, completion_status, completion_date FROM internal_mfg_orders";
    }

    const mfgRes = await client.query(query);
    const dbRows = mfgRes.rows;

    interface CellData {
      r: number;
      c: number;
      v: string;
    }

    const mapping = pageData.mapping || {};
    const extractedData: CellData[] = [];

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
        const coord = mapping[field];
        if (coord && typeof coord === "object") {
          const r = coord.r;
          const c = coord.c;
          const rows = coord.rows;
          if (r !== undefined && c !== undefined) {
            let val = firstRow[field];
            if (val instanceof Date) {
              val = formatDate(val);
            }
            extractedData.push({ r: Number(r), c: Number(c), v: String(val) });
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

    pageData.data = extractedData;
    await writeFile(jsonPath, JSON.stringify(parsedData), "utf-8");

    const html = await getHtmlFromPython(jsonPath);

    const dbRes = await client.query(
      "INSERT INTO parsed_documents (filename, template_schema, extracted_data, code) VALUES ($1, $2, $3, $4) RETURNING id",
      [
        pageData.filename || "document",
        JSON.stringify(pageData.template || {}),
        JSON.stringify(extractedData),
        pageData.code || "",
      ],
    );
    await client.end();

    const docId = dbRes.rows[0].id;

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
