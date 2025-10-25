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
        return True  # fail-safe


def load_data():
    """Always load calls and settings from disk before use."""
    global calls, settings
    try:
        if os.path.exists(CALLS_FILE):
            with open(CALLS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    calls = data
        else:
            calls = []

        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                settings.update(json.load(f))

    except Exception as e:
        print(f"⚠️ Error loading data: {e}")


def save_data():
    """Atomically save data to disk."""
    try:
        with lock:
            tmp_file = f"{CALLS_FILE}.tmp"
            with open(tmp_file, "w") as f:
                json.dump(calls, f, indent=2)
            os.replace(tmp_file, CALLS_FILE)

            tmp_file2 = f"{SETTINGS_FILE}.tmp"
            with open(tmp_file2, "w") as f:
                json.dump(settings, f, indent=2)
            os.replace(tmp_file2, SETTINGS_FILE)

            print(f"💾 Saved {len(calls)} call(s).")
    except Exception as e:
        print(f"⚠️ Error saving data: {e}")


# --- Routes ---
@app.route("/")
def home():
    return "✅ Lexi Call Agent Server running!"


@app.route("/calls", methods=["GET"])
def get_calls():
    """Always load latest version from disk."""
    load_data()
    return jsonify(calls)


@app.route("/calls", methods=["DELETE"])
def delete_calls():
    """Delete selected calls (both client & server)."""
    try:
        data = request.get_json(force=True)
        to_delete = data.get("calls", [])
        if not to_delete:
            return jsonify({"error": "No calls provided"}), 400

        load_data()
        before_count = len(calls)

        def match(c, d):
            return (
                c.get("name") == d.get("name")
                and c.get("phone") == d.get("phone")
                and c.get("timestamp") == d.get("timestamp")
            )

        remaining = [
            c for c in calls if not any(match(c, d) for d in to_delete)
        ]

        with lock:
            calls[:] = remaining
        save_data()

        deleted_count = before_count - len(calls)
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
    """Handles incoming VAPI webhook calls and records them."""
    data = request.get_json(force=True)
    msg = data.get("message", {})

    # Only process end-of-call events
    if msg.get("type") != "end-of-call-report":
        return jsonify({"ignored": msg.get("type")}), 200

    if not settings["bot_active"] or not within_active_hours():
        print("⏸ Ignored call (bot inactive or outside time range).")
        return jsonify({"ok": False, "reason": "inactive"}), 200

    # Extract caller info
    summary = msg.get("analysis", {}).get("summary", "")
    name = "Unknown"
    phone = "Unknown"

    names = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", summary)
    if names:
        name = names[0]

    digits = re.sub(r"\D", "", summary)
    if len(digits) >= 7:
        phone = digits[-10:]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_call = {
        "name": name,
        "phone": phone,
        "timestamp": timestamp,
    }

    load_data()
    with lock:
        calls.append(new_call)
    save_data()

    print(f"✅ Saved call: {name}, {phone}, {timestamp}")
    return jsonify({"ok": True})


# --- Run Server ---
if __name__ == "__main__":
    load_data()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)




















