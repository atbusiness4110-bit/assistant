# -*- coding: utf-8 -*-
"""
Created on Sun Oct 19 17:41:26 2025

@author: mthom
"""

from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

DESKTOP_APP_URL = "http://174.2.85.11"  # change this below

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    print("📞 Received call data from Vapi:", data, flush=True)

    try:
        requests.post(DESKTOP_APP_URL, json=data)
        print("✅ Forwarded to desktop app", flush=True)
    except Exception as e:
        print("⚠️ Could not forward to desktop app:", e, flush=True)

    return jsonify({"status": "success"}), 200