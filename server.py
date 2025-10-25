from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback
import json

app = Flask(__name__)

calls = {}  # Use dict so each call_id is recorded once


@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    try:
        # Read and log everything from Vapi
        data = request.get_json(force=True, silent=True)
        print("📨 RAW CALLBACK DATA:\n", json.dumps(data, indent=2))

        if not data:
            print("⚠️ No JSON data received from Vapi.")
            return jsonify({"error": "No data"}), 400

        call_id = str(data.get("call_id", "unknown"))
        messages = data.get("messages", [])
        status = data.get("status", "").lower()

        name = None
        phone = None

        # Analyze all messages (Vapi sends a full conversation log)
        for msg in messages:
            text = str(msg.get("message", "")).strip()
            if not text:
                continue

            # 🔍 Detect any capitalized word as a name (ignore greetings)
            possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
            if possible_names:
                filtered = [
                    n for n in possible_names
                    if n.lower() not in ["hi", "hello", "thanks", "good", "morning", "evening", "afternoon", "bye"]
                ]
                if filtered:
                    name = " ".join(filtered[:2])

            # 🔢 Detect phone number anywhere in message
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits

        # Only save when call ends
        if status == "ended" and call_id not in calls:
            entry = {
                "call_id": call_id,
                "name": name or "Unknown",
                "phone": phone or "Unknown",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            calls[call_id] = entry
            print(f"✅ SAVED CALL — {entry}")

        else:
            print(f"ℹ️ Ignored call update (status={status})")

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/calls", methods=["GET"])
def get_calls():
    """View all recorded calls"""
    return jsonify(list(calls.values())), 200


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Law Firm API is running!"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)



