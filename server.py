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
    return jsonify({"message": "✅ Law Firm API is running!"})

# ---------------------------
# ROUTE 2: Retrieve call records
# ---------------------------
@app.route('/calls', methods=['GET'])
def get_calls():
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

        # Vapi can send a dict or list of messages
        entries = data if isinstance(data, list) else [data]

        for entry in entries:
            msg = entry.get("message", {})
            status = msg.get("status")
            ended_reason = msg.get("endedReason")

            # Only process once call is marked as ended
            if status == "ended" or ended_reason:
                print("✅ Call ended detected")

                # Try to pull relevant text data
                summary_text = entry.get("summary", "")
                artifact = msg.get("artifact", {})
                messages = artifact.get("messages", [])

                # ---------------------------
                # 1️⃣ Extract name & phone from messages
                # ---------------------------
                extracted_name = None
                extracted_phone = None

                # Combine all text from the call
                all_text = " ".join(
                    m.get("message", "") for m in messages
                ) + " " + summary_text

                # --- Clean up whitespace ---
                all_text = re.sub(r"\s+", " ", all_text).strip()

                # --- Try to extract name ---
                # Handles: "My name is Sarah Jacobs" or "This is John"
                name_match = re.search(
                    r"(?:my name is|this is|i am)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)",
                    all_text,
                    re.I
                )
                if name_match:
                    extracted_name = name_match.group(1).strip()

                # --- Try to extract phone ---
                # Handles formats like:
                # "4037757197", "403 775 7197", "+1 403-775-7197"
                phone_match = re.search(
                    r"(\+?\d[\d\s\-]{6,})",
                    all_text
                )
                if phone_match:
                    # Clean spaces and dashes
                    extracted_phone = re.sub(r"[^\d\+]", "", phone_match.group(1))


                # ---------------------------
                # 2️⃣ Fallback: Extract from summary text
                # ---------------------------
                if not extracted_name or not extracted_phone:
                    summary_text = summary_text or ""
                    print("🧾 SUMMARY TEXT CANDIDATE:", summary_text)

                    if not extracted_name:
                        match = re.search(r"(?:name\s*[:\-]?\s*)([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", summary_text, re.I)
                        if match:
                            extracted_name = match.group(1)

                    if not extracted_phone:
                        match = re.search(r"(?:phone|number)\s*[:\-]?\s*(\+?\d[\d\s\-]{7,})", summary_text, re.I)
                        if match:
                            extracted_phone = match.group(1)

                # ---------------------------
                # 3️⃣ Default if missing
                # ---------------------------
                name = extracted_name or "Unknown"
                phone = extracted_phone or "Unknown"

                # ---------------------------
                # 4️⃣ Save the record
                # ---------------------------
                call_record = {
                    "name": name,
                    "phone": phone,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                calls.append(call_record)

                # ---------------------------
                # 5️⃣ Log for Render visibility
                # ---------------------------
                print(f"📞 FINAL CALL — Name: {name}, Phone: {phone}")
                print(f"🕒 Timestamp: {call_record['time']}")
                print("-" * 50)

                return jsonify({"message": "Final call recorded"}), 200

        # If not ended, ignore
        print("⏳ Ignored non-final webhook event.")
        return jsonify({"message": "Ignored non-final webhook"}), 200

    except Exception as e:
        print(f"⚠️ Error parsing callback: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------
# Local development run mode
# ---------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)






