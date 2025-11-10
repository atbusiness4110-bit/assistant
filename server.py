#!/usr/bin/env python3
"""
server.py — A&T AI Backend (Render-ready)
----------------------------------------
Handles:
 - User registration & login (secure, database-backed)
 - JWT token authentication
 - Call logs, webhook, and status endpoints
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
import jwt
import os
import json
import re
import threading
import logging

# --------------------------------------------
# CONFIGURATION
# --------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
DATABASE_URL = "sqlite:///lexi.db"

# Flask setup
app = Flask(__name__)
CORS(app)
app.config["JSON_SORT_KEYS"] = False
log = logging.getLogger(__name__)

# Database setup
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

# --------------------------------------------
# MODELS
# --------------------------------------------
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

Base.metadata.create_all(bind=engine)

# --------------------------------------------
# JWT UTILS
# --------------------------------------------
def create_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=12)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# --------------------------------------------
# AUTH ROUTES
# --------------------------------------------
@app.route("/auth/register", methods=["POST"])
def auth_register():
    try:
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
    except Exception as e:
        log.exception("auth_register failed")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/auth/login", methods=["POST"])
def auth_login():
    try:
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
    except Exception as e:
        import traceback
        traceback.print_exc()  # ✅ show exact cause in Render logs
        return jsonify({"success": False, "message": str(e)}), 500


# --------------------------------------------
# CALL LOG ROUTES
# --------------------------------------------
@app.route("/calls", methods=["GET"])
def get_calls():
    db = SessionLocal()
    calls = db.query(CallLog).order_by(CallLog.time.desc()).all()
    db.close()
    return jsonify([
        {"id": c.id, "name": c.name, "number": c.number, "time": c.time.isoformat(), "status": c.status}
        for c in calls
    ])

@app.route("/calls", methods=["POST"])
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

# --------------------------------------------
# STATUS & WEBHOOK ENDPOINTS
# --------------------------------------------
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

# --------------------------------------------
# MAIN
# --------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)








































