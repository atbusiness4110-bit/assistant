from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback
import json

app = Flask(__name__)

calls = {}  # store by call_id (1 per call)


@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    try:
        data = request.get_json(force=True, silent=True)
        print("📨 RAW CALLBACK DATA:", json.dumps(data, indent=2))

        if not data:
            return jsonify({"error": "no data"}), 400

        # Pull fields safely
        call_id = str(data.get("call_id", data.get("id", "unknown")))
        messages = data.get("messages") or data.get("conversation", {}).get("messages", [])
        status = data.get("status", data.get("event", "")).lower()

        name = None
        phone = None

        # Extract info from messages
        for msg in messages:
            # Message text might be stored differently
            text = str(
                msg.get("message")
                or msg.get("text")
                or msg.get("content")
                or ""
            ).strip()
            if not text:
                continue

            # Find names (capitalized words, skip greetings)
            possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
            if possible_names:
                filtered = [
                    n for n in possible_names
                    if n.lower() not in [
                        "hi", "hello", "hey", "good", "morning",
                        "afternoon", "evening", "thanks", "bye"
                    ]
                ]
                if filtered:
                    name = " ".join(filtered[:2])

            # Find phone numbers
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits

        # Save final entry only once per call
        if ("ended" in status or "completed" in status or "call.ended" in status) and call_id not in calls:
            entry = {
                "call_id": call_id,
                "name": name or "Unknown",
                "phone": phone or "Unknown",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            calls[call_id] = entry
            print(f"✅ SAVED CALL — {entry}")
        else:
            print(f"ℹ️ Update ignored (status={status})")

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/calls", methods=["GET"])
def get_calls():
    """Your .exe can call this endpoint to fetch all saved calls."""
    return jsonify(list(calls.values())), 200


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Law Firm API is running!"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)




