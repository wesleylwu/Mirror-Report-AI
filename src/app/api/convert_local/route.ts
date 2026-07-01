import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, readFile, unlink, readdir, stat } from "fs/promises";
import path from "path";
import os from "os";

interface LocalTemplate {
  match?: {
    title?: string;
    section_header?: string;
  };
  [key: string]: unknown;
}

export const maxDuration = 120;

export async function POST(req: NextRequest) {
  const contentType = req.headers.get("content-type") || "";

  // Support JSON payload for edited template regeneration (multi-page/batch)
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
      return NextResponse.json(
        {
          xlsx: base64xlsx,
        },
        { status: 200 },
      );
    } catch (err) {
      console.error("XLSX regeneration error:", err);
      return NextResponse.json(
        { error: err instanceof Error ? err.message : "Regeneration failed" },
        { status: 500 },
      );
    } finally {
      unlink(jsonPath).catch(() => {});
      unlink(xlsxPath).catch(() => {});
    }
  }

  // Handle standard multipart image/PDF upload (supports multiple files)
  const formData = await req.formData();
  const files = formData.getAll("file") as File[];

  if (files.length === 0) {
    return NextResponse.json({ error: "No files provided" }, { status: 400 });
  }

  const id = `mirror_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const tempFiles: string[] = [];
  const jsonPath = path.join(os.tmpdir(), `${id}.json`);
  const xlsxPath = path.join(os.tmpdir(), `${id}.xlsx`);

  try {
    // Write all uploaded files to tmp locations
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const ext = path.extname(file.name) || ".jpg";
      const filePath = path.join(os.tmpdir(), `${id}_${i}${ext}`);
      await writeFile(filePath, Buffer.from(await file.arrayBuffer()));
      tempFiles.push(filePath);
    }

    // Run Python JSONgen on all files concurrently
    await runPython(process.cwd(), [
      "pipeline/JSONgen.py",
      ...tempFiles,
      jsonPath,
    ]);

    // Run Python XLSXgen to generate multi-sheet workbook
    await runPython(process.cwd(), ["pipeline/XLSXgen.py", jsonPath, xlsxPath]);

    const jsonContent = await readFile(jsonPath, "utf-8");
    const extractedData = JSON.parse(jsonContent); // always structured as { pages: [...] }

    const templatesDir = path.join(process.cwd(), "pipeline", "templates");
    const templateFiles = await readdir(templatesDir);
    const templates: LocalTemplate[] = [];

    for (const f of templateFiles) {
      if (f.endsWith(".json")) {
        const fileContent = await readFile(path.join(templatesDir, f), "utf-8");
        templates.push(JSON.parse(fileContent));
      }
    }

    // Process matched templates for each page
    const pagesResult = [];
    const pagesList = extractedData.pages || [];

    for (const pageData of pagesList) {
      if (pageData.header) {
        if (pageData.header["店番"] === "S50") {
          pageData.header["店番"] = "シ50";
        }
      }
      const title = (pageData.title || "").trim();
      const section = (pageData.section_header || "").trim();
      let matchedTemplate: LocalTemplate | null = null;

      for (const tmpl of templates) {
        const m = tmpl.match || {};
        const isTitleMatch =
          (m.title || "").trim() === title ||
          (tmpl.id === "売上実績表" &&
            (title === "得意先別／営業目標" || title === "売上実績表"));
        if (isTitleMatch && (m.section_header || "").trim() === section) {
          matchedTemplate = tmpl;
          break;
        }
      }

      if (!matchedTemplate) {
        for (const tmpl of templates) {
          const m = tmpl.match || {};
          const isTitleMatch =
            (m.title || "").trim() === title ||
            (tmpl.id === "売上実績表" &&
              (title === "得意先別／営業目標" || title === "売上実績表"));
          if (isTitleMatch) {
            matchedTemplate = tmpl;
            break;
          }
        }
      }

      if (!matchedTemplate && templates.length > 0) {
        matchedTemplate = templates[0];
      }

      pagesResult.push({
        extractedData: pageData,
        template: matchedTemplate,
      });
    }

    let outName = "batch_export.xlsx";
    if (files.length === 1) {
      const ext = path.extname(files[0].name);
      outName = `${path.basename(files[0].name, ext)}.xlsx`;
    }

    const xlsxData = await readFile(xlsxPath);
    const base64xlsx = xlsxData.toString("base64");

    return NextResponse.json(
      {
        pages: pagesResult,
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
    unlink(jsonPath).catch(() => {});
    unlink(xlsxPath).catch(() => {});
    for (const p of tempFiles) {
      unlink(p).catch(() => {});
    }
  }
}

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
    } catch {
      // ignore
    }
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
