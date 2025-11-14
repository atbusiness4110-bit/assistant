#!/usr/bin/env python3
"""
server.py — A&T AI Backend + ARI bridge (Render-ready)

Features:
 - Flask with JWT auth & sqlite call log (from your prior server)
 - ARI WebSocket listener -> handles StasisStart events
 - VAPI endpoints: /vapi/dial (originate), /vapi/play (TTS playback), /vapi/hangup
 - Serves generated TTS files at /media/<file>.wav so Asterisk can play via HTTP
 - Minimal, pluggable stt/tts placeholders (replace with OpenAI or another provider)
 - NOTE: networking: make sure Asterisk can reach this service (ngrok / port-forward / same LAN)
"""
import os
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import requests
import websocket
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import jwt
from gtts import gTTS   # pip install gTTS

# ---------------------------
# Configuration (ENV-friendly)
# ---------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///lexi.db")

# Asterisk ARI config: ARI must be reachable from where this script runs.
# Example: "http://192.168.1.10:8088/ari"
ARI_URL = os.getenv("ARI_URL", "http://127.0.0.1:8088/ari")
# WebSocket events endpoint (Asterisk)
# e.g. "ws://192.168.1.10:8088/ari/events"
ARI_WS_URL = os.getenv("ARI_WS_URL", "ws://127.0.0.1:8088/ari/events")
ARI_USER = os.getenv("ARI_USER", "ariuser")
ARI_PASSWORD = os.getenv("ARI_PASSWORD", "aripass")
# Stasis app name configured in Asterisk (extensions -> Stasis(ai_app))
STASIS_APP = os.getenv("STASIS_APP", "ai_app")

# Public host where this Flask app is reachable by Asterisk (used for media URLs)
# e.g. "https://my-public-host.ngrok.io" or "https://your-render-app.onrender.com"
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "http://127.0.0.1:5000")

# Media dir for TTS files
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "./media"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Flask/DB settings
PORT = int(os.environ.get("PORT", 5000))

# Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("vapi_server")

# ---------------------------
# Flask + DB setup
# ---------------------------
app = Flask(__name__)
CORS(app)
app.config["JSON_SORT_KEYS"] = False

Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class CallLog(Base):
    __tablename__ = "calls"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    number = Column(String)
    time = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")
    asterisk_channel = Column(String, default="")  # store ARI channel id if present


Base.metadata.create_all(bind=engine)

# ---------------------------
# JWT utilities
# ---------------------------
def create_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=12)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None


def auth_required(fn):
    def wrapper(*a, **k):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"success": False, "message": "Missing token"}), 401
        token = auth.split(" ", 1)[1]
        data = verify_token(token)
        if not data:
            return jsonify({"success": False, "message": "Invalid/expired token"}), 401
        request.user = data
        return fn(*a, **k)
    wrapper.__name__ = fn.__name__
    return wrapper

# ---------------------------
# ARI REST helpers
# ---------------------------
def ari_rest(path, method="GET", params=None, json_body=None):
    url = f"{ARI_URL}{path}"
    auth = (ARI_USER, ARI_PASSWORD)
    try:
        if method == "GET":
            r = requests.get(url, auth=auth, params=params, timeout=10)
        elif method == "POST":
            r = requests.post(url, auth=auth, params=params, json=json_body, timeout=20)
        elif method == "DELETE":
            r = requests.delete(url, auth=auth, params=params, timeout=10)
        else:
            raise ValueError("Unsupported method")
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return r.text
    except Exception as e:
        log.exception("ARI REST error")
        raise

# ---------------------------
# Simple TTS (gTTS) util
# ---------------------------
def tts_save(text: str, filename: str = None) -> str:
    """
    Save TTS WAV file into MEDIA_DIR and return filename (relative).
    Uses gTTS -> saves MP3 then converts to WAV if needed. For simplicity we save MP3 and rely on Asterisk to support MP3 playback (Asterisk often supports it).
    If you need WAV specifically, convert via ffmpeg.
    """
    filename = filename or f"tts_{uuid.uuid4().hex}.mp3"
    path = MEDIA_DIR / filename
    try:
        t = gTTS(text=text)
        t.save(str(path))
        log.info("Saved TTS to %s", path)
        return filename
    except Exception:
        log.exception("TTS failed")
        raise

