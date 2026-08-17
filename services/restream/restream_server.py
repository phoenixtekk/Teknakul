#!/usr/bin/env python3
"""
Teknakul Multistream — destinations service + fan-out engine (Phase 1).

Two jobs:
  1) HTTP API to manage a creator's restream destinations (Twitch/YouTube/Kick/custom
     RTMP), Pro-gated, stream keys encrypted at rest.
  2) A background engine that watches for a creator's LIVE broadcast and fans it out
     with ffmpeg `-c copy` (no re-encode) to each of their enabled destinations.

Model: OBS/phone -> PeerTube (Teknakul live) -> this engine pulls the live's HLS and
pushes copies to each external platform. Non-invasive: creators keep their normal OBS
setup pointed at Teknakul; the fan-out happens server-side.

Stdlib only + ffmpeg. Entitlements come from a local file for now (Stripe wires in
Phase 2). AGPL-3.0.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ------------------------------------------------------------------ config
PORT          = int(os.environ.get("RESTREAM_PORT", "3082"))
HOST          = os.environ.get("RESTREAM_HOST", "127.0.0.1")
PT_URL        = os.environ.get("PEERTUBE_URL", "http://127.0.0.1:3050").rstrip("/")
PT_HOST       = os.environ.get("PEERTUBE_HOST", "teknakul.com")
CORS_ORIGIN   = os.environ.get("RESTREAM_CORS_ORIGIN", "https://teknakul.com")
ADMIN_FILE    = os.environ.get("PEERTUBE_ADMIN_FILE", "/home/lacy/teknakul/.peertube-admin")
DB_PATH       = os.environ.get("RESTREAM_DB", "/home/lacy/teknakul/services/restream/restream.db")
SECRET_FILE   = os.environ.get("RESTREAM_SECRET_FILE", "/home/lacy/teknakul/services/restream/.secret")
ENT_FILE      = os.environ.get("RESTREAM_ENTITLEMENTS", "/home/lacy/teknakul/services/restream/entitlements.json")
POLL_SECONDS  = int(os.environ.get("RESTREAM_POLL", "15"))
GLOBAL_MAX_FANOUT = int(os.environ.get("RESTREAM_GLOBAL_MAX", "24"))  # safety cap on concurrent ffmpeg pushes

PLATFORMS = {
    "twitch":  "rtmp://live.twitch.tv/app/",
    "youtube": "rtmp://a.rtmp.youtube.com/live2/",
    "kick":    None,        # Kick gives a full rtmps ingest URL per user
    "custom":  None,
}

def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)

# ------------------------------------------------------------------ secret / crypto
def _load_secret():
    try:
        with open(SECRET_FILE, "rb") as f:
            return f.read().strip()
    except FileNotFoundError:
        s = base64.b64encode(os.urandom(32))
        os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, s); os.close(fd)
        return s

SECRET = _load_secret()

def _keystream(nonce, n):
    out, c = b"", 0
    while len(out) < n:
        out += hmac.new(SECRET, nonce + c.to_bytes(4, "big"), hashlib.sha256).digest()
        c += 1
    return out[:n]

def enc(plaintext):
    """Reversible stream cipher (HMAC keystream XOR) so keys aren't stored in the clear.
    NB: not authenticated; production should move to AES-GCM / a KMS."""
    data = plaintext.encode()
    nonce = os.urandom(12)
    ks = _keystream(nonce, len(data))
    ct = bytes(a ^ b for a, b in zip(data, ks))
    return base64.b64encode(nonce + ct).decode()

def dec(token):
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    ks = _keystream(nonce, len(ct))
    return bytes(a ^ b for a, b in zip(ct, ks)).decode()

# ------------------------------------------------------------------ db
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS destinations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            label TEXT NOT NULL,
            platform TEXT NOT NULL,
            rtmp_url TEXT NOT NULL,
            key_enc TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created TEXT NOT NULL DEFAULT (datetime('now')))""")

# ------------------------------------------------------------------ peertube api
def _req(url, data=None, headers=None, method=None, timeout=20):
    h = {"Accept": "application/json", "User-Agent": "TeknakulRestream/1.0"}
    if url.startswith(PT_URL):
        h["Host"] = PT_HOST
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.read()

