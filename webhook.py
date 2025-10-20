# webhook.py
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Change this later to your desktop app's local address
DESKTOP_APP_URL = "http://localhost:5001/update"

@app.route('/')
def home():
    return "✅ Lexi Webhook Server is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("📞 Received data from Vapi:", data)

    # Forward the summary to the desktop app
    try:
        requests.post(DESKTOP_APP_URL, json=data)
        print("✅ Forwarded to desktop app")
    except Exception as e:
        print("⚠️ Failed to reach desktop app:", e)

    return jsonify({"status": "received"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
