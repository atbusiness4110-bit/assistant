#!/usr/bin/env python3
"""
server.py — Lexi Call Agent Server (DB, Auth, Smart Hours, AI converse)
Drop-in for Render (or run locally).
Required env vars:
 - OPENAI_API_KEY
 - JWT_SECRET
 - (optional) DATABASE_URL
"""

import os
import io
import json
import re
import threading
import logging
import sys
import base64
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
from zoneinfo import ZoneInfo
import time as _t

# security / db
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from functools import wraps
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

@app.route("/register", methods=["POST"])
def register_user():
    data = request.json
    users = load_users()
    if any(u["username"] == data["username"] for u in users):
        return jsonify({"success": False, "message": "Username already exists"})
    users.append({
        "name": data.get("name"),
        "username": data.get("username"),
        "password": data.get("password")  # plain text for now
    })
    save_users(users)
    return jsonify({"success": True, "message": "Account created successfully"})

@app.route("/login", methods=["POST"])
def login_user():
    data = request.json
    users = load_users()
    for u in users:
        if u["username"] == data["username"] and u["password"] == data["password"]:
            return jsonify({"success": True, "name": u["name"]})
    return jsonify({"success": False, "message": "Invalid username or password"})
# ---------------------------
# Logging & Flask app
# ---------------------------
logging.basicConfig(stream=sys.stdout, level=logging.INFO, force=True)
log = logging.getLogger("lexi-server")
app = Flask(__name__)

# ---------------------------
# Environment / Config
# ---------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///lexi.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "please_set_a_real_secret")
JWT_EXP_MINUTES = 60 * 24  # 1 day tokens
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")  # must be set on Render
OPENAI_BASE = "https://api.openai.com/v1"

if not OPENAI_KEY:
    log.warning("OPENAI_API_KEY not set — AI endpoints will fail until provided")

# ---------------------------
# DB & ORM
# ---------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    agents = relationship("Agent", back_populates="owner", cascade="all,delete")


class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    system_prompt = Column(Text, default="")
    voice = Column(String(100), default="alloy")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner = relationship("User", back_populates="agents")


class PhoneBinding(Base):
    __tablename__ = "phone_bindings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    phone_number = Column(String(40), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CallRecord(Base):
    __tablename__ = "calls"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    agent_id = Column(Integer, ForeignKey("agents.id"))
    name = Column(String(200))
    phone = Column(String(40))
    timestamp = Column(String(80))
    summary = Column(Text)
    raw = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)

