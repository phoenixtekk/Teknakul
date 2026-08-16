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
import os
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import runbook_ai as R

PORT = int(os.environ.get("ASK_PORT", "3081"))
HOST = os.environ.get("ASK_HOST", "127.0.0.1")
# Browser origin(s) allowed to call this API (the platform front-end).
CORS_ORIGIN = os.environ.get("ASK_CORS_ORIGIN", "https://teknakul.com")

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

class Handler(BaseHTTPRequestHandler):
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
        if u.path == "/health":
            return self._send(200, {"ok": True})
        if u.path == "/ask":
            q = parse_qs(u.query)
            return self._handle((q.get("videoId") or [""])[0], (q.get("q") or [""])[0])
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
