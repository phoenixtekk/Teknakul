#!/usr/bin/env python3
"""
Teknakul Runbook Mode - transcript embedding indexer (library-wide search).

Fetches every local video's Whisper transcript, splits it into ~short windows,
embeds each window with the self-hosted `nomic-embed-text` model on the Ollama box,
and writes rag_index.json. The ask-server's /search endpoint loads that index and
does cosine similarity against a query embedding (semantic transcript search).

Run via cron (e.g. hourly) or after a batch of uploads. Stdlib only. AGPL-3.0.
"""

import json
import os
import sys
import time

import runbook_ai as R
import ask_server as A

OUT = os.environ.get("RAG_INDEX_FILE", A.INDEX_FILE)
WINDOW_SECONDS = int(os.environ.get("RAG_WINDOW_SECONDS", "45"))
WINDOW_CHARS = int(os.environ.get("RAG_WINDOW_CHARS", "320"))

def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)

def windows(segments):
    """Group consecutive segments into ~WINDOW_SECONDS / WINDOW_CHARS chunks."""
    out = []
    cur, start = [], None
    for s, t in segments:
        if start is None:
            start = s
        cur.append(t)
        if (s - start) >= WINDOW_SECONDS or len(" ".join(cur)) >= WINDOW_CHARS:
            out.append((start, " ".join(cur).strip()))
            cur, start = [], None
    if cur:
        out.append((start or 0, " ".join(cur).strip()))
    return out

def list_indexable(token):
    """All instance-owned videos that are public (1) or unlisted (2) - skips private/internal."""
    out, start = [], 0
    while True:
        d = R.api_get(f"/api/v1/users/me/videos?count=50&start={start}", token)
        for v in d.get("data", []):
            if (v.get("privacy") or {}).get("id") in (1, 2):
                out.append(v)
        start += 50
        if start >= d.get("total", 0) or not d.get("data"):
            break
    return out

def main():
    token = R.get_token()
    videos = list_indexable(token)
    items = []
    for v in videos:
        vid = v["uuid"]
        try:
            segs = A.get_segments(vid, token)
        except Exception as e:  # noqa
            log(f"[{vid}] segments error: {e}")
            continue
        if not segs:
            continue
        name = v.get("name", "")
        wins = windows(segs)
        log(f"[{name[:40]!r}] {len(wins)} chunks")
        for tc, text in wins:
            if not text:
                continue
            try:
                vec = A.embed(f"{name}\n{text}")
            except Exception as e:  # noqa
                log(f"  embed error @ {tc}s: {e}")
                continue
            if vec:
                items.append({"videoId": vid, "shortUUID": v.get("shortUUID"),
                              "name": name, "timecode": int(tc), "text": text, "vec": vec})
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"built": None, "count": len(items), "items": items}, f)
    os.replace(tmp, OUT)
    log(f"Wrote {len(items)} chunks -> {OUT}")

if __name__ == "__main__":
    sys.exit(main())