# ---------------------------
# ARI WebSocket listener (background thread)
# ---------------------------
def handle_incoming_channel(channel_id):
    """Called when we receive StasisStart for a channel — simple flow: answer, play greeting, hang up"""
    try:
        log.info("Handling incoming channel %s", channel_id)
        # Answer
        ari_rest(f"/channels/{quote_plus(channel_id)}/answer", method="POST")
        log.info("Answered %s", channel_id)

        # Play a greeting — either a static Asterisk sound or dynamically generated file
        # We will play a static sound if available, else a generated TTS via /media/<file>
        greeting_text = "Hello. This is A and T A I. Please hold while we connect you."
        try:
            fname = tts_save(greeting_text)
            media_url = f"{PUBLIC_HOST.rstrip('/')}/media/{fname}"
            # ARI play media via channel play:
            ari_rest(f"/channels/{quote_plus(channel_id)}/play", method="POST", json_body={"media": media_url})
            log.info("Requested playback on %s -> %s", channel_id, media_url)
            # Wait a few seconds for playback to complete (better: handle PlaybackFinished events)
            time.sleep(4)
        except Exception:
            # fallback to built-in sound if TTS fails
            try:
                ari_rest(f"/channels/{quote_plus(channel_id)}/play", method="POST", json_body={"media": "sound:hello-world"})
                time.sleep(3)
            except Exception:
                log.exception("Playback fallback failed")

        # Hang up
        ari_rest(f"/channels/{quote_plus(channel_id)}/hangup", method="POST")
        log.info("Hanged up %s", channel_id)

        # Log to DB
        db = SessionLocal()
        cl = CallLog(name="incoming", number="", status="finished", asterisk_channel=channel_id)
        db.add(cl)
        db.commit()
        db.close()
    except Exception:
        log.exception("Failed to handle incoming channel %s", channel_id)


def ari_ws_thread():
    """
    Connects to Asterisk ARI WebSocket events and listens for StasisStart events.
    Make sure ARI WS URL is reachable, like ws://ASTERISK_IP:8088/ari/events
    """
    ws_url = f"{ARI_WS_URL}?api_key={ARI_USER}:{ARI_PASSWORD}&app={STASIS_APP}"
    log.info("Starting ARI WS client -> %s", ws_url)

    def on_message(ws, message):
        try:
            ev = json.loads(message)
            ev_type = ev.get("type")
            if ev_type == "StasisStart":
                channel = ev.get("channel", {}).get("id")
                log.info("StasisStart event for channel %s", channel)
                if channel:
                    t = threading.Thread(target=handle_incoming_channel, args=(channel,), daemon=True)
                    t.start()
        except Exception:
            log.exception("Error processing ARI WS message")

    def on_error(ws, error):
        log.error("ARI WS error: %s", error)

    def on_close(ws, code, reason):
        log.warning("ARI WS closed: %s %s", code, reason)
        # reconnect after short wait
        time.sleep(3)
        start_ws()

    def on_open(ws):
        log.info("Connected to ARI WS")

    def start_ws():
        # create and run websocket; this call blocks until closed, so run within thread
        ws_app = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        # run_forever will block; that's why this function is run in a thread
        ws_app.run_forever()

    # start the WS loop (blocks)
    try:
        start_ws()
    except Exception:
        log.exception("ARI WS thread ended unexpectedly")


# ---------------------------
# Flask auth & basic routes (based on your prior server)
# ---------------------------
@app.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(force=True)
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"success": False, "message": "Missing username or password"}), 400
    db = SessionLocal()
    if db.query(User).filter_by(username=username).first():
        db.close()
        return jsonify({"success": False, "message": "Username already exists"}), 409
    hashed_pw = generate_password_hash(password)
    new_user = User(username=username, password_hash=hashed_pw)
    db.add(new_user)
    db.commit()
    db.close()
    return jsonify({"success": True, "message": "Account created successfully"})


@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True)
    username = data.get("username")
    password = data.get("password")
    db = SessionLocal()
    user = db.query(User).filter_by(username=username).first()
    db.close()
    if user and check_password_hash(user.password_hash, password):
        token = create_token(user.id)
        return jsonify({
            "success": True,
            "message": "Login successful",
            "token": token,
            "user_id": user.id,
            "name": user.username
        })
    else:
        return jsonify({"success": False, "message": "Invalid username or password"}), 401


@app.route("/calls", methods=["GET"])
@auth_required
def get_calls():
    db = SessionLocal()
    calls = db.query(CallLog).order_by(CallLog.time.desc()).all()
    db.close()
    return jsonify([
        {"id": c.id, "name": c.name, "number": c.number, "time": c.time.isoformat(), "status": c.status, "channel": c.asterisk_channel}
        for c in calls
    ])


@app.route("/calls", methods=["POST"])
@auth_required
def add_call():
    data = request.get_json(force=True)
    name = data.get("name", "Unknown")
    number = data.get("number", "")
    status = data.get("status", "pending")
    db = SessionLocal()
    call = CallLog(name=name, number=number, status=status)
    db.add(call)
    db.commit()
    db.close()
    return jsonify({"success": True, "message": "Call logged"})


