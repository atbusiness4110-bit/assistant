from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

calls = []  # List to store final call summaries only

@app.route('/vapi/callback', methods=['POST'])
def vapi_callback():
    try:
        data = request.get_json()

        # Handle array or single payload from Vapi
        entries = data if isinstance(data, list) else [data]

        final_entries = [
            e for e in entries if e.get("ended_reason")  # Only when call is ended
        ]

        if not final_entries:
            print("⏳ Ignoring mid-call update...")
            return jsonify({"message": "Ignored mid-call update"}), 200

        latest = final_entries[-1]

        call_id = latest.get("call_id", "Unknown")
        assistant = latest.get("assistant", "Unknown")
        summary = latest.get("summary", "No summary available")

        print(f"📞 Final summary from {assistant} ({call_id}): {summary}")

        # For now, fill placeholders for name/phone until we parse them
        calls.append({
            "name": "Unknown",
            "phone": "Unknown",
            "reason": summary,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        return jsonify({"message": "Final summary saved"}), 200

    except Exception as e:
        print(f"⚠️ Error parsing callback: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/calls', methods=['GET'])
def get_calls():
    return jsonify(calls), 200


@app.route('/')
def home():
    return jsonify({"message": "✅ Law Firm API is running!"})

