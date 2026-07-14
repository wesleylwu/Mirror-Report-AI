import { NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl:
    process.env.DATABASE_URL?.includes("supabase.co") ||
    process.env.DATABASE_URL?.includes("pooler.supabase.com")
      ? { rejectUnauthorized: false }
      : undefined,
});

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
    await pool.query(
      "UPDATE parsed_documents SET extracted_data = $1 WHERE id = $2",
      [JSON.stringify(data), id],
    );
    return NextResponse.json({ success: true }, { status: 200 });
  } catch (error: any) {
    console.error("Autosave error:", error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
