#!/usr/bin/env python3
"""
Teknakul unified chat (Phase 3). Reads/writes Twitch + YouTube live chat in one place.

  - OAuth connect for Twitch + YouTube (tokens encrypted at rest, auto-refreshed).
  - Per-creator ChatSession: a Twitch IRC reader/sender + a YouTube live-chat poller/sender,
    buffered into one merged stream.
  - Lazy start on /chat/poll; idle sessions stop after ~2 min.

Stdlib only (socket/ssl for IRC, urllib for the YouTube Data API). AGPL-3.0.
"""

import base64
import hashlib
import hmac
import json
import os
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONN_FILE = os.path.join(HERE, "chat_connections.json")
SECRET_FILE = os.environ.get("RESTREAM_SECRET_FILE", os.path.join(HERE, ".secret"))
TWITCH_ID = os.environ.get("TWITCH_CLIENT_ID", "")
TWITCH_SECRET = os.environ.get("TWITCH_CLIENT_SECRET", "")
GOOGLE_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
OAUTH_BASE = os.environ.get("OAUTH_BASE", "https://restream.teknakul.com").rstrip("/")
APP = os.environ.get("PUBLIC_APP_URL", "https://teknakul.com")
IDLE_STOP = 150

with open(SECRET_FILE, "rb") as _f:
    SECRET = _f.read().strip()

# ---- crypto (same scheme as restream/billing) ----------------------------------
def _ks(nonce, n):
    out, c = b"", 0
    while len(out) < n:
        out += hmac.new(SECRET, nonce + c.to_bytes(4, "big"), hashlib.sha256).digest(); c += 1
    return out[:n]

def enc(s):
    d = s.encode(); nonce = os.urandom(12); ks = _ks(nonce, len(d))
    return base64.b64encode(nonce + bytes(a ^ b for a, b in zip(d, ks))).decode()

def dec(t):
    raw = base64.b64decode(t); nonce, ct = raw[:12], raw[12:]; ks = _ks(nonce, len(ct))
    return bytes(a ^ b for a, b in zip(ct, ks)).decode()

# ---- connection store ----------------------------------------------------------
_flock = threading.Lock()
_SEC = ("token", "refresh")

def _load():
    try:
        with open(CONN_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save(d):
    tmp = CONN_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, CONN_FILE)

def set_conn(username, platform, data):
    with _flock:
        d = _load()
        d.setdefault(username, {})[platform] = {
            k: (enc(v) if k in _SEC and v else v) for k, v in data.items()}
        _save(d)

def get_conn(username):
    out = {}
    for plat, info in _load().get(username, {}).items():
        out[plat] = {k: (dec(v) if k in _SEC and v else v) for k, v in info.items()}
    return out

def disconnect(username, platform):
    with _flock:
        d = _load()
        if username in d and platform in d[username]:
            del d[username][platform]; _save(d)

# ---- oauth state ---------------------------------------------------------------
def _state(username, platform):
    raw = f"{username}|{platform}|{int(time.time())}"
    sig = hmac.new(SECRET, raw.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{raw}|{sig}".encode()).decode()

def _unstate(state):
    try:
        raw = base64.urlsafe_b64decode(state).decode()
        u, p, ts, sig = raw.split("|")
        exp = hmac.new(SECRET, f"{u}|{p}|{ts}".encode(), hashlib.sha256).hexdigest()[:16]
        if hmac.compare_digest(exp, sig) and time.time() - int(ts) < 600:
            return u, p
    except Exception:  # noqa
        pass
    return None, None

def authorize_url(platform, username):
    st = _state(username, platform)
    if platform == "twitch":
        return "https://id.twitch.tv/oauth2/authorize?" + urllib.parse.urlencode({
            "client_id": TWITCH_ID, "redirect_uri": OAUTH_BASE + "/oauth/twitch/callback",
            "response_type": "code", "scope": "chat:read chat:edit user:read:email", "state": st})
    if platform == "youtube":
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": GOOGLE_ID, "redirect_uri": OAUTH_BASE + "/oauth/youtube/callback",
            "response_type": "code", "access_type": "offline", "prompt": "consent",
            "scope": "https://www.googleapis.com/auth/youtube.readonly "
                     "https://www.googleapis.com/auth/youtube.force-ssl", "state": st})
    return None

