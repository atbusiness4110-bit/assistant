# -*- coding: utf-8 -*-
"""
Created on Sun Oct 19 14:03:36 2025

@author: mthom
"""

# server.py
# Lexi webhook server: receive summaries from Vapi, store in SQLite, serve dashboard & API.

import os
import sqlite3
from flask import Flask, request, jsonify, render_template_string, abort
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # loads .env locally; Render uses Env Vars UI

# Config
DB_PATH = os.getenv("DB_PATH", "calls.db")
SECRET = os.getenv("WEBHOOK_SECRET", None)  # set on Render and in Vapi as header

app = Flask(__name__)
CORS(app)

# Init DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS calls (
        id TEXT PRIMARY KEY,
        phone_from TEXT,
        phone_to TEXT,
        transcript TEXT,
        summary TEXT,
        duration INTEGER,
        raw_json TEXT,
        received_at TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

# Helper to insert call
def save_call(call_id, phone_from, phone_to, transcript, summary, duration, raw_json):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO calls (id, phone_from, phone_to, transcript, summary, duration, raw_json, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (call_id, phone_from, phone_to, transcript, summary, duration, raw_json, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# Health
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status":"lexi-server-live"})

# Webhook endpoint for Vapi -> POST
@app.route("/webhook", methods=["POST"])
def webhook():
    # optional simple secret header authentication
    expected = SECRET
    if expected:
        got = request.headers.get("X-Webhook-Secret")
        if not got or got != expected:
            return jsonify({"error":"unauthorized"}), 401

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error":"no json"}), 400

    # Try common shapes; adapt to the payload Vapi sends
    call = data.get("call") or data
    call_id = call.get("id") or call.get("call_id") or call.get("uuid") or str(datetime.utcnow().timestamp())
    phone_from = call.get("from") or call.get("caller") or ""
    phone_to = call.get("to") or ""
    transcript = call.get("transcript") or call.get("full_transcript") or ""
    summary = call.get("summary") or call.get("short_summary") or ""
    duration = call.get("duration") or 0

    # Save raw json as string
    import json
    raw_json = json.dumps(data)

    save_call(call_id, phone_from, phone_to, transcript, summary, duration, raw_json)
    print(f"Saved call {call_id} from {phone_from}")

    return jsonify({"status":"received"}), 200

# JSON API for desktop app to fetch latest calls
@app.route("/api/calls", methods=["GET"])
def api_calls():
    # allow small API key via header
    api_key = request.headers.get("X-API-KEY")
    expected = os.getenv("API_KEY")
    if expected and api_key != expected:
        return jsonify({"error":"unauthorized"}), 401

    # return latest 50
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, phone_from, phone_to, summary, transcript, duration, received_at FROM calls ORDER BY received_at DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "from": r[1],
            "to": r[2],
            "summary": r[3],
            "transcript": r[4],
            "duration": r[5],
            "received_at": r[6]
        })
    return jsonify({"calls": items})

# Simple HTML dashboard
DASH_TEMPLATE = """
<!doctype html>
<title>Lexi Call Summaries</title>
<h1>Lexi Call Summaries</h1>
<p>Auto-refreshed every 10s</p>
<table border=1 cellpadding=6>
<tr><th>Time (UTC)</th><th>From</th><th>Summary</th><th>Transcript</th></tr>
{% for c in calls %}
<tr>
  <td>{{c.received_at}}</td>
  <td>{{c.from}}</td>
  <td>{{c.summary}}</td>
  <td style="max-width:600px;white-space:pre-wrap">{{c.transcript}}</td>
</tr>
{% endfor %}
</table>
<script>
setTimeout(()=>location.reload(),10000);
</script>
"""

@app.route("/calls", methods=["GET"])
def calls_page():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, phone_from, phone_to, summary, transcript, duration, received_at FROM calls ORDER BY received_at DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()
    calls = []
    for r in rows:
        calls.append({
            "id": r[0],
            "from": r[1],
            "to": r[2],
            "summary": r[3],
            "transcript": r[4],
            "duration": r[5],
            "received_at": r[6]
        })
    return render_template_string(DASH_TEMPLATE, calls=calls)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
