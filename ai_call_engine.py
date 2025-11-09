# ai_call_engine.py
import os, io, json, threading, time
from flask import Flask, request, jsonify, send_file
import requests

OPENAI_KEY = os.getenv("OPENAI_API_KEY")  # set this in Render secrets
if not OPENAI_KEY:
    raise RuntimeError("Set OPENAI_API_KEY environment variable")

app = Flask(__name__)

OPENAI_BASE = "https://api.openai.com/v1"

# ---------- Helpers ----------
def openai_transcribe_wav(file_bytes, filename="audio.wav", model="whisper-1", language=None):
    """Send audio (wav/mp3) to OpenAI transcription endpoint, return text."""
    files = {
        "file": (filename, file_bytes),
    }
    data = {"model": model}
    if language:
        data["language"] = language
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    resp = requests.post(f"{OPENAI_BASE}/audio/transcriptions", headers=headers, files=files, data=data, timeout=60)
    resp.raise_for_status()
    return resp.json().get("text", "")

def openai_chat_reply(prompt, system_prompt=None, model="gpt-4o-mini"):
    """Send prompt to chat model and return assistant reply text."""
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": []
    }
    if system_prompt:
        body["messages"].append({"role": "system", "content": system_prompt})
    body["messages"].append({"role": "user", "content": prompt})
    resp = requests.post(f"{OPENAI_BASE}/chat/completions", headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    j = resp.json()
    # compatible with responses: pick the best text
    text = ""
    try:
        text = j["choices"][0]["message"]["content"]
    except Exception:
        text = j.get("choices", [{}])[0].get("text", "")
    return text.strip()

def openai_tts_mp3(text, voice="alloy", model="gpt-4o-mini-tts"):
    """Request TTS from OpenAI. Returns bytes (mp3) and content-type."""
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"  # accept mp3
    }
    body = {
        "model": model,
        "voice": voice,
        "input": text
    }
    # Note: some OpenAI deployments return binary audio directly; handle both.
    resp = requests.post(f"{OPENAI_BASE}/audio/speech", headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "audio/mpeg")

# ---------- Routes ----------
@app.route("/stt", methods=["POST"])
def stt():
    """
    Accepts form-data with 'file' (audio blob).
    Returns: {"text": "..."}
    """
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    data = f.read()
    try:
        text = openai_transcribe_wav(data, filename=f.filename or "audio.wav")
        return jsonify({"text": text})
    except requests.HTTPError as e:
        return jsonify({"error": str(e), "detail": e.response.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/reply", methods=["POST"])
def reply():
    """
    Body JSON: { "text": "<transcript>", "system_prompt": "<optional system voice/persona>" }
    Returns: {"reply": "..."}
    """
    data = request.get_json(force=True) or {}
    text = data.get("text", "")
    system_prompt = data.get("system_prompt")
    if not text:
        return jsonify({"error": "no text provided"}), 400
    try:
        reply_text = openai_chat_reply(text, system_prompt=system_prompt)
        return jsonify({"reply": reply_text})
    except requests.HTTPError as e:
        return jsonify({"error": str(e), "detail": e.response.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/tts", methods=["POST"])
def tts():
    """
    Body JSON: { "text": "...", "voice": "alloy" }
    Returns binary audio (mp3)
    """
    data = request.get_json(force=True) or {}
    text = data.get("text", "")
    voice = data.get("voice", "alloy")
    if not text:
        return jsonify({"error": "no text"}), 400
    try:
        audio_bytes, content_type = openai_tts_mp3(text, voice=voice)
        # return as downloadable file
        return send_file(io.BytesIO(audio_bytes), mimetype=content_type, as_attachment=False, download_name="reply.mp3")
    except requests.HTTPError as e:
        return jsonify({"error": str(e), "detail": e.response.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    return jsonify({"ok": True, "service": "mini-vapi", "version": "phase1"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Starting AI Call Engine on port", port)
    app.run(host="0.0.0.0", port=port, threaded=True)
