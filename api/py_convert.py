from flask import Flask, request, jsonify
import io
import json
import base64
import re
import sys
from pathlib import Path
from PIL import Image
import fitz
import concurrent.futures

sys.path.append(str(Path(__file__).parent.parent))

from pipeline.JSONgen import extract_text_from_image
from pipeline.XLSXgen import execute_code, render_sheet, populate_data
from pipeline.HTMLgen import render_html, get_html_content
from openpyxl import Workbook

app = Flask(__name__)


def _sheet_name_from_page(page_data: dict, idx: int) -> str:
    code = page_data.get("code", "")
    if code:
        m = re.search(r'ws\.title\s*=\s*["\']([^"\']+)["\']', code)
        if m:
            return re.sub(r'[:\\/?*\[\]]', '', m.group(1))[:30].strip()
    tmpl = page_data.get("template") or page_data
    name = str(tmpl.get("sheet_name") or f"Sheet {idx + 1}")
    return re.sub(r'[:\\/?*\[\]]', '', name)[:30].strip() or f"Page {idx + 1}"


def _build_workbook(pages: list) -> bytes:
    wb = Workbook()
    default = wb.active
    seen: set = set()
    for idx, page_data in enumerate(pages):
        if "error" in page_data:
            continue
        base = _sheet_name_from_page(page_data, idx)
        name, ctr = base or f"Sheet {idx + 1}", 1
        while name in seen:
            suffix = f"_{ctr}"
            name = base[: 30 - len(suffix)] + suffix
            ctr += 1
        seen.add(name)
        ws = wb.create_sheet(title=name)
        code = page_data.get("code", "")
        if code:
            try:
                execute_code(code, ws)
                populate_data(ws, page_data.get("data"))
            except Exception as e:
                print(f"Code execution failed for page {idx + 1}: {e}", file=sys.stderr)
                tmpl = page_data.get("template")
                if tmpl:
                    render_sheet(tmpl, ws)
        else:
            render_sheet(page_data.get("template") or page_data, ws)
    if len(wb.worksheets) > 1:
        wb.remove(default)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _extract_data(page_data: dict) -> dict:
    """Return the data values extracted from the document."""
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
    # JSON payload — re-render edited spec to xlsx
    if request.is_json:
        body = request.get_json()
        extracted = body.get("extractedData", {})
        pages = extracted.get("pages") or [extracted]
        try:
            xlsx_bytes = _build_workbook(pages)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        return jsonify({"xlsx": base64.b64encode(xlsx_bytes).decode()})

    # Multipart file upload — full pipeline
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

    pages_result = []
    for idx, page_data in enumerate(pages_data):
        raw = tasks[idx][1]
        m = re.match(r"^(.*)\.([a-zA-Z0-9]+)\s*(\(page \d+\))?$", raw)
        filename = f"{m.group(1)}{m.group(3) or ''}" if m else raw
        page_data["filename"] = filename
        html = get_html_content(page_data)
        pages_result.append({
            "dataJson":    _extract_data(page_data),
            "htmlContent": html,
            "filename":    filename,
        })

    try:
        xlsx_bytes = _build_workbook(pages_data)
    except Exception as e:
        return jsonify({"error": f"Excel error: {e}"}), 500

    out_filename = "batch_export.xlsx"
    if len(files) == 1:
        out_filename = f"{Path(files[0].filename).stem}.xlsx"

    return jsonify({
        "pages":    pages_result,
        "xlsx":     base64.b64encode(xlsx_bytes).decode(),
        "filename": out_filename,
    })
