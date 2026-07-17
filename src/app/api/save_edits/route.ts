import { NextResponse } from "next/server";
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
    const pool = await sql.connect(config);
    await pool
      .request()
      .input("data", sql.NVarChar(sql.MAX), JSON.stringify(data))
      .input("id", sql.UniqueIdentifier, id)
      .query("UPDATE parsed_documents SET extracted_data = @data WHERE id = @id");

    return NextResponse.json({ success: true }, { status: 200 });
  } catch (error) {
    console.error("Autosave error:", error);
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