@app.route("/calls/<int:call_id>/status", methods=["POST"])
@auth_required
def update_call_status(call_id):
    data = request.get_json(force=True)
    status = data.get("status", "pending")
    db = SessionLocal()
    call = db.query(CallLog).filter_by(id=call_id).first()
    if not call:
        db.close()
        return jsonify({"success": False, "message": "Call not found"}), 404
    call.status = status
    db.commit()
    db.close()
    return jsonify({"success": True, "message": f"Status updated to {status}"})


@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "online", "time": datetime.utcnow().isoformat()})


@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    try:
        payload = request.get_json(force=True)
        log.info("Received VAPI callback: %s", payload)
        return jsonify({"ok": True})
    except Exception as e:
        log.exception("vapi_callback failed")
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------------------
# VAPI endpoints (dial / play / hangup)
# ---------------------------
@app.route("/vapi/dial", methods=["POST"])
@auth_required
def vapi_dial():
    """
    Originate an outbound call via ARI.
    Expected JSON: { "endpoint": "PJSIP/1000", "exten": "1000", "context": "default", "callerId": "1555xxxx" }
    Or simply: { "to": "sip:user@...", "from": "...", "app": STASIS_APP }
    """
    data = request.get_json(force=True)
    endpoint = data.get("endpoint")
    to = data.get("to")
    exten = data.get("exten", "")
    context = data.get("context", "")
    callerid = data.get("callerId", None)

    if not endpoint and not to:
        return jsonify({"success": False, "message": "Missing 'endpoint' or 'to'"}), 400

    # build ARI create channel query params
    params = {}
    if endpoint:
        params["endpoint"] = endpoint
    else:
        params["endpoint"] = to
    params["app"] = data.get("app", STASIS_APP)
    if exten:
        params["extension"] = exten
    if context:
        params["context"] = context
    if callerid:
        params["callerId"] = callerid

    try:
        # Note: ARI create channel uses query params; using requests via ari_rest wrapper:
        # ari_rest will compose f"{ARI_URL}/channels?endpoint=..."
        # we construct path with params manually:
        qp = "&".join([f"{k}={quote_plus(str(v))}" for k, v in params.items()])
        resp = ari_rest(f"/channels?{qp}", method="POST")
        log.info("Dial initiated: %s", resp)
        # Log call to DB
        db = SessionLocal()
        cl = CallLog(name="outbound", number=endpoint or to, status="ringing", asterisk_channel=resp.get("id",""))
        db.add(cl)
        db.commit()
        db.close()
        return jsonify({"success": True, "carrier_response": resp})
    except Exception:
        return jsonify({"success": False, "message": "Failed to originate call"}), 500


@app.route("/vapi/play", methods=["POST"])
@auth_required
def vapi_play():
    """
    Play TTS on an active channel.
    JSON: { "channel_id": "<ARI_CHANNEL_ID>", "text": "Hello world" }
    """
    data = request.get_json(force=True)
    channel_id = data.get("channel_id")
    text = data.get("text", "")
    if not channel_id or not text:
        return jsonify({"success": False, "message": "Missing channel_id or text"}), 400
    try:
        fname = tts_save(text)
        media_url = f"{PUBLIC_HOST.rstrip('/')}/media/{fname}"
        ari_rest(f"/channels/{quote_plus(channel_id)}/play", method="POST", json_body={"media": media_url})
        return jsonify({"success": True, "media": media_url})
    except Exception:
        return jsonify({"success": False, "message": "Playback failed"}), 500


@app.route("/vapi/hangup", methods=["POST"])
@auth_required
def vapi_hangup():
    """
    Hangup a channel.
    JSON: { "channel_id": "<ARI_CHANNEL_ID>" }
    """
    data = request.get_json(force=True)
    channel_id = data.get("channel_id")
    if not channel_id:
        return jsonify({"success": False, "message": "Missing channel_id"}), 400
    try:
        ari_rest(f"/channels/{quote_plus(channel_id)}/hangup", method="POST")
        return jsonify({"success": True})
    except Exception:
        return jsonify({"success": False, "message": "Hangup failed"}), 500


# ---------------------------
# Media serving (TTS files)
# ---------------------------
@app.route("/media/<path:filename>", methods=["GET"])
def media_serve(filename):
    # Basic protection: only allow files in MEDIA_DIR
    safe_path = MEDIA_DIR.resolve()
    requested = (MEDIA_DIR / filename).resolve()
    if not str(requested).startswith(str(safe_path)):
        abort(404)
    if not requested.exists():
        abort(404)
    # Serve file
    return send_from_directory(str(MEDIA_DIR), filename, as_attachment=False)


# ---------------------------
# Startup: ARI WS thread + Flask run
# ---------------------------
def start_background_threads():
    t = threading.Thread(target=ari_ws_thread, daemon=True)
    t.start()
    log.info("Started ARI WS background thread")


if __name__ == "__main__":
    # Start ARI WS client in background
    start_background_threads()
    # Flask app
    app.run(host="0.0.0.0", port=PORT, threaded=True)










