def pt_get(path, token):
    raw = _req(PT_URL + path, headers={"Authorization": "Bearer " + token})
    return json.loads(raw) if raw else None

_admin = {"tok": None, "ts": 0}
def admin_token():
    if _admin["tok"] and time.time() - _admin["ts"] < 3000:
        return _admin["tok"]
    oc = json.loads(_req(PT_URL + "/api/v1/oauth-clients/local"))
    creds = {}
    with open(ADMIN_FILE) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                creds[k.strip()] = v.strip()
    form = urllib.parse.urlencode({
        "client_id": oc["client_id"], "client_secret": oc["client_secret"],
        "grant_type": "password", "response_type": "code",
        "username": creds["username"], "password": creds["password"],
    }).encode()
    raw = _req(PT_URL + "/api/v1/users/token", data=form,
               headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    _admin["tok"] = json.loads(raw)["access_token"]; _admin["ts"] = time.time()
    return _admin["tok"]

def whoami(user_token):
    """Resolve the caller from their PeerTube bearer token."""
    me = pt_get("/api/v1/users/me", user_token)
    return me.get("username") if me else None

# ------------------------------------------------------------------ entitlements
def entitlement(username):
    """Returns {'plan': str, 'max': int}. Sourced from a local file until Stripe (Phase 2).
    Default = free (no multistream)."""
    try:
        with open(ENT_FILE) as f:
            ent = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        ent = {}
    e = ent.get(username)
    if not e:
        return {"plan": "free", "max": 0}
    return {"plan": e.get("plan", "pro"), "max": int(e.get("max", 3))}

# ------------------------------------------------------------------ destinations
def dest_target(platform, rtmp_url, key):
    base = (rtmp_url or PLATFORMS.get(platform) or "").rstrip("/")
    return base + "/" + key

def list_dests(username, reveal=False):
    with db() as c:
        rows = c.execute("SELECT * FROM destinations WHERE username=? ORDER BY id", (username,)).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "label": r["label"], "platform": r["platform"],
            "rtmpUrl": r["rtmp_url"], "enabled": bool(r["enabled"]),
            "streamKey": (dec(r["key_enc"]) if reveal else "•••• saved"),
        })
    return out

# ------------------------------------------------------------------ fan-out engine
_procs = {}          # (video_uuid, dest_id) -> Popen
_procs_lock = threading.Lock()

def _spawn(video_uuid, dest_row, hls_url):
    key = (video_uuid, dest_row["id"])
    with _procs_lock:
        if key in _procs and _procs[key].poll() is None:
            return
        if sum(1 for p in _procs.values() if p.poll() is None) >= GLOBAL_MAX_FANOUT:
            log("global fan-out cap reached; skipping", key)
            return
        target = dest_target(dest_row["platform"], dest_row["rtmp_url"], dec(dest_row["key_enc"]))
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin",
               "-re", "-i", hls_url, "-c", "copy", "-f", "flv", target]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _procs[key] = p
            log(f"fan-out START {dest_row['label']} ({dest_row['platform']}) for live {video_uuid[:8]}")
        except Exception as e:  # noqa
            log("ffmpeg spawn error:", e)

def _kill_for_video(video_uuid):
    with _procs_lock:
        for key in [k for k in _procs if k[0] == video_uuid]:
            p = _procs.pop(key)
            if p.poll() is None:
                try: p.send_signal(signal.SIGTERM)
                except Exception: pass
            log("fan-out STOP", key)

def _active_lives(token):
    """Local live videos currently broadcasting (state Published=1)."""
    out = []
    d = pt_get("/api/v1/videos?isLive=true&count=50&nsfw=both&isLocal=true", token)
    for v in (d.get("data", []) if d else []):
        if (v.get("state", {}) or {}).get("id") == 1:
            out.append(v)
    return out

