import os, json, re, threading, logging, sys
from datetime import datetime
from flask import Flask, request, jsonify

# Logging setup
logging.basicConfig(stream=sys.stdout, level=logging.INFO, force=True)
print = lambda *a, **kw: logging.info(" ".join(map(str, a)))

# Flask setup
app = Flask(__name__)

CALLS_FILE = "calls.json"
SETTINGS_FILE = "settings.json"

# Data stores
calls = []
settings = {
    "bot_active": True,
    "active_start": "00:00",
    "active_end": "23:59",
}

lock = threading.Lock()

def load_data():
    global calls, settings
    try:
        with lock:
            if os.path.exists(CALLS_FILE):
                with open(CALLS_FILE, "r") as f:
                    calls[:] = json.load(f)
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    settings.update(json.load(f))
    except Exception as e:
        print("⚠️ Error loading data:", e)

def save_data():
    try:
        with lock:
            with open(CALLS_FILE, "w") as f:
                json.dump(calls, f, indent=2)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
    except Exception as e:
        print("⚠️ Error saving data:", e)

# --- Routes ---
@app.route("/")
def home():
    return "✅ Lexi Call Agent Server running!"

@app.route("/calls")
def get_calls():
    return jsonify(calls)

@app.route("/delete", methods=["POST"])
def delete_calls():
    to_delete = request.get_json(force=True)
    global calls
    with lock:
        calls = [
            c for c in calls
            if not (c["name"] == to_delete["name"] and c["phone"] == to_delete["phone"])
        ]
    save_data()
    return jsonify({"ok": True})

@app.route("/status")
def status():
    return jsonify({
        "bot_active": settings["bot_active"],
        "active_start": settings["active_start"],
        "active_end": settings["active_end"],
        "within_hours": within_active_hours(),
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

@app.route("/toggle", methods=["POST"])
def toggle_bot():
    settings["bot_active"] = not settings["bot_active"]
    save_data()
    return jsonify({"bot_active": settings["bot_active"]})

@app.route("/set-time-range", methods=["POST"])
def set_time_range():
    data = request.get_json(force=True)
    settings["active_start"] = data.get("start", "00:00")
    settings["active_end"] = data.get("end", "23:59")
    save_data()
    return jsonify({"ok": True, "settings": settings})

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    data = request.get_json(force=True)
    msg = data.get("message", {})

    # Only process end-of-call events
    if msg.get("type") != "end-of-call-report":
        return jsonify({"ignored": msg.get("type")}), 200

    # Check if bot is active
    if not settings["bot_active"] or not within_active_hours():
        print("⏸ Ignored call (bot inactive or outside time range).")
        return jsonify({"ok": False, "reason": "inactive"}), 200

    # Extract caller info
    summary = msg.get("analysis", {}).get("summary", "")
    name, phone = "Unknown", "Unknown"

    names = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", summary)
    if names:
        name = names[0]

    digits = re.sub(r"\D", "", summary)
    if len(digits) >= 7:
        phone = digits[-10:]

    # Save call
    with lock:
        calls.append({
            "name": name,
            "phone": phone,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_data()

    print(f"✅ Saved call: {name}, {phone}")
    return jsonify({"ok": True})

# --- Run Server ---
if __name__ == "__main__":
    load_data()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)










