from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Define the list outside the route so it persists while the server runs
calls = []

@app.route('/')
def home():
    return jsonify({"message": "✅ Law Firm API is running!"})

@app.route('/vapi/callback', methods=['POST'])
def vapi_callback():
    data = request.get_json()
    print("📞 Full payload received from Vapi:", data)  # Keep full log for debugging

    # Safely parse nested fields
    message = data.get("message", {})
    call_info = message.get("call", {})
    assistant_info = message.get("assistant", {})
    artifact = message.get("artifact", {})
    messages = artifact.get("messages", [])

    # Extract a short human summary
    summary_text = ""
    for msg in messages:
        if msg.get("role") == "bot":
            summary_text += msg.get("message", "") + " "

    # Build the clean record
    call_entry = {
        "call_id": call_info.get("id"),
        "assistant": assistant_info.get("name"),
        "ended_reason": message.get("endedReason"),
        "timestamp": message.get("timestamp"),
        "summary": summary_text.strip() or "No summary available"
    }

    calls.append(call_entry)
    return jsonify({"status": "ok"})

@app.route('/calls', methods=['GET'])
def get_calls():
    return jsonify(calls)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
