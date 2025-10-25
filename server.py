from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback

app = Flask(__name__)
calls = []  # Store calls temporarily; can be replaced with a DB later


@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    data = request.json
    try:
        call_id = data.get("call_id", "unknown")
        messages = data.get("messages", [])
        name = None
        phone = None

        # Loop through all messages and intelligently detect name + phone
        for msg in messages:
            text = msg.get("message", "").strip()
            lower = text.lower()

            # Detect possible name statements
            if any(keyword in lower for keyword in ["name", "i am", "i'm", "this is", "call me", "myself"]):
                possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
                if possible_names:
                    filtered = [n for n in possible_names if n.lower() not in ["hi", "hello", "thanks", "good", "morning", "evening", "afternoon"]]
                    if filtered:
                        name = " ".join(filtered[:2])
                        print(f"[🧠 Detected name: {name}]")

            # Detect possible phone numbers
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits

        # ✅ Record the call every time (not just on "ended")
        entry = {
            "name": name or "Unknown",
            "phone": phone or "Unknown",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": data.get("status", "unknown")
        }

        print(f"📞 Recorded call — Name: {entry['name']}, Phone: {entry['phone']}, Status: {entry['status']}")
        calls.append(entry)

        return jsonify({"ok": True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/calls", methods=["GET"])
def get_calls():
    return jsonify(calls)


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Law Firm API is running!"})

