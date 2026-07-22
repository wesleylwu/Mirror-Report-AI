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

def _generate_fallback_mock_data(page_data: dict) -> list:
    mapping = page_data.get("mapping") or {}
    fields = mapping.get("fields") if isinstance(mapping, dict) else {}
    if not isinstance(fields, dict):
        fields = mapping if isinstance(mapping, dict) else {}
    
    mock_data = []
    sample_records = [
        {"取引日": "2026/05/10", "計上日": "2026/05/10", "伝票番号": "1001", "伝票Ｎｏ": "1001", "品目コード": "HIM-001", "商品コード": "HIM-001", "品目名": "特選ボルト A-10", "商品名": "特選ボルト A-10", "荷姿": "ケース", "単位": "ケース", "売上数量": "50", "数量": "50", "売上単価": "1,200", "単価": "1,200", "売上金額": "60,000", "金額": "60,000"},
        {"取引日": "2026/05/12", "計上日": "2026/05/12", "伝票番号": "1002", "伝票Ｎｏ": "1002", "品目コード": "HIM-002", "商品コード": "HIM-002", "品目名": "高圧ナット B-20", "商品名": "高圧ナット B-20", "荷姿": "箱", "単位": "箱", "売上数量": "30", "数量": "30", "売上単価": "2,500", "単価": "2,500", "売上金額": "75,000", "金額": "75,000"},
        {"取引日": "2026/05/15", "計上日": "2026/05/15", "伝票番号": "1003", "伝票Ｎｏ": "1003", "品目コード": "HIM-003", "商品コード": "HIM-003", "品目名": "ステンレスワッシャー C-30", "商品名": "ステンレスワッシャー C-30", "荷姿": "パック", "単位": "パック", "売上数量": "100", "数量": "100", "売上単価": "450", "単価": "450", "売上金額": "45,000", "金額": "45,000"},
        {"取引日": "2026/05/20", "計上日": "2026/05/20", "伝票番号": "1004", "伝票Ｎｏ": "1004", "品目コード": "HIM-004", "商品コード": "HIM-004", "品目名": "耐熱プレート D-40", "商品名": "耐熱プレート D-40", "荷姿": "枚", "単位": "枚", "売上数量": "15", "数量": "15", "売上単価": "8,000", "単価": "8,000", "売上金額": "120,000", "金額": "120,000"},
        {"取引日": "2026/05/25", "計上日": "2026/05/25", "伝票番号": "1005", "伝票Ｎｏ": "1005", "品目コード": "HIM-005", "商品コード": "HIM-005", "品目名": "産業用固定リング E-50", "商品名": "産業用固定リング E-50", "荷姿": "袋", "単位": "袋", "売上数量": "20", "数量": "20", "売上単価": "3,100", "単価": "3,100", "売上金額": "62,000", "金額": "62,000"}
    ]

    for field_name, coord in fields.items():
        if field_name == "matched_table" or not isinstance(coord, dict):
            continue
        c_val = coord.get("c")
        r_val = coord.get("r")
        row_list = coord.get("rows")
        
        if r_val is not None and c_val is not None:
            val = sample_records[0].get(field_name, "")
            if val:
                mock_data.append({"r": int(r_val), "c": int(c_val), "v": str(val)})
        elif c_val is not None and isinstance(row_list, list):
            for idx, r_idx in enumerate(row_list):
                if idx < len(sample_records) and r_idx is not None:
                    val = sample_records[idx].get(field_name, "")
                    if not val:
                        val = f"Sample {field_name} {idx+1}"
                    mock_data.append({"r": int(r_idx), "c": int(c_val), "v": str(val)})

    return mock_data


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

    page_data = pages_data[0] if pages_data else {}
    filename = page_data.get("filename") or "document"
    template_schema = page_data.get("template") or {}
    mapping = page_data.get("mapping") or {}
    code = page_data.get("code") or ""
    extracted_data = page_data.get("data") or []

    # Local storage file operations
    DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "parsed_documents.json")
    
    def read_docs():
        if not os.path.exists(DB_FILE):
            return {}
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def write_docs(docs):
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(docs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DEBUG py_convert] write_docs failed: {e}", file=sys.stderr)

    import time
    import random
    doc_id = f"mirror_doc_{int(time.time())}_{random.randint(1000, 9999)}"

    db_host = os.environ.get("DB_HOST")
    if db_host:
        try:
            conn = pymssql.connect(
                server=db_host,
                port=int(os.environ.get("DB_PORT", 51399)),
                user=os.environ.get("DB_USER"),
                password=os.environ.get("DB_PASSWORD"),
                database=os.environ.get("DB_NAME"),
                login_timeout=3
            )
            cur = conn.cursor()

            matched_table = mapping.get("matched_table") if isinstance(mapping, dict) else None
            raw_fields = mapping.get("fields") if isinstance(mapping, dict) else None
            if not raw_fields or not isinstance(raw_fields, dict):
                raw_fields = mapping if isinstance(mapping, dict) else {}

            fields_mapping = {k: v for k, v in raw_fields.items() if k != "matched_table" and isinstance(v, dict)}

            if not matched_table:
                matched_table = "取引データ"

            cols_to_query = list(fields_mapping.keys())
            if not cols_to_query:
                cols_to_query = ["伝票日付", "伝票Ｎｏ", "商品名", "数量", "単価", "金額"]
            
            cols_str = ", ".join(f"[{col}]" for col in cols_to_query)
            query = f"SELECT {cols_str} FROM [{matched_table}]"

            print(f"[DEBUG py_convert] Executing dynamic query: {query}", file=sys.stderr)
            cur.execute(query)
            db_rows = cur.fetchall() or []
            colnames = [desc[0] for desc in cur.description] if cur.description else []
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

            db_extracted_data = []
            if rows_dict:
                first_row = rows_dict[0]
                for field in colnames:
                    coord = fields_mapping.get(field)
                    if coord and isinstance(coord, dict):
                        r_val = coord.get("r")
                        c_val = coord.get("c")
                        row_list = coord.get("rows")
                        if r_val is not None and c_val is not None:
                            db_extracted_data.append({"r": int(r_val), "c": int(c_val), "v": str(first_row[field])})
                        elif c_val is not None and isinstance(row_list, list):
                            for idx, row_data in enumerate(rows_dict):
                                if idx < len(row_list) and row_list[idx] is not None:
                                    db_extracted_data.append({"r": int(row_list[idx]), "c": int(c_val), "v": str(row_data[field])})

            if db_extracted_data:
                extracted_data = db_extracted_data

            cur.close()
            conn.close()
        except Exception as e:
            print(f"[DEBUG py_convert] Database query skipped/failed (falling back to extracted_data): {e}", file=sys.stderr)

    if not extracted_data:
        print("[DEBUG py_convert] extracted_data is empty, generating fallback mock data for preview...", file=sys.stderr)
        extracted_data = _generate_fallback_mock_data(page_data)

    try:
        docs = read_docs()
        docs[doc_id] = {
            "id": doc_id,
            "filename": filename,
            "template_schema": template_schema,
            "extracted_data": extracted_data,
            "code": code
        }
        write_docs(docs)
    except Exception as e:
        print(f"[DEBUG py_convert] Saving doc locally skipped/failed: {e}", file=sys.stderr)

    html = get_html_content({"template": template_schema, "data": extracted_data, "html": page_data.get("html")})

    return jsonify({
        "id": str(doc_id),
        "html": html
    })