def engine_loop():
    log("fan-out engine started")
    while True:
        try:
            token = admin_token()
            live_now = _active_lives(token)
            live_uuids = set()
            for v in live_now:
                uuid = v["uuid"]
                live_uuids.add(uuid)
                owner = (v.get("account", {}) or {}).get("name")
                if not owner:
                    continue
                ent = entitlement(owner)
                if ent["max"] <= 0:
                    continue
                with db() as c:
                    dests = c.execute("SELECT * FROM destinations WHERE username=? AND enabled=1 ORDER BY id LIMIT ?",
                                      (owner, ent["max"])).fetchall()
                if not dests:
                    continue
                full = pt_get(f"/api/v1/videos/{uuid}", token)
                sp = (full.get("streamingPlaylists") or [])
                hls = sp[0]["playlistUrl"] if sp else None
                if not hls:
                    continue
                for d in dests:
                    _spawn(uuid, d, hls)
            # tear down fan-outs whose live has ended
            with _procs_lock:
                stale = {k[0] for k in _procs} - live_uuids
            for uuid in stale:
                _kill_for_video(uuid)
            # reap dead ffmpegs
            with _procs_lock:
                for k in [k for k, p in _procs.items() if p.poll() is not None]:
                    _procs.pop(k, None)
        except Exception as e:  # noqa
            log("engine error:", e)
        time.sleep(POLL_SECONDS)

def running_status(username):
    with _procs_lock:
        n = sum(1 for (u, d), p in _procs.items() if p.poll() is None)
    return {"activeFanouts": n}

# ------------------------------------------------------------------ http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, code, obj):
        payload = json.dumps(obj).encode()
        self.send_response(code); self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload))); self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204); self._cors()
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0"); self.end_headers()

    def _auth(self):
        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        if not tok:
            return None
        try:
            return whoami(tok)
        except urllib.error.HTTPError:
            return None

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._json(200, {"ok": True})
        user = self._auth()
        if not user:
            return self._json(401, {"error": "sign in required"})
        ent = entitlement(user)
        if u.path == "/destinations":
            return self._json(200, {"plan": ent["plan"], "max": ent["max"],
                                    "destinations": list_dests(user)})
        if u.path == "/status":
            return self._json(200, {"plan": ent["plan"], **running_status(user)})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        user = self._auth()
        if not user:
            return self._json(401, {"error": "sign in required"})
        ent = entitlement(user)
        body = self._body()
        if u.path == "/destinations":
            if ent["max"] <= 0:
                return self._json(403, {"error": "Multistream is a Pro feature. Upgrade to add destinations."})
            with db() as c:
                cnt = c.execute("SELECT COUNT(*) n FROM destinations WHERE username=?", (user,)).fetchone()["n"]
            if cnt >= ent["max"]:
                return self._json(403, {"error": f"Your plan allows {ent['max']} destinations. Add a Network add-on for more."})
            platform = (body.get("platform") or "custom").lower()
            key = (body.get("streamKey") or "").strip()
            rtmp = (body.get("rtmpUrl") or PLATFORMS.get(platform) or "").strip()
            label = (body.get("label") or platform.title()).strip()[:60]
            if not key or not rtmp or not rtmp.startswith(("rtmp://", "rtmps://")):
                return self._json(400, {"error": "A valid RTMP url and stream key are required."})
            with db() as c:
                c.execute("INSERT INTO destinations(username,label,platform,rtmp_url,key_enc,enabled) VALUES(?,?,?,?,?,1)",
                          (user, label, platform, rtmp, enc(key)))
            return self._json(200, {"ok": True, "destinations": list_dests(user)})
        m = re.match(r"^/destinations/(\d+)/toggle$", u.path)
        if m:
            did = int(m.group(1))
            with db() as c:
                r = c.execute("SELECT enabled FROM destinations WHERE id=? AND username=?", (did, user)).fetchone()
                if not r:
                    return self._json(404, {"error": "not found"})
                c.execute("UPDATE destinations SET enabled=? WHERE id=?", (0 if r["enabled"] else 1, did))
            return self._json(200, {"ok": True, "destinations": list_dests(user)})
        self._json(404, {"error": "not found"})

    def do_DELETE(self):
        u = urlparse(self.path)
        user = self._auth()
        if not user:
            return self._json(401, {"error": "sign in required"})
        m = re.match(r"^/destinations/(\d+)$", u.path)
        if m:
            with db() as c:
                c.execute("DELETE FROM destinations WHERE id=? AND username=?", (int(m.group(1)), user))
            return self._json(200, {"ok": True, "destinations": list_dests(user)})
        self._json(404, {"error": "not found"})

if __name__ == "__main__":
    init_db()
    threading.Thread(target=engine_loop, daemon=True).start()
    log(f"restream API on http://{HOST}:{PORT} (CORS {CORS_ORIGIN})")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
