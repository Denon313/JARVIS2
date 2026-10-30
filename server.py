import os, json, time, secrets
from flask import Flask, request, send_from_directory, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

DATA = os.environ.get("DATA_DIR", "./data")
MOV = os.path.join(DATA, "movies")
os.makedirs(MOV, exist_ok=True)
PROF = os.path.join(DATA, "profiles.json")
ADMIN_PASS = "7030"
DEFAULT = {"mahdi": "مهدی", "mahna": "مهنا", "fateme": "فاطمه", "amirali": "امیرعلی", "rastin": "راستین"}

try:
    profiles = json.load(open(PROF, encoding="utf-8"))
except Exception:
    profiles = {k: {"name": v, "avatar": ""} for k, v in DEFAULT.items()}

app = Flask(__name__)
CORS(app)
sio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", max_http_buffer_size=3_000_000)

state = {"movie": None, "playing": False, "pos": 0.0, "at": time.time() * 1000}
sid_user, tokens, history = {}, set(), []


def now():
    return time.time() * 1000


def snap():
    pos = state["pos"] + ((now() - state["at"]) / 1000 if state["playing"] else 0)
    return {"movie": state["movie"], "playing": state["playing"], "pos": pos, "at": now()}


def online():
    return {u: list(sid_user.values()).count(u) for u in DEFAULT}


def save_profiles():
    json.dump(profiles, open(PROF, "w", encoding="utf-8"), ensure_ascii=False)


@sio.on("connect")
def _c():
    emit("presence", online())
    emit("profiles", profiles)
    emit("state", snap())


@sio.on("disconnect")
def _d():
    sid_user.pop(request.sid, None)
    sio.emit("presence", online())


@sio.on("tsync")
def _t():
    return now()


@sio.on("join")
def _j(d):
    uid = d.get("uid")
    if uid not in DEFAULT:
        return
    if uid == "mahdi" and d.get("password") != ADMIN_PASS:
        emit("join_error")
        return
    sid_user[request.sid] = uid
    token = None
    if uid == "mahdi":
        token = secrets.token_hex(16)
        tokens.add(token)
    emit("joined", {"uid": uid, "token": token})
    emit("history", history)
    emit("state", snap())
    sio.emit("presence", online())


@sio.on("control")
def _ctl(d):
    if request.sid not in sid_user:
        return
    a, pos = d.get("action"), float(d.get("pos", 0))
    state["pos"], state["at"] = pos, now()
    if a == "play":
        state["playing"] = True
    elif a == "pause":
        state["playing"] = False
    sio.emit("state", snap())


@sio.on("select_movie")
def _sel(d):
    if d.get("token") not in tokens:
        return
    state.update(movie=d.get("name"), playing=False, pos=0.0, at=now())
    sio.emit("state", snap())


@sio.on("chat")
def _chat(d):
    uid = sid_user.get(request.sid)
    text = str(d.get("text", ""))[:500].strip()
    if not uid or not text:
        return
    m = {"uid": uid, "text": text, "ts": now()}
    history.append(m)
    del history[:-100]
    sio.emit("chat", m)


@sio.on("profile")
def _p(d):
    uid = sid_user.get(request.sid)
    if not uid:
        return
    name = str(d.get("name", "")).strip()[:20] or profiles[uid]["name"]
    av = d.get("avatar", profiles[uid]["avatar"])
    profiles[uid] = {"name": name, "avatar": av if len(av) < 200000 else ""}
    save_profiles()
    sio.emit("profiles", profiles)


def admin():
    return request.headers.get("X-Token") in tokens


@app.get("/movies")
def movies():
    return jsonify([{"name": f, "size": os.path.getsize(os.path.join(MOV, f))} for f in sorted(os.listdir(MOV))])


@app.get("/movies/<path:name>")
def movie(name):
    return send_from_directory(MOV, name, conditional=True)


@app.post("/upload")
def upload():
    if not admin():
        return "no", 403
    f = request.files["file"]
    f.save(os.path.join(MOV, os.path.basename(f.filename)))
    return "ok"


@app.delete("/movies/<path:name>")
def delete(name):
    if not admin():
        return "no", 403
    os.remove(os.path.join(MOV, os.path.basename(name)))
    return "ok"


if __name__ == "__main__":
    sio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), allow_unsafe_werkzeug=True)
