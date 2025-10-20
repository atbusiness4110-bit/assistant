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
    print("📞 Received call summary from Vapi:", data)
    calls.append(data)  # This appends to the shared list
    return jsonify({"status": "ok"})

@app.route('/calls', methods=['GET'])
def get_calls():
    return jsonify(calls)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
