#!/usr/bin/env python3
"""
Teknakul Runbook Mode - "Ask this video" co-pilot API.

A tiny HTTP service (stdlib only) that answers a viewer's question about ONE video
using its Whisper transcript, via the self-hosted Ollama box. Returns a concise
answer, the most-relevant timecode (so the player can jump there), and a short quote.

Endpoints:
  GET  /health                       -> {"ok":true}
  GET  /ask?videoId=<uuid>&q=<text>  -> answer JSON (handy for testing)
  POST /ask  {videoId, question}     -> answer JSON

Response: {"answer": str, "timecode": int seconds, "quote": str, "found": bool}

Runs under systemd on linuxg1; exposed via a Cloudflare route so the watch-page
plugin can call it. Reuses runbook_ai.py for auth/transcript plumbing. AGPL-3.0.
"""

import json
import math
import os
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import runbook_ai as R

PORT = int(os.environ.get("ASK_PORT", "3081"))
HOST = os.environ.get("ASK_HOST", "127.0.0.1")
# Browser origin(s) allowed to call this API (the platform front-end).
CORS_ORIGIN = os.environ.get("ASK_CORS_ORIGIN", "https://teknakul.com")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text:latest")
INDEX_FILE = os.environ.get("RAG_INDEX_FILE",
                            "/home/lacy/teknakul/services/runbook-ai/rag_index.json")

ASK_PROMPT = """You are a co-pilot for a technical tutorial video on Teknakul. Answer the \
viewer's question using ONLY the transcript below. The transcript is timestamped as [mm:ss].

Rules:
- Answer concisely and practically (2-5 sentences), in plain text.
- Pick the SINGLE most relevant moment and return its timecode as integer seconds.
- Include a short verbatim quote (<=120 chars) from the transcript near that moment.
- If the transcript does not contain the answer, set "found" to false, still answer helpfully
  from general knowledge but say it wasn't covered in the video, and set timecode to 0.
Return STRICT JSON: {"answer": string, "timecode": integer, "quote": string, "found": boolean}
Return ONLY the JSON, no markdown fences.

QUESTION: {question}

TRANSCRIPT:
{transcript}
"""

# cache the admin token across requests; refresh on auth failure
_token = {"v": None}

def _get_token(force=False):
    if force or not _token["v"]:
        _token["v"] = R.get_token()
    return _token["v"]

def get_segments(video_id, token):
    caps = R.api_get(f"/api/v1/videos/{video_id}/captions", token).get("data", [])
    cap = next((c for c in caps if c.get("language", {}).get("id") == R.CAPTION_LANG), None)
    if not cap:
        return None
    url = (R.PEERTUBE_URL + cap["captionPath"]) if cap.get("captionPath") else cap.get("fileUrl")
    vtt = R._req(url).decode("utf-8", "replace")
    return R.parse_vtt(vtt)

def answer_question(video_id, question):
    token = _get_token()
    try:
        segs = get_segments(video_id, token)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            token = _get_token(force=True)
            segs = get_segments(video_id, token)
        else:
            raise
    if not segs:
        return {"answer": "This video doesn't have a transcript yet - check back after processing.",
                "timecode": 0, "quote": "", "found": False}
    lines = [f"[{R.fmt_ts(s)}] {t}" for s, t in segs]
    transcript = "\n".join(lines)
    if len(transcript) > 14000:
        transcript = transcript[:14000] + "\n...[truncated]"
    body = json.dumps({
        "model": R.OLLAMA_MODEL,
        "prompt": ASK_PROMPT.replace("{question}", question).replace("{transcript}", transcript),
        "stream": False, "format": "json", "options": {"temperature": 0.2},
    }).encode()
    raw = R._req(R.OLLAMA_URL + "/api/generate", data=body,
                 headers={"Content-Type": "application/json"}, method="POST",
                 timeout=R.OLLAMA_TIMEOUT)
    out = json.loads(json.loads(raw)["response"])
    # normalize
    try:
        tc = max(0, int(round(float(out.get("timecode", 0)))))
    except (ValueError, TypeError):
        tc = 0
    return {"answer": str(out.get("answer", "")).strip(),
            "timecode": tc,
            "quote": str(out.get("quote", "")).strip()[:200],
            "found": bool(out.get("found", True))}