# ---- http helpers --------------------------------------------------------------
def _post(url, data, headers=None):
    body = urllib.parse.urlencode(data).encode()
    h = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        h.update(headers)
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, data=body, headers=h, method="POST"), timeout=20).read())

def _get(url, headers):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=20).read())

def _post_json(url, obj, headers):
    body = json.dumps(obj).encode()
    h = {"Content-Type": "application/json"}; h.update(headers)
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, data=body, headers=h, method="POST"), timeout=20).read())

# ---- oauth callback / refresh --------------------------------------------------
def handle_callback(platform, code, state):
    username, plat = _unstate(state)
    if not username or plat != platform:
        return None, "invalid state"
    if platform == "twitch":
        tok = _post("https://id.twitch.tv/oauth2/token", {
            "client_id": TWITCH_ID, "client_secret": TWITCH_SECRET, "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": OAUTH_BASE + "/oauth/twitch/callback"})
        login = _get("https://api.twitch.tv/helix/users",
                     {"Authorization": "Bearer " + tok["access_token"],
                      "Client-Id": TWITCH_ID})["data"][0]["login"]
        set_conn(username, "twitch", {"token": tok["access_token"],
                                      "refresh": tok.get("refresh_token", ""), "login": login})
        return username, None
    if platform == "youtube":
        tok = _post("https://oauth2.googleapis.com/token", {
            "client_id": GOOGLE_ID, "client_secret": GOOGLE_SECRET, "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": OAUTH_BASE + "/oauth/youtube/callback"})
        set_conn(username, "youtube", {"token": tok["access_token"],
                                       "refresh": tok.get("refresh_token", "")})
        return username, None
    return None, "unknown platform"

def _twitch_refresh(username, refresh):
    tok = _post("https://id.twitch.tv/oauth2/token", {
        "client_id": TWITCH_ID, "client_secret": TWITCH_SECRET,
        "grant_type": "refresh_token", "refresh_token": refresh})
    c = get_conn(username).get("twitch", {})
    c.update({"token": tok["access_token"], "refresh": tok.get("refresh_token", refresh)})
    set_conn(username, "twitch", c)
    return tok["access_token"]

def _google_token(username):
    c = get_conn(username).get("youtube", {})
    tok = _post("https://oauth2.googleapis.com/token", {
        "client_id": GOOGLE_ID, "client_secret": GOOGLE_SECRET,
        "grant_type": "refresh_token", "refresh_token": c.get("refresh", "")})
    c["token"] = tok["access_token"]; set_conn(username, "youtube", c)
    return tok["access_token"]