# ---------------------------
# JWT helpers & decorator
# ---------------------------
def create_token(user_id):
    payload = {"sub": int(user_id), "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)}
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token


def decode_token(token):
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return data.get("sub")
    except Exception:
        return None


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing token"}), 401
        token = auth.split(" ", 1)[1]
        user_id = decode_token(token)
        if not user_id:
            return jsonify({"error": "Invalid token"}), 401
        request.db = SessionLocal()
        request.user_id = int(user_id)
        return f(*args, **kwargs)
    return decorated


# ---------------------------
# File-based settings & calls fallback (kept for compatibility)
# ---------------------------
CALLS_FILE = "calls.json"
SETTINGS_FILE = "settings.json"
lock = threading.Lock()

settings = {
    "bot_active": True,
    "active_start": "09:00 AM",
    "active_end": "05:00 PM",
    "manual_override": None,  # "on", "off", or None (auto)
}


def safe_write_json(path: str, obj):
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log.warning("Failed to write %s: %s", path, e)


def load_settings():
    global settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                settings.update(loaded)
        except Exception as e:
            log.warning("Failed to load settings: %s", e)
    else:
        save_settings()


def save_settings():
    try:
        safe_write_json(SETTINGS_FILE, settings)
    except Exception as e:
        log.warning("Failed to save settings: %s", e)


def within_active_hours() -> bool:
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
        log.warning("Error in within_active_hours: %s", e)
        return True


# Auto-toggle worker
def auto_toggle_worker():
    log.info("Auto-toggle worker started")
    while True:
        try:
            manual = settings.get("manual_override", None)
            if manual == "on":
                if not settings.get("bot_active", False):
                    settings["bot_active"] = True
                    save_settings()
                    log.info("Manual override 'on' => bot_active = ON")
            elif manual == "off":
                if settings.get("bot_active", True):
                    settings["bot_active"] = False
                    save_settings()
                    log.info("Manual override 'off' => bot_active = OFF")
            else:
                active_hours = within_active_hours()
                prev = settings.get("bot_active", False)
                if active_hours != prev:
                    settings["bot_active"] = active_hours
                    save_settings()
                    state = "ON" if active_hours else "OFF"
                    log.info("Auto-toggle: Bot turned %s (Mountain Time range)", state)
        except Exception as e:
            log.warning("Auto-toggle error: %s", e)
        _t.sleep(60)


# Calls storage helpers (file-based fallback)
calls = []


def load_calls():
    global calls
    if os.path.exists(CALLS_FILE):
        try:
            with open(CALLS_FILE, "r", encoding="utf-8") as f:
                calls = json.load(f)
        except Exception as e:
            log.warning("Failed to load calls.json: %s", e)
            calls = []
    else:
        calls = []


def save_calls():
    try:
        with lock:
            safe_write_json(CALLS_FILE, calls)
    except Exception as e:
        log.warning("Failed to save calls.json: %s", e)


# ---------------------------
# OpenAI helper functions
# ---------------------------
def openai_transcribe(file_bytes, filename="audio.wav", model="whisper-1", language=None):
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    files = {"file": (filename, file_bytes, "audio/wav")}
    data = {"model": model}
    if language:
        data["language"] = language
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    r = requests.post(f"{OPENAI_BASE}/audio/transcriptions", headers=headers, files=files, data=data, timeout=120)
    r.raise_for_status()
    return r.json().get("text", "")


def openai_chat_reply(prompt_text, system_prompt=None, model="gpt-4o-mini"):
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    body = {"model": model, "messages": []}
    if system_prompt:
        body["messages"].append({"role": "system", "content": system_prompt})
    body["messages"].append({"role": "user", "content": prompt_text})
    r = requests.post(f"{OPENAI_BASE}/chat/completions", headers=headers, json=body, timeout=120)
    r.raise_for_status()
    j = r.json()
    text = ""
    try:
        text = j["choices"][0]["message"]["content"]
    except Exception:
        text = j.get("choices", [{}])[0].get("text", "")
    return text.strip()


def openai_tts_bytes(text, voice="alloy", model="gpt-4o-mini-tts"):
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {"model": model, "voice": voice, "input": text}
    r = requests.post(f"{OPENAI_BASE}/audio/speech", headers=headers, json=body, timeout=120)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "audio/mpeg")


# ---------------------------
# Auth endpoints
# ---------------------------
@app.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(force=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "username & password required"}), 400
    db = SessionLocal()
    if db.query(User).filter_by(username=username).first():
        return jsonify({"error": "username taken"}), 400
    u = User(username=username, password_hash=generate_password_hash(password))
    db.add(u)
    db.commit()
    return jsonify({"ok": True, "user_id": u.id}), 201


@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "username & password required"}), 400
    db = SessionLocal()
    user = db.query(User).filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "invalid credentials"}), 401
    token = create_token(user.id)
    return jsonify({"token": token, "user_id": user.id})


# ---------------------------
# Agent & phone endpoints (require auth)
# ---------------------------
@app.route("/agents", methods=["GET"])
@require_auth
def list_agents():
    db = request.db
    agents = db.query(Agent).filter_by(user_id=request.user_id).all()
    return jsonify([{"id": a.id, "name": a.name, "system_prompt": a.system_prompt, "voice": a.voice, "active": a.active} for a in agents])


@app.route("/agents", methods=["POST"])
@require_auth
def create_agent():
    data = request.get_json(force=True) or {}
    name = data.get("name", "New Agent")
    db = request.db
    a = Agent(user_id=request.user_id, name=name, system_prompt=data.get("system_prompt", ""))
    db.add(a)
    db.commit()
    return jsonify({"ok": True, "agent_id": a.id})


@app.route("/agents/<int:agent_id>/systemPrompt", methods=["PATCH"])
@require_auth
def update_agent_prompt(agent_id):
    data = request.get_json(force=True) or {}
    prompt = data.get("systemPrompt")
    if prompt is None:
        return jsonify({"error": "systemPrompt required"}), 400
    db = request.db
    a = db.query(Agent).filter_by(id=agent_id, user_id=request.user_id).first()
    if not a:
        return jsonify({"error": "not found"}), 404
    a.system_prompt = prompt
    db.commit()
    return jsonify({"ok": True})


@app.route("/agents/<int:agent_id>/toggle", methods=["POST"])
@require_auth
def toggle_agent(agent_id):
    data = request.get_json(force=True) or {}
    active = bool(data.get("active", False))
    db = request.db
    a = db.query(Agent).filter_by(id=agent_id, user_id=request.user_id).first()
    if not a:
        return jsonify({"error": "not found"}), 404
    a.active = active
    db.commit()
    return jsonify({"ok": True, "active": a.active})


