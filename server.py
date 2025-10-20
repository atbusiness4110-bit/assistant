from flask import Flask, request, jsonify

app = Flask(__name__)

# simple in-memory database
CALL_LOGS = []

@app.route('/calls', methods=['GET'])
def get_calls():
    return jsonify(CALL_LOGS)

@app.route('/vapi/callback', methods=['POST'])
def vapi_callback():
    data = request.get_json()
    if data:
        CALL_LOGS.append({
            "caller_name": data.get("caller", {}).get("name", "Unknown"),
            "phone": data.get("caller", {}).get("number", "Unknown"),
            "request": data.get("request", "Unknown"),
            "time": data.get("timestamp", "Unknown")
        })
        print(f"✅ Received call summary from Vapi: {data}")
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