COMMANDS_PROMPT = """From the transcript of a technical tutorial below, extract every \
command-line command, PowerShell cmdlet, shell/CLI invocation, or short code snippet that is \
mentioned or demonstrated. Reconstruct them into their most likely correct, runnable form.

Return STRICT JSON: {"commands": [{"command": string, "description": short string, "timecode": integer seconds}]}
- Only include real, runnable commands actually referenced in the transcript.
- "timecode" = the transcript second where the command is discussed.
- If there are no commands, return {"commands": []}.
Return ONLY the JSON, no markdown fences.

TRANSCRIPT:
{transcript}
"""

def extract_commands(video_id):
    token = _get_token()
    try:
        segs = get_segments(video_id, token)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            segs = get_segments(video_id, _get_token(force=True))
        else:
            raise
    if not segs:
        return {"commands": []}
    transcript = "\n".join(f"[{R.fmt_ts(s)}] {t}" for s, t in segs)[:14000]
    body = json.dumps({
        "model": R.OLLAMA_MODEL,
        "prompt": COMMANDS_PROMPT.replace("{transcript}", transcript),
        "stream": False, "format": "json", "options": {"temperature": 0.1},
    }).encode()
    raw = R._req(R.OLLAMA_URL + "/api/generate", data=body,
                 headers={"Content-Type": "application/json"}, method="POST",
                 timeout=R.OLLAMA_TIMEOUT)
    out = json.loads(json.loads(raw)["response"])
    cmds = []
    for c in (out.get("commands") or []):
        cmd = str(c.get("command", "")).strip()
        if not cmd:
            continue
        try:
            tc = max(0, int(round(float(c.get("timecode", 0)))))
        except (ValueError, TypeError):
            tc = 0
        cmds.append({"command": cmd, "description": str(c.get("description", "")).strip()[:160],
                     "timecode": tc})
    return {"commands": cmds}

# ---- library-wide transcript search (RAG over embeddings) --------------------
_index = {"mtime": 0, "items": []}

def embed(text):
    body = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    raw = R._req(R.OLLAMA_URL + "/api/embeddings", data=body,
                 headers={"Content-Type": "application/json"}, method="POST", timeout=120)
    return json.loads(raw).get("embedding") or []

def _load_index():
    try:
        m = os.path.getmtime(INDEX_FILE)
    except OSError:
        _index["items"] = []
        return _index["items"]
    if m != _index["mtime"]:
        with open(INDEX_FILE) as f:
            _index["items"] = json.load(f).get("items", [])
        _index["mtime"] = m
    return _index["items"]

