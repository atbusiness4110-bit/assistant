import os, json, re, threading, logging, sys, requests
from datetime import datetime
from flask import Flask, request, jsonify
from zoneinfo import ZoneInfo
import time as _t

# --- Logging setup ---
logging.basicConfig(stream=sys.stdout, level=logging.INFO, force=True)
print = lambda *a, **kw: logging.info(" ".join(map(str, a)))

# --- Flask setup ---
app = Flask(__name__)

CALLS_FILE = "calls.json"
SETTINGS_FILE = "settings.json"
lock = threading.Lock()

# --- Default settings ---
settings = {
    "bot_active": True,
    "active_start": "09:00 AM",
    "active_end": "05:00 PM",
    "manual_override": None  # "on", "off", or None (auto)
}

# --- Helpers ---
def load_settings():
    """Load settings safely."""
    global settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
                settings.update(loaded)
        except Exception as e:
            print(f"⚠️ Failed to load settings: {e}")
    else:
        save_settings()

def save_settings():
    """Persist settings safely."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to save settings: {e}")

def within_active_hours():
    """Check if current Mountain Time is within active range."""
    try:
        tz = ZoneInfo("America/Denver")
        now = datetime.now(tz).time()
        start = datetime.strptime(settings["active_start"], "%I:%M %p").time()
        end = datetime.strptime(settings["active_end"], "%I:%M %p").time()

        if start <= end:
            return start <= now <= end
        else:
            return now >= start or now <= end
    except Exception as e:
        print(f"⚠️ Error in within_active_hours: {e}")
        return True

# --- Auto-toggle worker ---
def auto_toggle_worker():
    """Runs in background every 60s to update bot_active automatically,
    unless a manual override is set."""
    while True:
        try:
            active_hours = within_active_hours()
            manual_override = settings.get("manual_override", None)

            if manual_override is not None:
                # Skip auto-toggle if user manually set ON/OFF
                continue

            prev = settings["bot_active"]
            settings["bot_active"] = active_hours
            if active_hours != prev:
                state = "ON" if active_hours else "OFF"
                print(f"⏱ Auto-toggle: Bot turned {state} (Mountain Time range)")
                save_settings()
        except Exception as e:
            print(f"⚠️ Auto-toggle error: {e}")
        finally:
            import time as _t
            _t.sleep(60)

# --- Calls storage ---
calls = []

def load_calls():
    global calls
    if os.path.exists(CALLS_FILE):
        try:
            with open(CALLS_FILE, "r") as f:
                calls = json.load(f)
        except Exception:
            calls = []
    else:
        calls = []

def save_calls():
    with open(CALLS_FILE, "w") as f:
        json.dump(calls, f, indent=2)

# --- Routes ---
@app.route("/")
def home():
    return "✅ Lexi Call Agent Server running with Smart Hours"

@app.route("/status")
def status():
    tz = ZoneInfo("America/Denver")
    now = datetime.now(tz)
    return jsonify({
        "bot_active": settings["bot_active"],
        "active_start": settings["active_start"],
        "active_end": settings["active_end"],
        "within_hours": within_active_hours(),
        "manual_override": settings.get("manual_override"),
        "server_time_mt": now.strftime("%Y-%m-%d %I:%M %p MT")
    })

@app.route("/toggle", methods=["POST"])
def toggle_vapi():
    try:
        data = request.get_json(force=True)
        active = bool(data.get("active", False))
        settings["bot_active"] = active
        settings["manual_override"] = True  # let UI override schedule
        save_settings()

        state = "ON" if active else "OFF"
        print(f"🟢 Manual toggle → Bot turned {state} (manual_override set)")
        return jsonify({"ok": True, "bot_active": active}), 200
    except Exception as e:
        print(f"⚠️ Toggle error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/clear-override", methods=["POST"])
def clear_override():
    """Allow dashboard to return to automatic schedule mode."""
    settings["manual_override"] = None
    save_settings()
    print("🔁 Manual override cleared → returning to automatic hours mode")
    return jsonify({"ok": True, "manual_override": None})

@app.route("/set-time-range", methods=["POST"])
def set_time_range():
    data = request.get_json(force=True)
    start = data.get("start", "09:00 AM")
    end = data.get("end", "05:00 PM")

    settings["active_start"] = start
    settings["active_end"] = end
    # changing schedule automatically clears override
    settings["manual_override"] = None
    save_settings()

    print(f"🕓 Active hours updated: {start} – {end} (MT); manual_override cleared")
    return jsonify({"ok": True, "settings": settings})

@app.route("/calls", methods=["GET"])
def get_calls():
    load_calls()
    return jsonify(calls)

@app.route("/calls", methods=["DELETE"])
def delete_calls():
    try:
        data = request.get_json(force=True)
        to_delete = data.get("calls", [])
        load_calls()

        remaining = [
            c for c in calls
            if not any(c["name"] == d["name"] and c["phone"] == d["phone"] for d in to_delete)
        ]

        with lock:
            calls[:] = remaining
        save_calls()
        return jsonify({"deleted": len(to_delete)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    data = request.get_json(force=True)
    msg = data.get("message", {})

    if msg.get("type") != "end-of-call-report":
        return jsonify({"ignored": msg.get("type")}), 200

    if not settings["bot_active"]:
        print("⏸ Ignored call (bot inactive).")
        return jsonify({"ok": False, "reason": "inactive"}), 200

    summary = msg.get("analysis", {}).get("summary", "")
    name = "Unknown"
    phone = "Unknown"

    names = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", summary)
    if names:
        name = names[0]

    digits = re.sub(r"\D", "", summary)
    if len(digits) >= 7:
        phone = digits[-10:]

    timestamp = datetime.now(ZoneInfo("America/Denver")).strftime("%Y-%m-%d %I:%M %p MT")
    new_call = {"name": name, "phone": phone, "timestamp": timestamp}

    load_calls()
    with lock:
        calls.append(new_call)
    save_calls()

    print(f"✅ Saved call: {name}, {phone}, {timestamp}")
    return jsonify({"ok": True})

@app.route("/resume-auto", methods=["POST"])
def resume_auto():
    """Resets manual override and resumes auto schedule."""
    settings["manual_override"] = None
    save_settings()
    print("🔄 Manual override cleared, resuming automatic schedule.")
    return jsonify({"ok": True})

# --- Run ---
if __name__ == "__main__":
    load_settings()
    load_calls()
    threading.Thread(target=auto_toggle_worker, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)

































