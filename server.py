from flask import Flask, request, jsonify
from datetime import datetime
import re

# ---------------------------
# Flask App Initialization
# ---------------------------
app = Flask(__name__)

# Store call summaries in memory
calls = []

# ---------------------------
# ROUTE 1: Root (health check)
# ---------------------------
@app.route('/')
def home():
    return jsonify({"message": "✅ Law Firm API is running!"}), 200


# ---------------------------
# ROUTE 2: Retrieve call records
# ---------------------------
@app.route('/calls', methods=['GET'])
def get_calls():
    """
    Returns all recorded calls (name, phone, timestamp)
    """
    return jsonify(calls), 200


# ---------------------------
# ROUTE 3: Receive Vapi Webhook
# ---------------------------
@app.route('/vapi/callback', methods=['POST'])
def vapi_callback():
    """
    Receives webhook data from Vapi and records caller info
    ONLY after the call has fully ended.
    """
    try:
        data = request.get_json()
        print("📩 Received webhook payload:", data)

        entries = data if isinstance(data, list) else [data]

        for entry in entries:
            msg = entry.get("message", {})
            status = msg.get("status")
            ended_reason = msg.get("endedReason")

            # Only record once call has ended
            if status == "ended" or ended_reason:
                print("✅ Call end detected")

                # --- Extract message data ---
                summary_text = entry.get("summary", "")
                artifact = msg.get("artifact", {})
                messages = artifact.get("messages", [])

                extracted_name = None
                extracted_phone = None

                # Combine all text content
                all_text = " ".join(
                    m.get("message", "") for m in messages
                ) + " " + summary_text
                all_text = re.sub(r"\s+", " ", all_text).strip()

                # ---------------------------
                # 1️⃣ Extract Name
                # ---------------------------
                name_match = re.search(
                    r"(?:my name is|this is|i am)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)",
                    all_text, re.I
                )
                if name_match:
                    extracted_name = name_match.group(1).strip()

                # ---------------------------
                # 2️⃣ Extract Phone Number
                # ---------------------------
                phone_match = re.search(
                    r"(\+?\d[\d\s\-]{6,})", all_text
                )
                if phone_match:
                    extracted_phone = re.sub(r"[^\d\+]", "", phone_match.group(1))

                # ---------------------------
                # 3️⃣ Fallback: Try from summary
                # ---------------------------
                if not extracted_name or not extracted_phone:
                    if summary_text:
                        print("🧾 SUMMARY TEXT:", summary_text)

                        if not extracted_name:
                            m = re.search(
                                r"(?:name\s*[:\-]?\s*)([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
                                summary_text, re.I
                            )
                            if m:
                                extracted_name = m.group(1)

                        if not extracted_phone:
                            m = re.search(
                                r"(?:phone|number)\s*[:\-]?\s*(\+?\d[\d\s\-]{7,})",
                                summary_text, re.I
                            )
                            if m:
                                extracted_phone = re.sub(r"[^\d\+]", "", m.group(1))

                # ---------------------------
                # 4️⃣ Defaults if missing
                # ---------------------------
                name = extracted_name or "Unknown"
                phone = extracted_phone or "Unknown"

                # ---------------------------
                # 5️⃣ Add timestamp
                # ---------------------------
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

                call_record = {
                    "name": name,
                    "phone": phone,
                    "time": timestamp
                }
                calls.append(call_record)

                # ---------------------------
                # 6️⃣ Log to Render console
                # ---------------------------
                print(f"📞 FINAL CALL — Name: {name}, Phone: {phone}, Time: {timestamp}")
                print("-" * 60)

                return jsonify({"message": "Final call recorded"}), 200

        # Ignore interim messages
        print("⏳ Ignored non-final webhook event.")
        return jsonify({"message": "Ignored non-final webhook"}), 200

    except Exception as e:
        print(f"⚠️ Error parsing callback: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------
# Local Development Entry Point
# ---------------------------
if __name__ == '__main__':
    # For local testing
    app.run(host='0.0.0.0', port=10000)

