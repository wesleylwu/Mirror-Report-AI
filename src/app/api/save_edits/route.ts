import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { id, data } = body;
    if (!id || data === undefined) {
      return NextResponse.json(
        { error: "Missing ID or data" },
        { status: 400 },
      );
    }

    const localDbPath = path.join(process.cwd(), "parsed_documents.json");
    let docs: any = {};
    try {
      const existing = await fs.readFile(localDbPath, "utf-8");
      docs = JSON.parse(existing);
    } catch {}

    if (docs[id]) {
      docs[id].extracted_data = data;
      await fs.writeFile(localDbPath, JSON.stringify(docs, null, 2), "utf-8");
      return NextResponse.json({ success: true }, { status: 200 });
    } else {
      return NextResponse.json(
        { error: "Document not found locally" },
        { status: 404 },
      );
    }
  } catch (error) {
    console.error("Autosave error:", error);
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