# ---- chat session --------------------------------------------------------------
class Session:
    def __init__(self, username):
        self.username = username
        self.buf = []
        self.lock = threading.Lock()
        self.last_poll = time.time()
        self.running = True
        self.twitch_sock = None
        self.twitch_channel = None
        threading.Thread(target=self._twitch_loop, daemon=True).start()
        threading.Thread(target=self._youtube_loop, daemon=True).start()

    def _add(self, platform, user, text):
        with self.lock:
            self.buf.append({"platform": platform, "user": user, "text": text,
                             "ts": int(time.time() * 1000)})
            self.buf = self.buf[-300:]

    def messages(self, after):
        self.last_poll = time.time()
        with self.lock:
            return [m for m in self.buf if m["ts"] > after]

    def stop(self):
        self.running = False
        try:
            if self.twitch_sock:
                self.twitch_sock.close()
        except Exception:  # noqa
            pass

    # ---- twitch ----
    def _twitch_loop(self):
        while self.running:
            conn = get_conn(self.username).get("twitch")
            if not conn:
                time.sleep(10); continue
            try:
                token, login = conn["token"], conn["login"]
                self.twitch_channel = "#" + login
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(socket.create_connection(("irc.chat.twitch.tv", 6697), timeout=15),
                                    server_hostname="irc.chat.twitch.tv")
                s.sendall(f"PASS oauth:{token}\r\nNICK {login}\r\nCAP REQ :twitch.tv/tags\r\nJOIN #{login}\r\n".encode())
                self.twitch_sock = s
                s.settimeout(20); buf = ""
                while self.running:
                    try:
                        data = s.recv(4096).decode("utf-8", "replace")
                    except socket.timeout:
                        s.sendall(b"PING :tmi.twitch.tv\r\n"); continue
                    if not data:
                        break
                    buf += data
                    while "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                        if line.startswith("PING"):
                            s.sendall(b"PONG :tmi.twitch.tv\r\n")
                        elif "PRIVMSG" in line:
                            user = line.split("!")[0].split(" ")[-1].lstrip("@:")
                            # prefer display-name tag
                            if line.startswith("@") and "display-name=" in line:
                                dn = line.split("display-name=", 1)[1].split(";", 1)[0]
                                if dn:
                                    user = dn
                            text = line.split("PRIVMSG", 1)[1].split(":", 1)[-1]
                            self._add("twitch", user, text)
            except urllib.error.HTTPError:
                try:
                    self._twitch_refresh_inline()
                except Exception:  # noqa
                    pass
                time.sleep(5)
            except Exception:  # noqa
                time.sleep(8)

    def _twitch_refresh_inline(self):
        conn = get_conn(self.username).get("twitch")
        if conn and conn.get("refresh"):
            _twitch_refresh(self.username, conn["refresh"])

    def send_twitch(self, text):
        if self.twitch_sock and self.twitch_channel:
            self.twitch_sock.sendall(f"PRIVMSG {self.twitch_channel} :{text}\r\n".encode())
            self._add("twitch", "you", text)
            return True
        return False

    # ---- youtube ----
    def _youtube_loop(self):
        page = None; live_chat_id = None; backoff = 8
        while self.running:
            conn = get_conn(self.username).get("youtube")
            if not conn:
                time.sleep(15); continue
            try:
                tok = _google_token(self.username)
                hdr = {"Authorization": "Bearer " + tok}
                if not live_chat_id:
                    b = _get("https://www.googleapis.com/youtube/v3/liveBroadcasts?part=snippet&broadcastStatus=active&broadcastType=all&mine=true", hdr)
                    items = b.get("items", [])
                    if not items:
                        time.sleep(20); continue
                    live_chat_id = items[0]["snippet"].get("liveChatId")
                    self._yt_chat_id = live_chat_id
                    if not live_chat_id:
                        time.sleep(20); continue
                url = ("https://www.googleapis.com/youtube/v3/liveChat/messages?part=snippet,authorDetails&liveChatId="
                       + live_chat_id + ("&pageToken=" + page if page else ""))
                r = _get(url, hdr)
                page = r.get("nextPageToken")
                for it in r.get("items", []):
                    self._add("youtube", it["authorDetails"]["displayName"],
                              it["snippet"].get("displayMessage", ""))
                time.sleep(max(int(r.get("pollingIntervalMillis", 6000)) / 1000.0, 4))
            except Exception:  # noqa
                live_chat_id = None
                time.sleep(backoff)

    def send_youtube(self, text):
        conn = get_conn(self.username).get("youtube")
        cid = getattr(self, "_yt_chat_id", None)
        if not conn or not cid:
            return False
        tok = _google_token(self.username)
        _post_json("https://www.googleapis.com/youtube/v3/liveChat/messages?part=snippet",
                   {"snippet": {"liveChatId": cid, "type": "textMessageEvent",
                                "textMessageDetails": {"messageText": text}}},
                   {"Authorization": "Bearer " + tok})
        self._add("youtube", "you", text)
        return True

# ---- manager -------------------------------------------------------------------
_sessions = {}
_slock = threading.Lock()

def _reaper():
    while True:
        time.sleep(30)
        with _slock:
            for u in [u for u, s in _sessions.items() if time.time() - s.last_poll > IDLE_STOP]:
                _sessions[u].stop(); del _sessions[u]

threading.Thread(target=_reaper, daemon=True).start()

def _session(username):
    with _slock:
        if username not in _sessions:
            _sessions[username] = Session(username)
        return _sessions[username]

def poll(username, after):
    if not get_conn(username):
        return {"connected": [], "messages": []}
    s = _session(username)
    return {"connected": list(get_conn(username).keys()),
            "messages": s.messages(after)}

def send(username, platform, text):
    s = _session(username)
    if platform == "twitch":
        return s.send_twitch(text)
    if platform == "youtube":
        return s.send_youtube(text)
    return False

def status(username):
    conns = get_conn(username)
    return {"connected": list(conns.keys()),
            "twitch": conns.get("twitch", {}).get("login") if "twitch" in conns else None,
            "youtube": ("youtube" in conns)}
