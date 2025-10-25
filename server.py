import os
import sys
import time
import json
import logging
import threading
import re
import traceback
from datetime import datetime
from flask import Flask, request, jsonify

# === CONFIGURE LOGGING (for Render logs) ===
logging.basicConfig(stream=sys.stdout, level=logging.INFO, force=True)
print = lambda *args, **kwargs: logging.info(" ".join(map(str, args)))

# === GLOBAL MEMORY ===
calls = {}
last_action = "Idle"
last_update_time = "Never"

# === FLASK APP ===
app = Flask(__name__)

# === HOME ROUTE ===
@app.route("/")
def home():
    return "✅ Lexi Vapi Callback Server is running on Render!"

@app.route("/health")
def health():
    return "OK", 200

# === STATUS ROUTE (for external monitoring / .exe dashboard) ===
@app.route("/status")
def status():
    return jsonify({
        "status": "running",
        "last_action": last_action,
        "last_update": last_update_time,
        "total_calls": len(calls)
    })

# === GET ALL CALLS (for dashboard UI or testing) ===
@app.route("/calls")
def get_calls():
    return jsonify(list(calls.values()))

# === VAPI CALLBACK ===
@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    global last_action, last_update_time
    print("\n🔥 VAPI CALLBACK RECEIVED 🔥")

    try:
        data = request.get_json(force=True)
        print("\n📩 RAW VAPI DATA (truncated):\n", json.dumps(data, indent=2)[:1000])

        message = data.get("message", {})
        msg_type = message.get("type", "").lower()
        timestamp = message.get("timestamp", datetime.now().timestamp())
        call_id = str(timestamp)

        # Initialize data
        name = None
        phone = None
        summary = None

        # Extract from analysis.summary if available
        analysis = message.get("analysis", {})
        if "summary" in analysis:
            summary = analysis["summary"]
            print("📄 Summary found:", summary)

            # Extract name
            possible_names = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", summary)
            if possible_names:
                name = possible_names[0]

            # Extract phone
            digits = re.sub(r"\D", "", summary)
            if len(digits) >= 7:
                phone = digits[-10:]  # last 10 digits

        # Fallback: search in artifact.messages
        if not name or not phone:
            artifact = message.get("artifact", {})
            msgs = artifact.get("messages", [])
            for msg in msgs:
                text = str(msg.get("message", "")) or str(msg.get("content", ""))
                if not text:
                    continue

                if not phone:
                    digits = re.sub(r"\D", "", text)
                    if len(digits) >= 7:
                        phone = digits[-10:]

                if not name:
                    poss = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", text)
                    if poss:
                        name = poss[0]

        # Only record completed calls (end-of-call-report)
        if msg_type == "end-of-call-report":
            entry = {
                "call_id": call_id,
                "name": name or "Unknown",
                "phone": phone or "Unknown",
                "summary": summary or "(No summary)",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            calls[call_id] = entry
            print("✅ CALL SAVED:", entry)
            last_action = f"Saved call for {entry['name']}"
            last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            print(f"ℹ️ Skipped message (type={msg_type})")

        return jsonify({"ok": True}), 200

    except Exception as e:
        print("❌ Error handling callback:", e)
        traceback.print_exc()
        last_action = f"Error: {e}"
        return jsonify({"error": str(e)}), 500

# === AUTO LOOP: Keep app active and simulate periodic health check ===
def keep_alive_loop():
    global last_action
    print("🕓 Background monitor started (every 60 seconds)")
    while True:
        try:
            print("✅ Server still alive — total calls:", len(calls))
            last_action = "Monitoring health"
        except Exception as e:
            print("⚠️ Monitor error:", e)
        time.sleep(60)

# === START SERVER ===
if __name__ == "__main__":
    # Run Flask in a background thread (like your email bot)
    def run_flask():
        port = int(os.environ.get("PORT", 5000))
        print(f"🚀 Starting Flask server on port {port}")
        app.run(host="0.0.0.0", port=port)

    threading.Thread(target=run_flask, daemon=True).start()

    # Start background monitor loop
    keep_alive_loop()






