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

def _sheet_name_from_page(page_data: dict, idx: int) -> str:
    tmpl = page_data.get("template") or {}
    name = str(tmpl.get("sheet_name") or f"Sheet {idx + 1}")
    return re.sub(r'[:\\/?*\[\]]', '', name)[:30].strip() or f"Page {idx + 1}"

def _extract_data(page_data: dict) -> dict:
    sheet_name = _sheet_name_from_page(page_data, 0)
    cells = []
    for item in (page_data.get("data") or []):
        row = item.get("r") or item.get("row")
        col = item.get("c") or item.get("col")
        val = item.get("v") or item.get("value") or ""
        if val and row and col:
            cells.append({"row": int(row), "col": int(col), "value": val})
    return {"sheet_name": sheet_name, "cells": cells}

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
                    pix = doc.load_page(i).get_pixmap(dpi=150)
                    tasks.append((Image.open(io.BytesIO(pix.tobytes("jpeg"))), f"{fname} (page {i+1})"))
            except Exception as e:
                return jsonify({"error": f"PDF error: {e}"}), 500
        else:
            try:
                tasks.append((Image.open(io.BytesIO(fbytes)), fname))
            except Exception as e:
                return jsonify({"error": f"Image error: {e}"}), 500

    if not tasks:
        return jsonify({"error": "No valid pages"}), 400

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(extract_text_from_image, t[0], t[1]) for t in tasks]
            pages_data = [f.result() for f in futures]
    except Exception as e:
        return jsonify({"error": f"OCR failed: {e}"}), 500

    page_data = pages_data[0]
    filename = page_data.get("filename") or "document"
    template_schema = page_data.get("template") or {}
    extracted_data = page_data.get("data") or []
    code = page_data.get("code") or ""
    html = get_html_content(page_data)

    try:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            return jsonify({"error": "DATABASE_URL environment variable is missing"}), 500
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO parsed_documents (filename, template_schema, extracted_data, code) VALUES (%s, %s, %s, %s) RETURNING id",
            (filename, json.dumps(template_schema), json.dumps(extracted_data), code)
        )
        doc_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": f"Database connection/insertion failed: {e}"}), 500

    return jsonify({
        "id": str(doc_id),
        "html": html
    })
