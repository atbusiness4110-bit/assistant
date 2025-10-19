# -*- coding: utf-8 -*-
"""
Created on Sun Oct 19 17:57:01 2025

@author: mthom
"""

from flask import Flask, request, jsonify

app = Flask(__name__)

# store the most recent summary
latest_summary = ""

@app.route('/')
def home():
    return "Lexi webhook running!"

@app.route('/summary', methods=['POST'])
def receive_summary():
    global latest_summary
    data = request.json
    summary = data.get("summary", "No summary received.")
    latest_summary = summary
    print("✅ Received summary:", summary)
    return jsonify({"message": "Summary received successfully!"}), 200

@app.route('/get_summary', methods=['GET'])
def get_summary():
    return jsonify({"summary": latest_summary})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)