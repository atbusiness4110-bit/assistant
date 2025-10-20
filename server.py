from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Define the list outside the route so it persists while the server runs
calls = []

@app.route('/')
def home():
    return jsonify({"message": "✅ Law Firm API is running!"})

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "no data"}), 400

    try:
        # Handle array payloads or single message
        if isinstance(data, list):
            # Only take the last summary where the call has ended
            final_summaries = [item for item in data if item.get("ended_reason")]
            if final_summaries:
                latest = final_summaries[-1]
            else:
                latest = data[-1]
        else:
            latest = data

        summary_text = latest.get("summary", "No summary provided")
        call_id = latest.get("call_id", "Unknown")
        assistant_name = latest.get("assistant", "Unknown")

        # Log cleanly
        print(f"📞 Final summary from {assistant_name} ({call_id}): {summary_text}")

        # Store or serve minimal data to frontend
        summaries.append({
            "assistant": assistant_name,
            "call_id": call_id,
            "summary": summary_text,
            "timestamp": latest.get("timestamp")
        })

        return jsonify({"status": "ok", "received": summary_text})

    except Exception as e:
        print("⚠️ Error parsing callback:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/calls', methods=['GET'])
def get_calls():
    return jsonify(calls)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
