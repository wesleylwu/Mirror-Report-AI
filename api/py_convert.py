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
import pymssql

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

    # Local storage file operations
    DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "parsed_documents.json")
    
    def read_docs():
        if not os.path.exists(DB_FILE):
            return {}
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def write_docs(docs):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)

    try:
        conn = pymssql.connect(
            server=os.environ.get("DB_HOST"),
            port=int(os.environ.get("DB_PORT", 51399)),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            database=os.environ.get("DB_NAME")
        )
        cur = conn.cursor()

        # Parse dynamic mapping from Claude
        matched_table = mapping.get("matched_table")
        fields_mapping = mapping.get("fields") or {}
        
        # Revert to root keys if fields structure is absent
        if not matched_table:
            # Fallback if Claude returned flat mappings
            matched_table = "取引データ"
            fields_mapping = mapping

        # Build dynamic select query safely
        cols_to_query = list(fields_mapping.keys())
        if not cols_to_query:
            # Fallback if no columns mapped
            cols_to_query = ["伝票日付", "伝票Ｎｏ", "商品名", "数量", "単価", "金額"]
        
        cols_str = ", ".join(f"[{col}]" for col in cols_to_query)
        query = f"SELECT {cols_str} FROM {matched_table}"

        print(f"[DEBUG py_convert] Executing dynamic query: {query}", file=sys.stderr)
        cur.execute(query)
        db_rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        print(f"[DEBUG py_convert] Columns: {colnames}, Rows fetched: {len(db_rows)}", file=sys.stderr)

        rows_dict = []
        for r in db_rows:
            row_map = {}
            for col_idx, col_name in enumerate(colnames):
                val = r[col_idx]
                if isinstance(val, (int, float)) or (val is not None and type(val).__name__ == 'Decimal'):
                    row_map[col_name] = float(val)
                elif hasattr(val, 'strftime'):
                    row_map[col_name] = val.strftime('%Y-%m-%d')
                else:
                    row_map[col_name] = str(val) if val is not None else ""
            rows_dict.append(row_map)

        print(f"[DEBUG py_convert] Mapping keys from Claude: {list(fields_mapping.keys())}", file=sys.stderr)

        extracted_data = []
        if rows_dict:
            first_row = rows_dict[0]
            for field in colnames:
                coord = fields_mapping.get(field)
                if coord and isinstance(coord, dict):
                    r_val = coord.get("r")
                    c_val = coord.get("c")
                    row_list = coord.get("rows")
                    if r_val is not None and c_val is not None:
                        extracted_data.append({"r": int(r_val), "c": int(c_val), "v": str(first_row[field])})
                    elif c_val is not None and isinstance(row_list, list):
                        for idx, row_data in enumerate(rows_dict):
                            if idx < len(row_list):
                                extracted_data.append({"r": int(row_list[idx]), "c": int(c_val), "v": str(row_data[field])})

        print(f"[DEBUG py_convert] Extracted data size: {len(extracted_data)}", file=sys.stderr)

        # Generate a unique document id and save locally (no SQL Server writes!)
        import time
        import random
        doc_id = f"mirror_doc_{int(time.time())}_{random.randint(1000, 9999)}"
        docs = read_docs()
        docs[doc_id] = {
            "id": doc_id,
            "filename": filename,
            "template_schema": template_schema,
            "extracted_data": extracted_data,
            "code": code
        }
        write_docs(docs)
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    html = get_html_content({"template": template_schema, "data": extracted_data, "html": page_data.get("html")})

    return jsonify({
        "id": str(doc_id),
        "html": html
    })
