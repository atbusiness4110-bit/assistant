import os, json, re, threading, logging, sys
from datetime import datetime
from flask import Flask, request, jsonify

# --- Logging setup ---
logging.basicConfig(stream=sys.stdout, level=logging.INFO, force=True)
print = lambda *a, **kw: logging.info(" ".join(map(str, a)))

app = Flask(__name__)

CALLS_FILE = "calls.json"
SETTINGS_FILE = "settings.json"

lock = threading.Lock()  # Prevent simultaneous file writes

# Default settings
calls = []
settings = {
    "bot_active": True,
    "active_start": "00:00",
    "active_end": "23:59",
}

# --- Helpers ---
def load_data():
    global calls, settings
    if os.path.exists(CALLS_FILE):
        try:
            with open(CALLS_FILE, "r") as f:
                calls[:] = json.load(f)
        except Exception:
            calls.clear()

    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings.update(json.load(f))
        except Exception:
            pass

def save_data():
    with lock:
        with open(CALLS_FILE, "w") as f:
            json.dump(calls, f, indent=2)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)

def within_active_hours():
    now = datetime.now()
    try:
        start = datetime.strptime(settings["active_start"], "%H:%M").time()
        end = datetime.strptime(settings["active_end"], "%H:%M").time()
        return start <= now.time() <= end
    except Exception:
        return True

# --- Routes ---
@app.route("/")
def home():
    return "✅ Lexi Call Agent Server running!"

@app.route("/calls", methods=["GET"])
def get_calls():
    """Return full list of saved calls."""
    with lock:
        return jsonify(calls)

@app.route("/delete", methods=["POST"])
def delete_calls():
    """Delete specific calls when user checks box in dashboard."""
    to_delete = request.get_json(force=True)
    global calls
    with lock:
        calls = [c for c in calls if not (
            c["name"] == to_delete.get("name") and c["phone"] == to_delete.get("phone")
        )]
        save_data()
    return jsonify({"ok": True})

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "bot_active": settings["bot_active"],
        "active_start": settings["active_start"],
        "active_end": settings["active_end"],
        "within_hours": within_active_hours(),
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route("/toggle", methods=["POST"])
def toggle_bot():
    """Turn bot on/off from the dashboard."""
    data = request.get_json(force=True)
    settings["bot_active"] = bool(data.get("active", not settings["bot_active"]))
    save_data()
    return jsonify({"bot_active": settings["bot_active"]})

@app.route("/set-time-range", methods=["POST"])
def set_time_range():
    """Set active time range (controlled from dashboard)."""
    data = request.get_json(force=True)
    settings["active_start"] = data.get("start", "00:00")
    settings["active_end"] = data.get("end", "23:59")
    save_data()
    return jsonify({"ok": True, "settings": settings})

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    """Triggered when VAPI sends call data."""
    data = request.get_json(force=True)
    msg = data.get("message", {})
    if msg.get("type") != "end-of-call-report":
        return jsonify({"ignored": msg.get("type")}), 200

    # Respect bot active status & time range
    if not settings["bot_active"] or not within_active_hours():
        print("⏸ Ignored call (bot inactive or outside time range).")
        return jsonify({"ok": False, "reason": "inactive"}), 200

    # Extract summary info
    summary = msg.get("analysis", {}).get("summary", "")
    name, phone = "Unknown", "Unknown"

    # Attempt to find a name (two capitalized words)
    names = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", summary)
    if names:
        name = names[0]

    # Attempt to find a phone number
    digits = re.sub(r"\D", "", summary)
    if len(digits) >= 7:
        phone = digits[-10:]

    new_call = {
        "name": name,
        "phone": phone,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    with lock:
        # Prevent duplicates within 10 seconds (fixes flicker)
        if not calls or calls[-1] != new_call:
            calls.append(new_call)
            save_data()
            print(f"✅ Saved call: {name}, {phone}")
        else:
            print("⚠️ Duplicate call ignored (within last 10s).")

    return jsonify({"ok": True, "saved": new_call})

# --- Start server ---
if __name__ == "__main__":
    load_data()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)









