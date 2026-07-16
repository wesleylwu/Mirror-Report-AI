import io
import json
import base64
import re
import sys
import os
import concurrent.futures
from pathlib import Path
from flask import Flask, request, jsonify
from PIL import Image
import fitz
import psycopg2

sys.path.append(str(Path(__file__).parent.parent))

from pipeline.JSONgen import extract_text_from_image
from pipeline.HTMLgen import get_html_content

app = Flask(__name__)

@app.route("/api/convert", methods=["POST"])
@app.route("/api/py_convert", methods=["POST"])
def convert():
    files = request.files.getlist("file")
    if not files or files[0].filename == "":
        return jsonify({"error": "No files provided"}), 400

    tasks = []
    for file in files:
        fname = file.filename
        fbytes = file.read()
        if fname.lower().endswith(".pdf"):
            try:
                doc = fitz.open(stream=fbytes, filetype="pdf")
                for i in range(len(doc)):
                    pix = doc.load_page(i).get_pixmap(dpi=200)
                    tasks.append((Image.open(io.BytesIO(pix.tobytes("jpeg"))), f"{fname} (page {i+1})"))
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        else:
            try:
                tasks.append((Image.open(io.BytesIO(fbytes)), fname))
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    if not tasks:
        return jsonify({"error": "No valid pages"}), 400

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(extract_text_from_image, t[0], t[1]) for t in tasks]
            pages_data = [f.result() for f in futures]
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    page_data = pages_data[0]
    filename = page_data.get("filename") or "document"
    template_schema = page_data.get("template") or {}
    mapping = page_data.get("mapping") or {}
    code = page_data.get("code") or ""

    try:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            return jsonify({"error": "DATABASE_URL missing"}), 500
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("SELECT order_no, issue_date, item_name, ingredient_name, unit_requirement, total_quantity, supplier, order_content, lot_no, due_date, order_qty, control_no, completion_status, completion_date FROM internal_mfg_orders")
        db_rows = cur.fetchall()

        rows_dict = []
        for r in db_rows:
            rows_dict.append({
                "order_no": str(r[0]),
                "issue_date": str(r[1]),
                "item_name": str(r[2]),
                "ingredient_name": str(r[3]),
                "unit_requirement": float(r[4]) if r[4] is not None else 0.0,
                "total_quantity": float(r[5]) if r[5] is not None else 0.0,
                "supplier": str(r[6]) if r[6] is not None else "",
                "order_content": str(r[7]) if r[7] is not None else "",
                "lot_no": str(r[8]) if r[8] is not None else "",
                "due_date": str(r[9]) if r[9] is not None else "",
                "order_qty": float(r[10]) if r[10] is not None else 0.0,
                "control_no": str(r[11]) if r[11] is not None else "",
                "completion_status": str(r[12]) if r[12] is not None else "",
                "completion_date": str(r[13]) if r[13] is not None else ""
            })

        extracted_data = []
        if rows_dict:
            first_row = rows_dict[0]
            fields = [
                "order_no", "issue_date", "item_name", "ingredient_name", "unit_requirement", "total_quantity",
                "supplier", "order_content", "lot_no", "due_date", "order_qty", "control_no", "completion_status", "completion_date"
            ]
            for field in fields:
                coord = mapping.get(field)
                if coord and isinstance(coord, dict):
                    r_val = coord.get("r")
                    c_val = coord.get("c")
                    row_list = coord.get("rows")
                    if r_val is not None and c_val is not None:
                        extracted_data.append({"r": int(r_val), "c": int(c_val), "v": first_row[field]})
                    elif c_val is not None and isinstance(row_list, list):
                        for idx, row_data in enumerate(rows_dict):
                            if idx < len(row_list):
                                extracted_data.append({"r": int(row_list[idx]), "c": int(c_val), "v": str(row_data[field])})

        cur.execute(
            "INSERT INTO parsed_documents (filename, template_schema, extracted_data, code) VALUES (%s, %s, %s, %s) RETURNING id",
            (filename, json.dumps(template_schema), json.dumps(extracted_data), code)
        )
        doc_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    html = get_html_content({"template": template_schema, "data": extracted_data})

    return jsonify({
        "id": str(doc_id),
        "html": html
    })
