# -*- coding: utf-8 -*-
"""
Created on Sun Oct 19 17:41:26 2025

@author: mthom
"""

from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "✅ Lexi Webhook is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    print("📞 Received call data from Vapi:", data)
    
    # For now, just confirm receipt
    return jsonify({"status": "success", "message": "Webhook received!"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)