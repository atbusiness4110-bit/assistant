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

            # Detect possible name statements (many variations)
            if any(keyword in lower for keyword in ["name", "i am", "i'm", "this is", "call me", "myself"]):
                # Extract capitalized word(s) that look like names
                possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
                if possible_names:
                    # Avoid common words that aren't names
                    filtered = [n for n in possible_names if n.lower() not in ["hi", "hello", "thanks", "good", "morning", "evening", "afternoon"]]
                    if filtered:
                        name = " ".join(filtered[:2])  # Support first + last name
                        print(f"[🧠 Detected name: {name}]")

            # Detect possible phone numbers (extract digits)
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits

        # Record only at the end of the call
        if data.get("status", "").lower() == "ended":
            entry = {
                "name": name or "Unknown",
                "phone": phone or "Unknown",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            print(f"📞 FINAL CALL — Name: {entry['name']}, Phone: {entry['phone']}")
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
