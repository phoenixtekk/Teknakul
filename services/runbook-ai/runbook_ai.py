#!/usr/bin/env python3
"""
Teknakul Runbook Mode - AI chapters + summaries generator.

Reads each local video's auto-generated transcript (WebVTT caption produced by the
Whisper remote runner), sends it to the self-hosted Ollama box, and writes back:

  * native PeerTube **chapters** (timecoded navigation markers on the player timeline)
  * an **AI summary** section appended to the video description

Runs headless (cron every N minutes). Idempotent: a video is skipped once it already
has chapters, and processed UUIDs are recorded in a state file.

Stdlib only (urllib/json) - no pip installs. Part of Teknakul (AGPL-3.0).
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

# ---------------------------------------------------------------------------- config
# Call PeerTube on the loopback interface with a Host header - Cloudflare 403s direct
# external hits from the box, and this avoids a pointless round trip through the edge.
PEERTUBE_URL = os.environ.get("PEERTUBE_URL", "http://127.0.0.1:3050").rstrip("/")
PEERTUBE_HOST = os.environ.get("PEERTUBE_HOST", "teknakul.com")
ADMIN_FILE   = os.environ.get("PEERTUBE_ADMIN_FILE", "/home/lacy/teknakul/.peertube-admin")
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://192.168.166.182:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.3:70b")
STATE_FILE   = os.environ.get("RUNBOOK_STATE_FILE", "/home/lacy/teknakul/services/runbook-ai/state.json")
CAPTION_LANG = os.environ.get("RUNBOOK_CAPTION_LANG", "en")
SUMMARY_MARK = "<!-- teknakul-ai-summary -->"
HTTP_TIMEOUT = 30
OLLAMA_TIMEOUT = 600  # a 70B model over a long transcript can be slow

def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)

# ------------------------------------------------------------------------- http utils
def _req(url, data=None, headers=None, method=None, timeout=HTTP_TIMEOUT):
    h = {"Accept": "application/json", "User-Agent": "TeknakulRunbookAI/1.0"}
    # Inject the Host header for loopback calls to PeerTube (not for the Ollama box).
    if url.startswith(PEERTUBE_URL):
        h["Host"] = PEERTUBE_HOST
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read()
    return raw

def api_get(path, token):
    url = PEERTUBE_URL + path
    raw = _req(url, headers={"Authorization": "Bearer " + token})
    return json.loads(raw) if raw else None

def load_admin():
    creds = {}
    with open(ADMIN_FILE) as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    if not creds.get("username") or not creds.get("password"):
        raise SystemExit("admin creds file missing username/password: " + ADMIN_FILE)
    return creds["username"], creds["password"]

def get_token():
    """PeerTube OAuth password grant."""
    oc = api_get_public("/api/v1/oauth-clients/local")
    user, pw = load_admin()
    form = urllib.parse.urlencode({
        "client_id": oc["client_id"],
        "client_secret": oc["client_secret"],
        "grant_type": "password",
        "response_type": "code",
        "username": user,
        "password": pw,
    }).encode()
    raw = _req(PEERTUBE_URL + "/api/v1/users/token", data=form,
               headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    return json.loads(raw)["access_token"]

def api_get_public(path):
    raw = _req(PEERTUBE_URL + path)
    return json.loads(raw)

# ------------------------------------------------------------------------- vtt parsing
# Whisper emits HH:MM:SS.mmm for long clips and MM:SS.mmm for short ones - hours optional.
_TS = re.compile(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->")

def parse_vtt(text):
    """Return list of (start_seconds:int, text:str), merged & de-duplicated."""
    segments = []
    lines = text.replace("\r", "").split("\n")
    i = 0
    cur_start = None
    cur_text = []
    while i < len(lines):
        m = _TS.search(lines[i])
        if m:
            if cur_start is not None and cur_text:
                segments.append((cur_start, " ".join(cur_text).strip()))
            hh, mm, ss, _ms = m.groups()
            cur_start = int(hh or 0) * 3600 + int(mm) * 60 + int(ss)
            cur_text = []
        elif lines[i].strip() and cur_start is not None and "WEBVTT" not in lines[i] and not lines[i].strip().isdigit():
            cur_text.append(lines[i].strip())
        i += 1
    if cur_start is not None and cur_text:
        segments.append((cur_start, " ".join(cur_text).strip()))
    # drop consecutive duplicate text (whisper repeats)
    out = []
    last = None
    for s, t in segments:
        if t and t != last:
            out.append((s, t))
            last = t
    return out

def fmt_ts(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

# ------------------------------------------------------------------------- ollama call
PROMPT = """You are an assistant that structures technical tutorial videos for a platform \
called Teknakul (think YouTube for IT pros - Microsoft 365, Intune, Google Workspace, \
security, homelab, scripting).

Below is the timestamped transcript of a video titled "{title}" (duration {dur}s).

Produce STRICT JSON with exactly these keys:
  "summary": a concise 2-4 sentence summary of what the viewer will learn, plain text.
  "chapters": an array of 3-8 objects, each {{"timecode": <integer seconds>, "title": <short chapter title, <=60 chars>}}.

Rules for chapters:
- The first chapter MUST have timecode 0.
- timecodes are integer seconds, strictly increasing, unique, and less than {dur}.
- Base each chapter on an actual topic shift in the transcript; use the nearest transcript timestamp.
- Titles are specific (e.g. "Create the Conditional Access policy"), not generic ("Introduction" only for the first).
Return ONLY the JSON object, no prose, no markdown fences.

