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

        sheet_name = template_schema.get("sheet_name", "")
        print(f"[DEBUG py_convert] Detected sheet name: {sheet_name}", file=sys.stderr)
        if "売上" in sheet_name or "実績" in sheet_name:
            query = "SELECT month, category, last_year_actual, last_year_total, achievement_rate, target, this_year_actual, this_year_total FROM sales_performance"
        elif ("工事" in sheet_name or "費用" in sheet_name or "明細" in sheet_name) and not "業務" in sheet_name:
            query = "SELECT code, company_name, prev_month_balance, this_month_billed, this_month_received, this_month_adjusted, this_month_paid_construction, this_month_paid_management, this_month_balance, next_month_balance FROM construction_costs"
        elif "業務" in sheet_name or "賃料" in sheet_name or "物件" in sheet_name:
            query = "SELECT no, property_name, building_no, room_no, contract_type, start_date, end_date, rent, common_fee, parking_fee, other_fee, total, amount_received, difference, cumulative_received, cumulative_difference, management_fee, repair_fee, remarks FROM rent_details"
        elif "取引" in sheet_name or "伝票" in sheet_name or "一覧" in sheet_name:
            query = "SELECT transaction_date, slip_no, item_code, item_name, packaging, quantity, unit_price, amount FROM transaction_data_list"
        else:
            query = "SELECT order_no, issue_date, item_code, item_name, process_seq, order_qty, due_date, supplier, order_content, lot_no, control_no, completion_status, completion_date, ingredient_name, unit_requirement, total_quantity, weighed_by, material_lot, checked_by FROM internal_mfg_orders"

        print(f"[DEBUG py_convert] Executing query: {query}", file=sys.stderr)
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

        print(f"[DEBUG py_convert] Mapping keys from Claude: {list(mapping.keys())}", file=sys.stderr)

        extracted_data = []
        if rows_dict:
            first_row = rows_dict[0]
            for field in colnames:
                coord = mapping.get(field)
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

    html = get_html_content({"template": template_schema, "data": extracted_data, "html": page_data.get("html")})

    return jsonify({
        "id": str(doc_id),
        "html": html
    })
