from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback
import json
import os

app = Flask(__name__)

CALLS_FILE = "calls.json"

# Create calls.json if missing
if not os.path.exists(CALLS_FILE):
    with open(CALLS_FILE, "w") as f:
        json.dump([], f)


def extract_name_and_number(text):
    """Detects names and phone numbers from any text."""
    name = None
    phone = None

    # Normalize
    text = text.strip()

    # --- Phone number detection ---
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 7 and len(digits) <= 15:
        phone = digits

    # --- Name detection ---
    # Look for "I'm John", "This is Sarah Lee", etc.
    patterns = [
        r"(?:i am|i'm|this is|my name is|call me|name's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1).strip()
            # Filter out generic words that aren't names
            if candidate.lower() not in ["hi", "hello", "thanks", "yes", "no", "okay", "good", "morning", "afternoon", "evening"]:
                name = candidate
                break

    return name, phone


@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    try:
        data = request.json
        print("📨 Incoming call data received")

        # Handle both formats (plain JSON or nested under 'message')
        message_data = data.get("message", {})
        call_info = message_data.get("call", {})
        messages = message_data.get("conversation", [])

        # Some services send directly a messages list
        if not messages and "messages" in data:
            messages = data["messages"]

        call_id = call_info.get("id", data.get("call_id", "unknown"))
        status = (call_info.get("status") or data.get("status", "")).lower()

        name = None
        phone = None

        # Go through all messages in the conversation
        for msg in messages:
            text = msg.get("message", "").strip()
            if not text:
                continue

            found_name, found_phone = extract_name_and_number(text)

            if found_name and not name:
                name = found_name
            if found_phone and not phone:
                phone = found_phone

        # ✅ Only save when we have both
        if name and phone:
            entry = {
                "name": name,
                "phone": phone,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            with open(CALLS_FILE, "r") as f:
                calls = json.load(f)

            # Avoid duplicates (same number or same name)
            if not any(c["phone"] == phone or c["name"].lower() == name.lower() for c in calls):
                calls.append(entry)
                with open(CALLS_FILE, "w") as f:
                    json.dump(calls, f, indent=2)
                print(f"✅ SAVED CALL — Name: {name}, Phone: {phone}, Time: {entry['timestamp']}")
            else:
                print(f"⚠️ Duplicate detected for {name} ({phone}), skipping save.")
        else:
            print("⚙️ No complete name + number detected yet...")

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/calls", methods=["GET"])
def get_calls():
    try:
        with open(CALLS_FILE, "r") as f:
            calls = json.load(f)
        return jsonify(calls)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Law Firm Caller API is live and detecting names + numbers!"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)




