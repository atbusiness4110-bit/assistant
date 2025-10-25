import os, json, re, threading, logging, sys
from datetime import datetime
from flask import Flask, request, jsonify

# --- Logging setup ---
logging.basicConfig(stream=sys.stdout, level=logging.INFO, force=True)
print = lambda *a, **kw: logging.info(" ".join(map(str, a)))

# --- Flask setup ---
app = Flask(__name__)

CALLS_FILE = "calls.json"
SETTINGS_FILE = "settings.json"

# --- Data stores ---
calls = []
settings = {
    "bot_active": True,
    "active_start": "00:00",
    "active_end": "23:59",
}

lock = threading.Lock()


# --- Helpers ---
def within_active_hours():
    """Check if current time is within the active time range."""
    try:
        now = datetime.now().time()
        start = datetime.strptime(settings["active_start"], "%H:%M").time()
        end = datetime.strptime(settings["active_end"], "%H:%M").time()
        return start <= now <= end
    except Exception as e:
        print(f"⚠️ Error in within_active_hours: {e}")
        return True  # fail-safe: always true


def load_data():
    """Load existing call and settings data."""
    global calls, settings
    try:
        with lock:
            if os.path.exists(CALLS_FILE):
                with open(CALLS_FILE, "r") as f:
                    calls[:] = json.load(f)
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    settings.update(json.load(f))
        print("📂 Data loaded successfully.")
    except Exception as e:
        print(f"⚠️ Error loading data: {e}")


def save_data():
    """Save all data to disk."""
    try:
        with lock:
            with open(CALLS_FILE, "w") as f:
                json.dump(calls, f, indent=2)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        print("💾 Data saved successfully.")
    except Exception as e:
        print(f"⚠️ Error saving data: {e}")


def save_data_async():
    """Save data in background thread to avoid Render timeouts."""
    threading.Thread(target=save_data, daemon=True).start()


# --- Routes ---
@app.route("/")
def home():
    return "✅ Lexi Call Agent Server running!"


@app.route("/calls")
def get_calls():
    return jsonify(calls)


@app.route("/calls", methods=["DELETE"])
def delete_calls():
    try:
        data = request.get_json(force=True)
        to_delete = data.get("calls", [])
        if not to_delete:
            return jsonify({"error": "No calls provided"}), 400

        global calls_data
        before_count = len(calls_data)

        # Remove entries that exactly match all three fields
        def match(c, d):
            return (
                c.get("name") == d.get("name")
                and c.get("phone") == d.get("phone")
                and c.get("timestamp") == d.get("timestamp")
            )

        calls_data = [
            c for c in calls_data
            if not any(match(c, d) for d in to_delete)
        ]

        deleted_count = before_count - len(calls_data)
        return jsonify({"deleted": deleted_count}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    save_data_async()
    return jsonify({"bot_active": settings["bot_active"]})


@app.route("/set-time-range", methods=["POST"])
def set_time_range():
    data = request.get_json(force=True)
    settings["active_start"] = data.get("start", "00:00")
    settings["active_end"] = data.get("end", "23:59")
    save_data_async()
    return jsonify({"ok": True, "settings": settings})


@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    data = request.get_json(force=True)
    msg = data.get("message", {})

    # Only process end-of-call events
    if msg.get("type") != "end-of-call-report":
        return jsonify({"ignored": msg.get("type")}), 200

    # Check if bot is active and within hours
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
    save_data_async()

    print(f"✅ Saved call: {name}, {phone}")
    return jsonify({"ok": True})


# --- Run Server ---
if __name__ == "__main__":
    load_data()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)














