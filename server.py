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
    """Always load calls from disk before using."""
    global calls
    try:
        if os.path.exists(CALLS_FILE):
            with open(CALLS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    calls = data
        else:
            calls = []
    except Exception as e:
        print(f"⚠️ Error loading data: {e}")
        calls = []

def save_data():
    """Atomically save current calls to disk."""
    global calls
    try:
        with lock:
            tmp_file = f"{CALLS_FILE}.tmp"
            with open(tmp_file, "w") as f:
                json.dump(calls, f, indent=2)
            os.replace(tmp_file, CALLS_FILE)
            print(f"💾 Saved {len(calls)} call(s).")
    except Exception as e:
        print(f"⚠️ Error saving data: {e}")



# --- Routes ---
@app.route("/")
def home():
    return "✅ Lexi Call Agent Server running!"


@app.route("/calls", methods=["GET"])
def get_calls():
    """Always load from disk before returning."""
    load_data()
    return jsonify(calls)


@app.route("/calls", methods=["DELETE"])
def delete_calls():
    try:
        data = request.get_json(force=True)
        to_delete = data.get("calls", [])
        if not to_delete:
            return jsonify({"error": "No calls provided"}), 400

        global calls
        before_count = len(calls)

        # Remove entries that exactly match all three fields
        def match(c, d):
            return (
                c.get("name") == d.get("name")
                and c.get("phone") == d.get("phone")
                and c.get("timestamp") == d.get("timestamp")
            )

        with lock:
            calls[:] = [
                c for c in calls
                if not any(match(c, d) for d in to_delete)
            ]
            save_data_async()  # Save changes to disk in background

        deleted_count = before_count - len(calls)
        print(f"🗑️ Deleted {deleted_count} call(s).")
        return jsonify({"deleted": deleted_count}), 200

    except Exception as e:
        print(f"⚠️ Error in delete_calls: {e}")
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
    print(f"Incoming data: {data}")

    name = data.get("name", "Unknown")
    phone = data.get("phone_number", "Unknown")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_call = {
        "name": name,
        "phone": phone,
        "timestamp": timestamp,
        "selected": False
    }

    load_data()  # 🔥 ensures we have the latest list before appending
    calls.append(new_call)
    save_data()

    return jsonify({"status": "ok", "added": new_call})



# --- Run Server ---
if __name__ == "__main__":
    load_data()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)


