@app.route("/phones/link", methods=["POST"])
@require_auth
def link_phone():
    data = request.get_json(force=True) or {}
    phone = data.get("phone")
    agent_id = data.get("agent_id")
    if not phone or not agent_id:
        return jsonify({"error": "phone & agent_id required"}), 400
    db = request.db
    a = db.query(Agent).filter_by(id=agent_id, user_id=request.user_id).first()
    if not a:
        return jsonify({"error": "agent not found"}), 404
    pb = PhoneBinding(user_id=request.user_id, agent_id=agent_id, phone_number=phone)
    db.add(pb)
    db.commit()
    return jsonify({"ok": True, "binding_id": pb.id})


# ---------------------------
# AI Converse endpoint: STT -> Chat -> TTS
# ---------------------------
@app.route("/agents/<int:agent_id>/converse", methods=["POST"])
@require_auth
def agent_converse(agent_id):
    """
    Accepts multipart/form-data with 'file' (wav) upload.
    Returns JSON: {"transcript": "...", "reply": "...", "audio_b64": "<base64 mp3>"}
    """
    db = request.db
    agent = db.query(Agent).filter_by(id=agent_id, user_id=request.user_id).first()
    if not agent:
        return jsonify({"error": "agent not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "no audio file uploaded (multipart form 'file')"}), 400

    file = request.files["file"]
    try:
        file_bytes = file.read()
        transcript = openai_transcribe(file_bytes, filename=file.filename or "audio.wav", model="whisper-1")
    except requests.HTTPError as e:
        return jsonify({"error": "stt_failed", "detail": e.response.text}), 500
    except Exception as e:
        return jsonify({"error": "stt_error", "detail": str(e)}), 500

    try:
        reply_text = openai_chat_reply(transcript, system_prompt=agent.system_prompt, model="gpt-4o-mini")
    except requests.HTTPError as e:
        return jsonify({"error": "chat_failed", "detail": e.response.text}), 500
    except Exception as e:
        return jsonify({"error": "chat_error", "detail": str(e)}), 500

    try:
        audio_bytes, content_type = openai_tts_bytes(reply_text, voice=agent.voice or "alloy", model="gpt-4o-mini-tts")
    except requests.HTTPError as e:
        return jsonify({"error": "tts_failed", "detail": e.response.text}), 500
    except Exception as e:
        return jsonify({"error": "tts_error", "detail": str(e)}), 500

    # Save call record
    try:
        name = "Unknown"
        phone = "Unknown"
        names = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", transcript)
        if names:
            name = names[0]
        digits = re.sub(r"\D", "", transcript)
        if len(digits) >= 7:
            phone = digits[-10:]
        timestamp = datetime.now(ZoneInfo("America/Denver")).strftime("%Y-%m-%d %I:%M %p MT")
        cr = CallRecord(
            user_id=request.user_id,
            agent_id=agent.id,
            name=name,
            phone=phone,
            timestamp=timestamp,
            summary=reply_text,
            raw=json.dumps({"transcript": transcript}),
        )
        request.db.add(cr)
        request.db.commit()
    except Exception as e:
        log.warning("Failed to save call record: %s", e)

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    return jsonify({"transcript": transcript, "reply": reply_text, "audio_b64": audio_b64})


# ---------------------------
# Status / settings / toggle / calls routes (file-based & backwards compat)
# ---------------------------
@app.route("/")
def home():
    return "✅ Lexi Call Agent Server running with Smart Hours"


@app.route("/health")
def health():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat() + "Z"})


@app.route("/status")
def status():
    tz = ZoneInfo("America/Denver")
    now = datetime.now(tz)
    return jsonify(
        {
            "bot_active": settings["bot_active"],
            "active_start": settings["active_start"],
            "active_end": settings["active_end"],
            "within_hours": within_active_hours(),
            "manual_override": settings.get("manual_override"),
            "server_time_mt": now.strftime("%Y-%m-%d %I:%M %p MT"),
        }
    )


@app.route("/toggle", methods=["POST"])
def toggle_vapi():
    try:
        data = request.get_json(force=True) or {}
        active = bool(data.get("active", False))
        # when toggled via this route we use file-based global settings for backwards compat
        settings["bot_active"] = active
        settings["manual_override"] = "on" if active else "off"
        save_settings()
        state = "ON" if active else "OFF"
        log.info("Manual toggle → Bot turned %s (manual_override set)", state)
        return jsonify({"ok": True, "bot_active": active}), 200
    except Exception as e:
        log.exception("Toggle error")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/clear-override", methods=["POST"])
