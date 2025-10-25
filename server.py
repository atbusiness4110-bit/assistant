from flask import Flask, request, jsonify
from datetime import datetime
import re
import traceback

app = Flask(__name__)
calls = []  # temporary storage (replace with DB later)

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    try:
        data = request.json
        print("\n📨 Incoming JSON:", data)  # 🧠 log entire payload

        if not data:
            return jsonify({"error": "No data received"}), 400

        call_id = data.get("call_id", "unknown")
        messages = data.get("messages", [])
        name = None
        phone = None

        # 🧩 Analyze all messages to detect name & phone
        for msg in messages:
            text = msg.get("message", "").strip()
            lower = text.lower()
            print(f"🗣 Message fragment: {text}")

            # --- Detect possible name ---
            if any(keyword in lower for keyword in ["name", "i am", "i'm", "this is", "call me", "myself"]):
                possible_names = re.findall(r"\b[A-Z][a-z]+\b", text)
                if possible_names:
                    filtered = [n for n in possible_names if n.lower() not in 
                                ["hi", "hello", "thanks", "good", "morning", "evening", "afternoon"]]
                    if filtered:
                        name = " ".join(filtered[:2])
                        print(f"🧠 Detected name: {name}")

            # --- Detect phone numbers ---
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                phone = digits
                print(f"📞 Detected phone: {phone}")

        # 🧠 If nothing detected, mark as unknown
        entry = {
            "call_id": call_id,
            "name": name or "Unknown",
            "phone": phone or "Unknown",
            "status": data.get("status", "unknown"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        calls.append(entry)
        print(f"✅ Recorded call → {entry}")

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/calls", methods=["GET"])
def get_calls():
    """View all recorded calls."""
    return jsonify(calls)


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ Law Firm Caller API is running!"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)


