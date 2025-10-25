@app.route("/vapi/callback", methods=["POST"])
def vapi_callback():
    print("\n🔥 VAPI CALLBACK RECEIVED 🔥")

    try:
        try:
            data = request.get_json(force=True)
        except Exception:
            data = json.loads(request.data.decode("utf-8"))
        if isinstance(data, str):
            data = json.loads(data)

        print("\n📩 RAW VAPI DATA (truncated):\n", json.dumps(data, indent=2)[:1000])

        # extract message wrapper
        message = data.get("message", {})
        msg_type = message.get("type", "").lower()

        # we'll use timestamp as unique ID if Vapi doesn't send call_id
        call_id = str(message.get("timestamp", datetime.now().timestamp()))

        name = None
        phone = None

        # 1️⃣ check analysis summary first (most accurate)
        analysis = message.get("analysis", {})
        if "summary" in analysis:
            summary = analysis["summary"]

            # extract name and phone from text summary
            possible_names = re.findall(r"\b[A-Z][a-z]+\b", summary)
            filtered = [n for n in possible_names if n.lower() not in
                        ["hi", "hello", "thanks", "good", "morning", "evening",
                         "afternoon", "bye", "test", "you", "please", "attorney",
                         "law", "firm", "called", "recent", "contract", "agreement"]]
            if filtered:
                name = " ".join(filtered[:2])

            digits = re.sub(r"\D", "", summary)
            if len(digits) >= 7:
                phone = digits

        # 2️⃣ fallback: look in artifact.messages if summary is missing
        if not name or not phone:
            artifact = message.get("artifact", {})
            msgs = artifact.get("messages", [])
            for msg in msgs:
                text = str(msg.get("message", "")) or str(msg.get("content", ""))
                if not text:
                    continue
                digits = re.sub(r"\D", "", text)
                if len(digits) >= 7:
                    phone = digits
                poss = re.findall(r"\b[A-Z][a-z]+\b", text)
                if poss:
                    filt = [p for p in poss if p.lower() not in ["hi", "hello", "good", "bye", "thanks", "please"]]
                    if filt:
                        name = " ".join(filt[:2])

        # 3️⃣ save only if this is an end-of-call report
        if msg_type == "end-of-call-report":
            entry = {
                "call_id": call_id,
                "name": name or "Unknown",
                "phone": phone or "Unknown",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            calls[call_id] = entry
            print(f"✅ SAVED CALL: {entry}")
        else:
            print(f"ℹ️ Skipped (type={msg_type})")

        return jsonify({"ok": True}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500