def _cos(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

def search(query, k=8):
    items = _load_index()
    if not items:
        return {"results": [], "indexed": 0}
    qv = embed(query)
    scored = sorted(((_cos(qv, it["vec"]), it) for it in items),
                    key=lambda x: x[0], reverse=True)
    results = []
    for score, it in scored[:k]:
        results.append({"videoId": it["videoId"], "name": it["name"],
                        "shortUUID": it.get("shortUUID"), "timecode": it["timecode"],
                        "text": it["text"], "score": round(float(score), 3)})
    return {"results": results, "indexed": len(items)}


PLATFORM_URL = os.environ.get("PLATFORM_URL", "https://teknakul.com")

SEARCH_UI = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Teknakul - Transcript Search</title><style>
:root{--teal:#27d3c1}*{box-sizing:border-box}
body{margin:0;background:#080f0f;color:#eafaf8;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;padding:26px}
.wrap{max-width:760px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}.sub{color:#8fb6b1;font-size:14px;margin-bottom:18px}
.bar{display:flex;gap:8px}input{flex:1;padding:12px 14px;border-radius:11px;border:1px solid rgba(39,211,193,.3);background:#0f1b1b;color:#eafaf8;font-size:15px;outline:none}
button{padding:12px 22px;border:none;border-radius:11px;background:var(--teal);color:#04100e;font-weight:700;cursor:pointer;font-size:15px}
.r{display:block;margin-top:14px;padding:14px 16px;border:1px solid rgba(39,211,193,.16);border-radius:12px;background:#0f1b1b;text-decoration:none;color:inherit;transition:.15s}
.r:hover{border-color:var(--teal);transform:translateY(-2px)}
.r .t{font-weight:650;color:var(--teal)}.r .tc{font-size:12px;color:#8fb6b1;font-variant-numeric:tabular-nums}
.r .x{color:#cfe;opacity:.85;font-size:14px;margin-top:6px}.muted{color:#8fb6b1;margin-top:16px}
</style></head><body><div class=wrap>
<h1>&#128269; Transcript Search</h1><div class=sub>Search every Teknakul video by what was actually said - land on the exact moment.</div>
<div class=bar><input id=q placeholder="e.g. reset MFA for a locked-out admin" autofocus><button onclick=go()>Search</button></div>
<div id=out></div></div><script>
var PLATFORM=%PLATFORM%;
function fmt(s){s=parseInt(s,10)||0;var m=Math.floor(s/60),x=s%60;return m+':'+String(x).padStart(2,'0')}
async function go(){var q=document.getElementById('q').value.trim();var out=document.getElementById('out');if(!q)return;
out.innerHTML='<div class=muted>Searching...</div>';
try{var res=await fetch('/search?q='+encodeURIComponent(q)+'&k=12');var d=await res.json();
if(!d.results||!d.results.length){out.innerHTML='<div class=muted>No matches'+(d.indexed?'':' - the index is empty, upload a video with speech first')+'.</div>';return}
out.innerHTML=d.results.map(function(r){var u=PLATFORM+'/w/'+(r.shortUUID||r.videoId)+'?start='+r.timecode;
return '<a class=r href="'+u+'"><span class=t>'+r.name+'</span> <span class=tc>@ '+fmt(r.timecode)+'</span><div class=x>'+r.text.replace(/</g,'&lt;').slice(0,220)+'</div></a>'}).join('')}
catch(e){out.innerHTML='<div class=muted>Search unavailable.</div>'}}
document.getElementById('q').addEventListener('keydown',function(e){if(e.key==='Enter')go()});
</script></body></html>""".replace("%PLATFORM%", json.dumps(PLATFORM_URL))


class Handler(BaseHTTPRequestHandler):
    def _send_html(self, html):
        payload = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send(self, code, obj):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):  # quieter logs
        pass

    def do_OPTIONS(self):
        self._send(204, {})

    def _handle(self, video_id, question):
        if not video_id or not question:
            return self._send(400, {"error": "videoId and question are required"})
        try:
            self._send(200, answer_question(video_id, question))
        except Exception as e:  # noqa
            self._send(500, {"error": str(e)})

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/search-ui"):
            return self._send_html(SEARCH_UI)
        if u.path == "/health":
            return self._send(200, {"ok": True})
        if u.path == "/ask":
            return self._handle((q.get("videoId") or [""])[0], (q.get("q") or [""])[0])
        if u.path == "/commands":
            vid = (q.get("videoId") or [""])[0]
            if not vid:
                return self._send(400, {"error": "videoId is required"})
            try:
                return self._send(200, extract_commands(vid))
            except Exception as e:  # noqa
                return self._send(500, {"error": str(e)})
        if u.path == "/search":
            query = (q.get("q") or [""])[0].strip()
            if not query:
                return self._send(400, {"error": "q is required"})
            try:
                return self._send(200, search(query, int((q.get("k") or ["8"])[0])))
            except Exception as e:  # noqa
                return self._send(500, {"error": str(e)})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/ask":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "invalid JSON body"})
        self._handle(data.get("videoId", ""), data.get("question", ""))

if __name__ == "__main__":
    print(f"ask-server on http://{HOST}:{PORT} (CORS: {CORS_ORIGIN})", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
