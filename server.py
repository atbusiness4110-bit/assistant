from flask import Flask, request, jsonify
from datetime import datetime
import re
import json
import traceback

app = Flask(__name__)
calls = {}

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    print("\n🔥 VAPI CALLBACK RECEIVED 🔥")

    try:
        # Parse JSON safely (handles plain string bodies too)
        try:
            data = request.get_json(force=True)
        except Exception:
            data = json.loads(request.data.decode("utf-8"))

        # Handle if data itself is a stringified JSON
        if isinstance(data, str):
            data = json.loads(data)

        print("\n📩 RAW VAPI DATA (truncated):\n", json.dumps(data, indent=2)[:1000])

        call_id = str(data.get("call_id", data.get("id", "unknown")))
        status = str(data.get("status", data.get("call_status", ""))).lower()

        # ✅ Detect messages in any shape
        messages = []
        if "messages" in data:
            messages = data["messages"]
        elif "messagesOpenAIFormatted" in data:
            messages = data["messagesOpenAIFormatted"]
        elif isinstance(data, list):
            messages = data
        elif "message" in data:
            messages = [data]

        name = None
        phone = None

        # Loop through every message we can find
        for msg in messages:
            # Each message may be dict or string
            text = ""
            if isinstance(msg, dict):
                text = msg.get("message") or msg.get("content") or ""
            elif isinstance(msg, str):
                text = msg
            text = str(text).strip()

            if not text:
                continue

            # Find capitalized names (skip generic words)
            possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
            if possible_names:
                filtered = [
                    n for n in possible_names
                    if n.lower() not in ["hi", "hello", "thanks", "good", "morning", "evening",
                                         "afternoon", "bye", "test", "you", "please", "attorney"]
                ]
                if filtered and not name:
                    name = " ".join(filtered[:2])

            # Find any 7+ digit number for phone
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits

        # ✅ Save only when the call ends
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
            print(f"ℹ️ Update ignored (status={status}, call_id={call_id})")

        return jsonify({"ok": True}), 200

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