TRANSCRIPT:
{transcript}
"""

def ollama_structure(title, duration, segments):
    # Build a compact timestamped transcript, cap length to keep the prompt sane.
    lines = [f"[{fmt_ts(s)}] {t}" for s, t in segments]
    transcript = "\n".join(lines)
    if len(transcript) > 14000:
        transcript = transcript[:14000] + "\n...[truncated]"
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": PROMPT.format(title=title, dur=int(duration), transcript=transcript),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }).encode()
    raw = _req(OLLAMA_URL + "/api/generate", data=body,
               headers={"Content-Type": "application/json"}, method="POST",
               timeout=OLLAMA_TIMEOUT)
    resp = json.loads(raw)
    return json.loads(resp["response"])

def clean_chapters(chapters, duration):
    """Validate/normalize: unique increasing int timecodes in [0,duration), first=0."""
    seen = set()
    out = []
    for c in chapters or []:
        try:
            tc = int(round(float(c["timecode"])))
        except (KeyError, ValueError, TypeError):
            continue
        title = str(c.get("title", "")).strip()[:80]
        if not title:
            continue
        if tc < 0 or (duration and tc >= duration):
            continue
        if tc in seen:
            continue
        seen.add(tc)
        out.append({"timecode": tc, "title": title})
    out.sort(key=lambda c: c["timecode"])
    if not out:
        return []
    if out[0]["timecode"] != 0:
        # force a chapter at 0 so PeerTube shows the timeline from the start
        if 0 not in seen:
            out.insert(0, {"timecode": 0, "title": out[0]["title"]})
        else:
            out[0]["timecode"] = 0
    return out[:8]

# ----------------------------------------------------------------- peertube write-back
def put_chapters(video_id, token, chapters):
    body = json.dumps({"chapters": chapters}).encode()
    _req(f"{PEERTUBE_URL}/api/v1/videos/{video_id}/chapters", data=body,
         headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
         method="PUT")

def get_chapters(video_id, token):
    d = api_get(f"/api/v1/videos/{video_id}/chapters", token)
    return (d or {}).get("chapters", [])

def update_description(video_uuid, token, old_desc, summary):
    """Append/replace the AI-summary block in the description via multipart PUT."""
    old_desc = old_desc or ""
    block = f"{SUMMARY_MARK}\n\n✨ AI Summary\n{summary}"
    if SUMMARY_MARK in old_desc:
        new_desc = re.sub(re.escape(SUMMARY_MARK) + r".*", block, old_desc, flags=re.S)
    else:
        new_desc = (old_desc.rstrip() + "\n\n" + block).strip() if old_desc.strip() else block
    new_desc = new_desc[:9900]
    boundary = "----teknakulRunbookAI"
    parts = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="description"\r\n\r\n')
    parts.append(new_desc.encode("utf-8") + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    data = b"".join(parts)
    _req(f"{PEERTUBE_URL}/api/v1/videos/{video_uuid}", data=data,
         headers={"Authorization": "Bearer " + token,
                  "Content-Type": f"multipart/form-data; boundary={boundary}"},
         method="PUT")

# ----------------------------------------------------------------------- state / main
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"processed": []}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def list_local_videos(token):
    out = []
    start = 0
    while True:
        d = api_get(f"/api/v1/videos?count=50&start={start}&sort=-publishedAt&isLocal=true&nsfw=both", token)
        data = d.get("data", [])
        out.extend(data)
        start += 50
        if start >= d.get("total", 0) or not data:
            break
    return out

def process_video(v, token, state, force=False):
    vid = v["uuid"]
    name = v.get("name", "")[:60]
    if not force and vid in state["processed"]:
        return "skip(state)"
    if not force and get_chapters(vid, token):
        state["processed"].append(vid)
        return "skip(has-chapters)"
    caps = api_get(f"/api/v1/videos/{vid}/captions", token).get("data", [])
    cap = next((c for c in caps if c.get("language", {}).get("id") == CAPTION_LANG), None)
    if not cap:
        return "skip(no-caption)"
    # Prefer the relative captionPath against the loopback base (fileUrl may point at the CDN).
    cap_url = (PEERTUBE_URL + cap["captionPath"]) if cap.get("captionPath") else cap.get("fileUrl")
    vtt = _req(cap_url).decode("utf-8", "replace")
    segs = parse_vtt(vtt)
    if not segs:
        return "skip(empty-transcript)"
    full = api_get(f"/api/v1/videos/{vid}", token)
    duration = full.get("duration") or (segs[-1][0] + 5)
    log(f"  -> LLM structuring '{name}' ({len(segs)} segments, {duration}s)")
    result = ollama_structure(v.get("name", ""), duration, segs)
    chapters = clean_chapters(result.get("chapters", []), duration)
    summary = str(result.get("summary", "")).strip()
    if chapters:
        put_chapters(vid, token, chapters)
    if summary:
        update_description(vid, token, full.get("description", ""), summary)
    state["processed"].append(vid)
    return f"OK ({len(chapters)} chapters, summary={'y' if summary else 'n'})"

def main(argv):
    force = "--force" in argv
    only = None
    for a in argv:
        if a.startswith("--video="):
            only = a.split("=", 1)[1]
    token = get_token()
    state = load_state()
    if only:
        # Fetch directly - the published-videos list omits still-transcoding uploads.
        videos = [api_get(f"/api/v1/videos/{only}", token)]
    else:
        videos = list_local_videos(token)
    log(f"Scanning {len(videos)} local video(s)")
    for v in videos:
        try:
            r = process_video(v, token, state, force=force)
            log(f"[{v['uuid']}] {v.get('name','')[:50]!r}: {r}")
        except urllib.error.HTTPError as e:
            log(f"[{v['uuid']}] HTTP {e.code}: {e.read()[:200]}")
        except Exception as e:  # noqa
            log(f"[{v['uuid']}] ERROR: {e}")
        save_state(state)
    log("Done.")

if __name__ == "__main__":
    main(sys.argv[1:])
