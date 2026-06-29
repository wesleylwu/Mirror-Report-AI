from flask import Flask, request, send_file, make_response, jsonify
import io
import json
import base64
import urllib.parse
import sys
import re
from pathlib import Path
from PIL import Image
import fitz
import concurrent.futures

sys.path.append(str(Path(__file__).parent.parent))

from pipeline.JSONgen import extract_text_from_image
from pipeline.XLSXgen import _load_templates, _match_template, fill_template
from openpyxl import Workbook

app = Flask(__name__)

@app.route("/api/convert", methods=["POST"])
@app.route("/api/py_convert", methods=["POST"])
def convert():
    if request.is_json:
        body = request.get_json()
        extracted_data = body.get("extractedData", {})
        wb = Workbook()
        default_sheet = wb.active
        pages = extracted_data.get("pages")
        if pages is None:
            pages = [extracted_data]
        templates = _load_templates()
        for idx, page_data in enumerate(pages):
            tmpl = _match_template(page_data, templates)
            title = page_data.get("title", f"Sheet {idx+1}")
            clean_title = re.sub(r'[:\\/?*\[\]]', '', title)[:30].strip() or f"Page {idx+1}"
            orig_title = clean_title
            ctr = 1
            while clean_title in wb.sheetnames:
                suffix = f"_{ctr}"
                clean_title = orig_title[:30 - len(suffix)] + suffix
                ctr += 1
            ws = wb.create_sheet(title=clean_title)
            fill_template(tmpl, page_data, ws)
        if len(wb.worksheets) > 1:
            wb.remove(default_sheet)
        out_stream = io.BytesIO()
        wb.save(out_stream)
        xlsx_data = out_stream.getvalue()
        base64_xlsx = base64.b64encode(xlsx_data).decode("utf-8")
        return jsonify({
            "xlsx": base64_xlsx
        })

    files = request.files.getlist("file")
    if not files or files[0].filename == "":
        return jsonify({"error": "No files provided"}), 400

    tasks = []
    for file in files:
        filename = file.filename
        file_bytes = file.read()
        if filename.lower().endswith(".pdf"):
            try:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                for page_idx in range(len(doc)):
                    page = doc.load_page(page_idx)
                    pix = page.get_pixmap(dpi=150)
                    img_data = pix.tobytes("jpeg")
                    img = Image.open(io.BytesIO(img_data))
                    tasks.append((img, f"{filename} (page {page_idx + 1})"))
            except Exception as e:
                return jsonify({"error": f"Error parsing PDF: {str(e)}"}), 500
        else:
            try:
                img = Image.open(io.BytesIO(file_bytes))
                tasks.append((img, filename))
            except Exception as e:
                return jsonify({"error": f"Error parsing image: {str(e)}"}), 500

    if not tasks:
        return jsonify({"error": "No valid pages to process"}), 400

    pages_data = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(extract_text_from_image, task[0], task[1]) for task in tasks]
            for f in futures:
                pages_data.append(f.result())
    except Exception as e:
        return jsonify({"error": f"OCR extraction failed: {str(e)}"}), 500

    wb = Workbook()
    default_sheet = wb.active
    templates = _load_templates()
    pages_result = []

    for idx, page_data in enumerate(pages_data):
        try:
            tmpl = _match_template(page_data, templates)
            title = page_data.get("title", f"Sheet {idx+1}")
            clean_title = re.sub(r'[:\\/?*\[\]]', '', title)[:30].strip() or f"Page {idx+1}"
            orig_title = clean_title
            ctr = 1
            while clean_title in wb.sheetnames:
                suffix = f"_{ctr}"
                clean_title = orig_title[:30 - len(suffix)] + suffix
                ctr += 1
            ws = wb.create_sheet(title=clean_title)
            fill_template(tmpl, page_data, ws)
            pages_result.append({
                "extractedData": page_data,
                "template": tmpl
            })
        except Exception as e:
            return jsonify({"error": f"Excel generation failed: {str(e)}"}), 500

    if len(wb.worksheets) > 1:
        wb.remove(default_sheet)

    out_stream = io.BytesIO()
    wb.save(out_stream)
    xlsx_data = out_stream.getvalue()
    base64_xlsx = base64.b64encode(xlsx_data).decode("utf-8")

    out_filename = "batch_export.xlsx"
    if len(files) == 1:
        base_name = Path(files[0].filename).stem
        out_filename = f"{base_name}.xlsx"

    return jsonify({
        "pages": pages_result,
        "xlsx": base64_xlsx,
        "filename": out_filename
    })
