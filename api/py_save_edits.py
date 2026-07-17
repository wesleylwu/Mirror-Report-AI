import json
import sys
import os
from flask import Flask, request, jsonify
import pymssql

app = Flask(__name__)

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
        conn = pymssql.connect(
            server=os.environ.get("DB_HOST"),
            port=int(os.environ.get("DB_PORT", 51399)),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            database=os.environ.get("DB_NAME")
        )
        cur = conn.cursor()
        cur.execute(
            "UPDATE parsed_documents SET extracted_data = %s WHERE id = %s",
            (json.dumps(data), doc_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"[Autosave] Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e)}), 500
