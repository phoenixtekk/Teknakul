#!/usr/bin/env python3
"""
Teknakul AI Clips — auto-cut shareable highlight clips from a VOD.

Reads a video's Whisper transcript, asks Ollama to pick the most clippable moments,
cuts each with ffmpeg from the VOD's HLS source, and uploads them back as short videos
(unlisted, for the creator to review/publish). Foundation for feature #2 (AI clips).

Usage: python3 clips.py <video-uuid> [--max N] [--publish]
Stdlib + ffmpeg. AGPL-3.0.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import uuid as uuidlib

sys.path.insert(0, "/home/lacy/teknakul/services/runbook-ai")
import runbook_ai as R  # token / api / vtt helpers

MIN_CLIP = 8
MAX_CLIP = 60

HIGHLIGHT_PROMPT = """You are a social-clips editor for Teknakul (video for technical people, \
gamers, and news). Below is the timestamped transcript of "{title}" (duration {dur}s).

Pick the {n} most engaging, self-contained moments to cut into short clips.
Each clip must be between %d and %d seconds long and start/end on a natural boundary.
Return STRICT JSON: {{"clips":[{{"start":<int s>,"end":<int s>,"title":<catchy <=70 chars>,"hook":<one-line reason it's clippable>}}]}}
Return ONLY the JSON, no prose.

TRANSCRIPT:
{transcript}
""" % (MIN_CLIP, MAX_CLIP)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def get_segments(vid, tok):
    caps = R.api_get(f"/api/v1/videos/{vid}/captions", tok).get("data", [])
    cap = next((c for c in caps if c.get("language", {}).get("id") == "en"), None)
    if not cap:
        return None
    url = (R.PEERTUBE_URL + cap["captionPath"]) if cap.get("captionPath") else cap.get("fileUrl")
    return R.parse_vtt(R._req(url).decode("utf-8", "replace"))


def pick_highlights(name, duration, segments, n):
    transcript = "\n".join(f"[{R.fmt_ts(s)}] {t}" for s, t in segments)[:14000]
    prompt = HIGHLIGHT_PROMPT.format(title=name, dur=int(duration), n=n, transcript=transcript)
    body = json.dumps({"model": R.OLLAMA_MODEL, "prompt": prompt, "stream": False,
                       "format": "json", "options": {"temperature": 0.3}}).encode()
    raw = R._req(R.OLLAMA_URL + "/api/generate", data=body,
                 headers={"Content-Type": "application/json"}, method="POST", timeout=R.OLLAMA_TIMEOUT)
    clips = json.loads(json.loads(raw)["response"]).get("clips", [])
    out = []
    for c in clips:
        try:
            s = max(0, int(c["start"])); e = int(c["end"])
        except (KeyError, ValueError, TypeError):
            continue
        if e <= s:
            continue
        e = min(e, s + MAX_CLIP, int(duration))
        if e - s < MIN_CLIP:
            e = min(s + MIN_CLIP, int(duration))
        if e - s < 4:
            continue
        out.append({"start": s, "end": e, "title": str(c.get("title", "")).strip()[:100] or "Highlight",
                    "hook": str(c.get("hook", "")).strip()[:160]})
    return out[:n]


def hls_source(vid, tok):
    """Return (source_url, host_header). Cloudflare blocks local video segments, so for
    locally-served HLS we hit the loopback with a Host header; R2-served HLS is public."""
    from urllib.parse import urlparse
    full = R.api_get(f"/api/v1/videos/{vid}", tok)
    sp = full.get("streamingPlaylists") or []
    if not sp:
        return None, None, full
    url = sp[0]["playlistUrl"]
    p = urlparse(url)
    if p.netloc == R.PEERTUBE_HOST:            # local static -> loopback + Host header
        return (R.PEERTUBE_URL + p.path), R.PEERTUBE_HOST, full
    return url, None, full                      # R2/CDN -> reachable as-is


def cut_clip(hls, start, dur, out_path, host=None, vertical=False):
    vf = ("scale=-2:1920,crop=1080:1920" if vertical else "scale=-2:720")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if host:
        cmd += ["-headers", "Host: " + host + "\r\n"]
    cmd += ["-ss", str(start), "-i", hls, "-t", str(dur),
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True)


def upload_clip(path, name, channel_id, tok, publish=False):
    b = "----clip" + uuidlib.uuid4().hex

    def field(nm, v):
        return (f"--{b}\r\nContent-Disposition: form-data; name=\"{nm}\"\r\n\r\n{v}\r\n").encode()
    with open(path, "rb") as f:
        data = f.read()
    parts = [field("name", name), field("channelId", str(channel_id)),
             field("privacy", "1" if publish else "2")]  # 1=public, 2=unlisted
    parts.append((f"--{b}\r\nContent-Disposition: form-data; name=\"videofile\"; "
                  f"filename=\"clip.mp4\"\r\nContent-Type: video/mp4\r\n\r\n").encode())
    parts.append(data + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    raw = R._req(R.PEERTUBE_URL + "/api/v1/videos/upload", data=b"".join(parts),
                 headers={"Authorization": "Bearer " + tok,
                          "Content-Type": f"multipart/form-data; boundary={b}"},
                 method="POST", timeout=180)
    return json.loads(raw)["video"]


def main(argv):
    if not argv:
        print("usage: clips.py <video-uuid> [--max N] [--publish] [--vertical]"); return 1
    vid = argv[0]
    n = 2
    if "--max" in argv:
        n = int(argv[argv.index("--max") + 1])
    publish = "--publish" in argv
    vertical = "--vertical" in argv
    tok = R.get_token()
    segs = get_segments(vid, tok)
    if not segs:
        log("no transcript for", vid); return 1
    hls, host, full = hls_source(vid, tok)
    if not hls:
        log("no HLS source for", vid); return 1
    duration = full.get("duration") or (segs[-1][0] + 5)
    channel_id = full["channel"]["id"]
    log(f"picking up to {n} highlights from {full.get('name','')!r} ({duration}s)")
    clips = pick_highlights(full.get("name", ""), duration, segs, n)
    if not clips:
        log("no highlights chosen"); return 1
    made = []
    for i, c in enumerate(clips, 1):
        dur = c["end"] - c["start"]
        log(f"  clip {i}: {c['start']}s-{c['end']}s ({dur}s) — {c['title']!r}")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
            out = tf.name
        try:
            cut_clip(hls, c["start"], dur, out, host=host, vertical=vertical)
            sz = os.path.getsize(out)
            v = upload_clip(out, "✂ " + c["title"], channel_id, tok, publish=publish)
            made.append({"uuid": v["uuid"], "title": c["title"], "bytes": sz, **c})
            log(f"     -> uploaded {v['uuid'][:8]} ({sz} bytes)")
        finally:
            try: os.unlink(out)
            except OSError: pass
    print(json.dumps({"source": vid, "clips": made}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
