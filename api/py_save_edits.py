import json
import sys
import os
import pymssql
from flask import Flask, request, jsonify

app = Flask(__name__)

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

@app.route("/api/save_edits", methods=["POST"])
@app.route("/api/py_save_edits", methods=["POST"])
def save_edits():
    body = request.get_json() or {}
    doc_id = body.get("id")
    data = body.get("data")
    if not doc_id:
        return jsonify({"error": "Missing ID"}), 400
    if data is None:
        return jsonify({"error": "Missing data"}), 400

    try:
        docs = read_docs()
        if str(doc_id) in docs:
            docs[str(doc_id)]["extracted_data"] = data
            write_docs(docs)
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Document not found locally"}), 404
    except Exception as e:
        print(f"[Autosave] Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e)}), 500
