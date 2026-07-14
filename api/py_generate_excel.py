import io
import json
import base64
import re
import sys
import os
from pathlib import Path
from flask import Flask, request, jsonify
import psycopg2
from openpyxl import Workbook

sys.path.append(str(Path(__file__).parent.parent))

from pipeline.XLSXgen import render_sheet

app = Flask(__name__)

def _sheet_name_from_page(page_data: dict, idx: int) -> str:
    tmpl = page_data.get("template") or {}
    name = str(tmpl.get("sheet_name") or f"Sheet {idx + 1}")
    return re.sub(r'[:\\/?*\[\]]', '', name)[:30].strip() or f"Page {idx + 1}"

@app.route("/api/generate_excel", methods=["POST"])
@app.route("/api/py_generate_excel", methods=["POST"])
def generate_excel():
    body = request.get_json() or {}
    doc_id = body.get("id")
    extracted_data = body.get("extractedData")
    if not doc_id:
        return jsonify({"error": "Missing ID"}), 400

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return jsonify({"error": "DATABASE_URL environment variable is missing"}), 500

    try:
        print(f"[Excel Gen] Starting for doc_id: {doc_id}", file=sys.stderr)
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        if extracted_data:
            print("[Excel Gen] Merging client edits...", file=sys.stderr)
            cur.execute("SELECT extracted_data FROM parsed_documents WHERE id = %s", (doc_id,))
            row = cur.fetchone()
            if row:
                current_data = row[0] or []
                if isinstance(current_data, str):
                    current_data = json.loads(current_data)
                edits = extracted_data.get("data") or []
                merged_map = {}
                for item in current_data:
                    r = item.get("r") if item.get("r") is not None else item.get("row")
                    c = item.get("c") if item.get("c") is not None else item.get("col")
                    v = item.get("v") if item.get("v") is not None else item.get("value")
                    merged_map[f"{r}_{c}"] = {"r": r, "c": c, "v": v}
                for item in edits:
                    r = item.get("r") if item.get("r") is not None else item.get("row")
                    c = item.get("c") if item.get("c") is not None else item.get("col")
                    v = item.get("v") if item.get("v") is not None else item.get("value")
                    merged_map[f"{r}_{c}"] = {"r": r, "c": c, "v": v}
                merged_data = list(merged_map.values())
                cur.execute(
                    "UPDATE parsed_documents SET extracted_data = %s WHERE id = %s",
                    (json.dumps(merged_data), doc_id)
                )
                print("[Excel Gen] Client edits merged successfully", file=sys.stderr)

        print("[Excel Gen] Fetching template and data from DB...", file=sys.stderr)
        cur.execute("SELECT template_schema, extracted_data FROM parsed_documents WHERE id = %s", (doc_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            print(f"[Excel Gen] Document {doc_id} not found", file=sys.stderr)
            return jsonify({"error": "Document not found"}), 404

        template_schema = row[0]
        extracted_data = row[1]

        if isinstance(template_schema, str):
            template_schema = json.loads(template_schema)
        if isinstance(extracted_data, str):
            extracted_data = json.loads(extracted_data)

        print("[Excel Gen] Compiling openpyxl workbook...", file=sys.stderr)
        wb = Workbook()
        default_sheet = wb.active
        ws = wb.create_sheet(title=_sheet_name_from_page({"template": template_schema}, 0))
        render_sheet(template_schema, ws, filled_data=extracted_data)

        if len(wb.worksheets) > 1:
            wb.remove(default_sheet)

        buf = io.BytesIO()
        wb.save(buf)
        xlsx_bytes = buf.getvalue()

        print("[Excel Gen] Compilation successful, returning base64 sheet", file=sys.stderr)
        return jsonify({
            "xlsx": base64.b64encode(xlsx_bytes).decode()
        })
    except Exception as e:
        print(f"[Excel Gen] Error: {e}", file=sys.stderr)
        return jsonify({"error": f"Database / Excel compilation failed: {e}"}), 500