def clear_override():
    settings["manual_override"] = None
    save_settings()
    log.info("Manual override cleared → returning to automatic hours mode")
    return jsonify({"ok": True, "manual_override": None})


@app.route("/set-time-range", methods=["POST"])
def set_time_range():
    data = request.get_json(force=True) or {}
    start = data.get("start", "09:00 AM")
    end = data.get("end", "05:00 PM")
    settings["active_start"] = start
    settings["active_end"] = end
    settings["manual_override"] = None
    save_settings()
    log.info("Active hours updated: %s – %s (MT); manual_override cleared", start, end)
    return jsonify({"ok": True, "settings": settings})


@app.route("/calls", methods=["GET"])
def get_calls():
    # try DB first; fallback to file-based if empty
    try:
        db = SessionLocal()
        recs = db.query(CallRecord).order_by(CallRecord.created_at.desc()).limit(200).all()
        result = []
        for r in recs:
            result.append(
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "agent_id": r.agent_id,
                    "name": r.name,
                    "phone": r.phone,
                    "timestamp": r.timestamp,
                    "summary": r.summary,
                }
            )
        if result:
            return jsonify(result)
    except Exception:
        log.info("DB calls fetch failed or no records; falling back to file-based calls")
    load_calls()
    return jsonify(calls)


@app.route("/calls", methods=["DELETE"])
def delete_calls():
    try:
        data = request.get_json(force=True) or {}
        to_delete = data.get("calls", [])
        load_calls()
        remaining = [c for c in calls if not any(c["name"] == d.get("name") and c["phone"] == d.get("phone") for d in to_delete)]
        with lock:
            calls[:] = remaining
        save_calls()
        return jsonify({"deleted": len(to_delete)})
    except Exception as e:
        log.exception("delete_calls error")
        return jsonify({"error": str(e)}), 500


@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    """
    External services (or your dashboard) can post end-of-call reports here.
    This will save into DB (if available) mapping phone -> phone_binding -> user/agent when possible.
    """
    try:
        data = request.get_json(force=True) or {}
        msg = data.get("message", {}) or {}
        if msg.get("type") != "end-of-call-report":
            return jsonify({"ignored": msg.get("type")}), 200
        if not settings.get("bot_active", True):
            log.info("Ignored call (bot inactive).")
            return jsonify({"ok": False, "reason": "inactive"}), 200

        summary = msg.get("analysis", {}).get("summary", "") or ""
        name = "Unknown"
        phone = "Unknown"
        names = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", summary)
        if names:
            name = names[0]
        digits = re.sub(r"\D", "", summary)
        if len(digits) >= 7:
            phone = digits[-10:]

        timestamp = datetime.now(ZoneInfo("America/Denver")).strftime("%Y-%m-%d %I:%M %p MT")

        # Try mapping to phone binding (by suffix)
        dbs = SessionLocal()
        binding = None
        if phone and phone != "Unknown":
            # try exact then suffix match
            binding = dbs.query(PhoneBinding).filter(PhoneBinding.phone_number == phone).first()
            if not binding:
                # suffix match: last 7-10 digits
                for length in (10, 7):
                    suffix = phone[-length:]
                    binding = dbs.query(PhoneBinding).filter(PhoneBinding.phone_number.endswith(suffix)).first()
                    if binding:
                        break

        if binding:
            user_id = binding.user_id
            agent_id = binding.agent_id
        else:
            user_id = None
            agent_id = None

        # save into DB if possible
        try:
            cr = CallRecord(
                user_id=user_id,
                agent_id=agent_id,
                name=name,
                phone=phone,
                timestamp=timestamp,
                summary=summary,
                raw=json.dumps(data),
            )
            dbs.add(cr)
            dbs.commit()
            log.info("Saved call -> DB: %s %s %s", name, phone, timestamp)
        except Exception as e:
            log.warning("Failed to save call to DB: %s", e)
            # fallback to file-based
            load_calls()
            with lock:
                calls.append({"name": name, "phone": phone, "timestamp": timestamp})
            save_calls()
            log.info("Saved call -> file fallback: %s %s", name, phone)

        return jsonify({"ok": True})
    except Exception as e:
        log.exception("vapi_callback error")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/resume-auto", methods=["POST"])
def resume_auto():
    settings["manual_override"] = None
    save_settings()
    log.info("Manual override cleared, resuming automatic schedule.")
    return jsonify({"ok": True})


# ---------------------------
# Boot
# ---------------------------
if __name__ == "__main__":
    load_settings()
    load_calls()
    t = threading.Thread(target=auto_toggle_worker, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    log.info("Starting Lexi server on port %s", port)
    app.run(host="0.0.0.0", port=port, threaded=True)




































