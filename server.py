from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback
import json
import os

app = Flask(__name__)

CALLS_FILE = "calls.json"

# Ensure file exists
if not os.path.exists(CALLS_FILE):
    with open(CALLS_FILE, "w") as f:
        json.dump([], f)

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    data = request.json
    try:
        print("📨 Incoming JSON received")
        # Sometimes the Vapi webhook wraps data inside 'message'
        message_data = data.get("message", {})
        call_info = message_data.get("call", {})

        call_id = call_info.get("id", "unknown")
        messages = message_data.get("conversation", [])
        status = call_info.get("status", "").lower()

        name = None
        phone = None

        # Parse through messages
        for msg in messages:
            text = msg.get("message", "").strip()
            lower = text.lower()

            # Detect possible names
            if any(keyword in lower for keyword in ["name", "i am", "i'm", "this is", "call me", "myself"]):
                possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
                filtered = [n for n in possible_names if n.lower() not in ["hi", "hello", "thanks", "good", "morning", "evening", "afternoon"]]
                if filtered:
                    name = " ".join(filtered[:2])
                    print(f"[🧠 Detected name: {name}]")

            # Detect possible phone numbers
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits
                print(f"[📞 Detected phone: {phone}]")

        # Record only at the end of the call
        if status in ["ended", "completed", "done", "queued"] or len(messages) > 5:
            entry = {
                "call_id": call_id,
                "name": name or "Unknown",
                "phone": phone or "Unknown",
                "status": status or "completed",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # Load, append, save
            with open(CALLS_FILE, "r") as f:
                calls = json.load(f)
            calls.append(entry)
            with open(CALLS_FILE, "w") as f:
                json.dump(calls, f, indent=2)

            print(f"✅ SAVED CALL — {entry}")
        else:
            print("🕓 Call still in progress — not saved yet")

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/calls", methods=["GET"])
def get_calls():
    with open(CALLS_FILE, "r") as f:
        calls = json.load(f)
    return jsonify(calls)


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Law Firm API is running!"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)



