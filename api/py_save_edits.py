import json
import sys
import os
from flask import Flask, request, jsonify
import psycopg2

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

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return jsonify({"error": "DATABASE_URL environment variable is missing"}), 500

    try:
        conn = psycopg2.connect(db_url)
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
