# server.py
from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback
import json
import os
import threading

app = Flask(__name__)

# In-memory store (persisted to disk for restarts)
calls = {}
store_file = "calls.json"
lock = threading.Lock()

# Load persisted calls (if any)
if os.path.exists(store_file):
    try:
        with open(store_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                calls.update(loaded)
            elif isinstance(loaded, list):
                # allow old format (list) by converting to dict keyed by call_id
                for item in loaded:
                    cid = item.get("call_id")
                    if cid:
                        calls[cid] = item
    except Exception:
        print("⚠️ Could not load persisted calls, starting fresh.")
        traceback.print_exc()


def persist_calls():
    """Write calls dict to disk (simple persistence)."""
    try:
        with open(store_file, "w", encoding="utf-8") as f:
            json.dump(calls, f, indent=2, ensure_ascii=False)
    except Exception:
        print("⚠️ Failed to persist calls to disk.")
        traceback.print_exc()


def normalize_messages(raw_messages):
    """Return list of message dicts with at least a 'message' key."""
    msgs = []
    if raw_messages is None:
        return msgs

    if isinstance(raw_messages, str):
        msgs.append({"message": raw_messages})
    elif isinstance(raw_messages, dict):
        # sometimes single message object
        if "message" in raw_messages:
            msgs.append({"message": raw_messages.get("message")})
        else:
            # flatten values which might be text
            for v in raw_messages.values():
                if isinstance(v, (str, int, float)):
                    msgs.append({"message": str(v)})
    elif isinstance(raw_messages, list):
        for m in raw_messages:
            if isinstance(m, dict):
                if "message" in m:
                    msgs.append({"message": m.get("message")})
                else:
                    # try to string-ify the dict
                    msgs.append({"message": json.dumps(m)})
            else:
                msgs.append({"message": str(m)})
    else:
        msgs.append({"message": str(raw_messages)})

    return msgs


def extract_name_and_phone_from_text(text):
    """Return (name, phone) from a piece of text."""
    name = None
    phone = None

    # Normalize whitespace
    text = (text or "").strip()

    # PHONE: look for sequences that contain at least 7 digits (allow +, spaces, dashes, parens)
    phone_match = re.search(r'(\+?\d[\d\-\s\(\)]{6,}\d)', text)
    if phone_match:
        digits = re.sub(r'\D', '', phone_match.group(0))
        if len(digits) >= 7:
            phone = digits

    # NAME: look for 1-3 capitalized words (Handle things like "John", "John Doe", "Mary-Anne Smith")
    # We avoid all-caps words and common greetings.
    possible = re.findall(r"\b[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?\b", text)
    if possible:
        filtered = [n for n in possible if n.lower() not in
                    {"hi", "hello", "thanks", "thank", "good", "morning", "evening", "afternoon", "bye", "test", "ok", "okay"}]
        if filtered:
            # take up to 2 words to form name (first + last)
            name = " ".join(filtered[:2])

    return name, phone


@app.after_request
def add_cors_headers(response):
    # allow your dashboard to fetch /calls from a different origin if needed
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/vapi/callback", methods=["POST", "OPTIONS"])
def vapi_callback():
    if request.method == "OPTIONS":
        return ("", 204)

    try:
        # Robust JSON parsing: try flask's get_json, fallback to raw body
        data = request.get_json(silent=True)
        if data is None:
            raw = request.get_data(as_text=True)
            try:
                data = json.loads(raw) if raw else {}
            except Exception:
                # If payload isn't JSON, treat as text message
                data = {"messages": raw}

        # Debug log the raw payload (prints to Render logs)
        try:
            print("\n📩 RAW VAPI DATA:\n", json.dumps(data, indent=2))
        except Exception:
            print("📩 RAW VAPI DATA (non-serializable):", data)

        call_id = str(data.get("call_id", "unknown"))
        status = str(data.get("status", "")).lower()
        raw_messages = data.get("messages", [])

        # Normalize messages to list of {"message": "..."}
        messages = normalize_messages(raw_messages)

        name = None
        phone = None

        # Scan messages for name + phone (take first good values)
        for msg in messages:
            text = str(msg.get("message", "")).strip()
            if not text:
                continue

            n, p = extract_name_and_phone_from_text(text)
            if not name and n:
                name = n
            if not phone and p:
                phone = p

            if name and phone:
                break

        # Only save when call has ended (avoids partial updates), and avoid duplicate save
        if status == "ended":
            with lock:
                if call_id not in calls:
                    entry = {
                        "call_id": call_id,
                        "name": name or "Unknown",
                        "phone": phone or "Unknown",
                        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    calls[call_id] = entry
                    persist_calls()
                    print(f"✅ SAVED CALL: {entry}")
                else:
                    print(f"ℹ️ call_id {call_id} already stored; ignoring duplicate.")
        else:
            print(f"ℹ️ Received status='{status}' for call_id={call_id} — not saved yet.")

        return jsonify({"ok": True}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/calls", methods=["GET"])
def get_calls():
    # Return list of saved call entries (insertion order not guaranteed prior to Python 3.7)
    with lock:
        data = list(calls.values())
    return jsonify(data), 200


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Lexi webhook running fine!", "now_utc": datetime.utcnow().isoformat()}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # For local testing only. On Render use gunicorn in Procfile / service settings.
    app.run(host="0.0.0.0", port=port)






