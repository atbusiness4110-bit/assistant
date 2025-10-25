from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback
import json

app = Flask(__name__)
calls = {}  # Stores one entry per call_id


@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    """Receives call data from Vapi and extracts name + phone number."""
    try:
        data = request.get_json(force=True, silent=True)

        # Log everything coming from Vapi
        print("📨 RAW DATA RECEIVED FROM VAPI:\n", json.dumps(data, indent=2))

        if not data:
            print("⚠️ No JSON received from Vapi!")
            return jsonify({"error": "No data received"}), 400

        # --- Extract core info ---
        call_id = str(data.get("call_id") or data.get("id") or "unknown")
        messages = data.get("messages", [])
        status = str(data.get("status", "")).lower()

        name = None
        phone = None

        # --- Analyze all message text ---
        for msg in messages:
            text = str(msg.get("message") or msg.get("text") or "").strip()
            if not text:
                continue

            # Detect possible names (any capitalized words, ignore greetings)
            possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
            if possible_names:
                filtered = [
                    n for n in possible_names
                    if n.lower() not in ["hi", "hello", "thanks", "good", "morning", "evening", "afternoon", "bye"]
                ]
                if filtered:
                    name = " ".join(filtered[:2])

            # Detect possible phone numbers (digits only)
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits

        # --- Save once when call ends ---
        if status == "ended" and call_id not in calls:
            entry = {
                "call_id": call_id,
                "name": name or "Unknown",
                "phone": phone or "Unknown",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            calls[call_id] = entry
            print(f"✅ SAVED FINAL CALL: {entry}")
        else:
            print(f"ℹ️ Ignored interim update (status={status})")

        return jsonify({"ok": True}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/calls", methods=["GET"])
def get_calls():
    """View all recorded calls."""
    return jsonify(list(calls.values())), 200


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Law Firm API is running and waiting for Vapi data."}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)






