from flask import Flask, request, jsonify
import json
from datetime import datetime
import os

app = Flask(__name__)

CALLS_FILE = "calls.json"

# Ensure calls.json exists
if not os.path.exists(CALLS_FILE):
    with open(CALLS_FILE, "w") as f:
        json.dump([], f)

@app.route("/")
def home():
    return "Caller Bot Webhook Active", 200

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    try:
        data = request.get_json()
        print("📨 Incoming JSON:", json.dumps(data, indent=2))

        # Extract key info safely
        call_id = data.get("message", {}).get("call", {}).get("id", "unknown")
        conversation = data.get("message", {}).get("conversation", [])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Initialize default
        caller_name = "Unknown"
        caller_phone = "Unknown"
        status = "unknown"

        # Try to extract from conversation messages
        for msg in conversation:
            if msg.get("role") == "user":
                user_text = msg.get("message", "")
                # Basic heuristics to detect name / phone
                if any(x in user_text.lower() for x in ["name", "i am", "this is", "my name"]):
                    caller_name = user_text
                elif any(c.isdigit() for c in user_text) and len(user_text) >= 7:
                    caller_phone = user_text
            elif msg.get("role") == "bot" and "thank you" in msg.get("message", "").lower():
                status = "complete"

        # Build new record
        new_call = {
            "call_id": call_id,
            "name": caller_name,
            "phone": caller_phone,
            "status": status,
            "timestamp": timestamp
        }

        # Load existing calls
        with open(CALLS_FILE, "r") as f:
            calls = json.load(f)

        calls.append(new_call)

        # Save updated calls
        with open(CALLS_FILE, "w") as f:
            json.dump(calls, f, indent=2)

        print("✅ Saved call info:", new_call)
        return jsonify({"success": True, "saved": new_call}), 200

    except Exception as e:
        print("❌ Error handling callback:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

