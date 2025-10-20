from flask import Flask, request, jsonify
from datetime import datetime
import re

app = Flask(__name__)
calls = []

@app.route('/vapi/callback', methods=['POST'])
def vapi_callback():
    try:
        data = request.get_json()
        print("📩 Received webhook:", data)

        # Vapi sends nested message data — handle both array and single dict
        entries = data if isinstance(data, list) else [data]

        for entry in entries:
            msg = entry.get("message", {})
            status = msg.get("status")
            ended_reason = msg.get("endedReason")

            # Trigger only when call has ended
            if status == "ended" or ended_reason:
                print("✅ Call ended detected")

                # Extract potential text summary or artifact data
                summary_text = entry.get("summary", "")
                artifact = msg.get("artifact", {})
                messages = artifact.get("messages", [])

                # Sometimes summary is in last bot message
                if not summary_text and messages:
                    for m in reversed(messages):
                        if m.get("role") == "bot":
                            summary_text = m.get("message", "")
                            break

                # Extract name and phone
                name_match = re.search(r"(?:Mr\.|Mrs\.|Ms\.|Mister)?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", summary_text)
                phone_match = re.search(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b", summary_text)

                name = name_match.group(1) if name_match else "Unknown"
                phone = phone_match.group(0) if phone_match else "Unknown"

                calls.append({
                    "name": name,
                    "phone": phone,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

                print(f"📞 FINAL CALL — Name: {name}, Phone: {phone}")
                return jsonify({"message": "Final call recorded"}), 200

        print("⏳ Ignored non-final webhook")
        return jsonify({"message": "Ignored non-final webhook"}), 200

    except Exception as e:
        print(f"⚠️ Error parsing callback: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/calls', methods=['GET'])
def get_calls():
    return jsonify(calls), 200


@app.route('/')
def home():
    return jsonify({"message": "✅ Law Firm API is running!"})



