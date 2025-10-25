from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback
import json

app = Flask(__name__)
calls = {}

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    try:
        # Get data safely (works even if Vapi sends weird content)
        try:
            data = request.get_json(force=True)
        except:
            data = json.loads(request.data.decode("utf-8"))

        print("\n📩 RAW VAPI DATA:\n", json.dumps(data, indent=2))

        call_id = str(data.get("call_id", "unknown"))
        status = str(data.get("status", "")).lower()
        messages = data.get("messages", [])

        # fallback — sometimes Vapi sends message as string not list
        if isinstance(messages, str):
            messages = [{"message": messages}]

        name = None
        phone = None

        # Loop through messages and find name + phone
        for msg in messages:
            text = str(msg.get("message", "")).strip()
            if not text:
                continue

            # Try to detect name (capitalized words)
            possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
            if possible_names:
                filtered = [n for n in possible_names if n.lower() not in
                            ["hi", "hello", "thanks", "good", "morning", "evening", "afternoon", "bye", "test"]]
                if filtered:
                    name = " ".join(filtered[:2])

            # Detect phone number
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits

        # Save only one entry per call_id (when ended)
        if status == "ended" and call_id not in calls:
            entry = {
                "call_id": call_id,
                "name": name or "Unknown",
                "phone": phone or "Unknown",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            calls[call_id] = entry
            print(f"✅ SAVED CALL: {entry}")
        else:
            print(f"ℹ️ Update ignored (status={status})")

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/calls", methods=["GET"])
def get_calls():
    return jsonify(list(calls.values())), 200

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Lexi webhook running fine!"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)





