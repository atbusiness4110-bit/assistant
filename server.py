from flask import Flask, request, jsonify
from datetime import datetime
import re

app = Flask(__name__)

calls = []  # Only store final call summaries


@app.route('/vapi/callback', methods=['POST'])
def vapi_callback():
    try:
        data = request.get_json()
        entries = data if isinstance(data, list) else [data]

        # Only process at end of call
        final_entries = [e for e in entries if e.get("ended_reason")]
        if not final_entries:
            print("⏳ Ignoring in-progress summaries...")
            return jsonify({"message": "Ignored mid-call update"}), 200

        latest = final_entries[-1]
        summary = latest.get("summary", "")

        # Try to extract name and phone
        name_match = re.search(r"(?:Mr\.|Mrs\.|Ms\.|Mister)?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", summary)
        phone_match = re.search(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b", summary)

        name = name_match.group(1) if name_match else "Unknown"
        phone = phone_match.group(0) if phone_match else "Unknown"

        print(f"📞 FINAL CALL — Name: {name}, Phone: {phone}")

        calls.append({
            "name": name,
            "phone": phone,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        return jsonify({"message": "Final call data stored"}), 200

    except Exception as e:
        print(f"⚠️ Error parsing callback: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/calls', methods=['GET'])
def get_calls():
    return jsonify(calls), 200


@app.route('/')
def home():
    return jsonify({"message": "✅ Law Firm API is running!"})

