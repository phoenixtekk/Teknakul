# Teknakul — Admin & Operator Documentation

Operator runbook for the **PeerTube 7.3.0** deployment. Living document.

---

## 0. Deployment: linuxg1

**Location:** `/home/lacy/teknakul/` on **linuxg1** · **Stack:** Docker Compose (`sudo docker compose`)

| Item | Value |
|---|---|
| Public URL (**PERMANENT**) | `https://teknakul.com` (apex; channel handles `@name@teknakul.com`) |
| App container | `teknakul-peertube` (`chocobozzz/peertube:v7.3.0-bookworm`) → **127.0.0.1:3050** |
| Database | `teknakul-pg` (`postgres:17-alpine`) — container-internal, no host port |
| Cache | `teknakul-redis` (`redis:7-alpine`) — container-internal, no host port |
| Config/secrets | `.env` (mode 600) |
| Root admin | `.peertube-admin` (mode 600) — password rotated after first-boot leak |
| Data/config dirs | `./data`, `./config` (owned **uid 999** = in-container `peertube` user) |
| Resource caps | peertube 2.5 CPU / 6 GB · pg 1.0 / 2 GB · redis 512 MB |

### Why standalone (no bundled nginx/certbot)
TLS terminates at Cloudflare; the box can't take another 80/443 binding. We run only the app container
behind the existing tunnel `teknakul.com → :3050`. Own Postgres + Redis so it never touches the shared
host PostgreSQL (mibrow/tekkops) or Zammad's Redis.

### Operate
```bash
cd /home/lacy/teknakul && sudo docker compose {ps|logs -f peertube|restart|pull|up -d|down}
```
Upgrade: bump the pinned tag in `compose.yml`, `sudo docker compose pull peertube && up -d`. Read
PeerTube release notes first; migrations run automatically on boot.

### Admin API (for config changes without the UI)
Get a token (must send `Host: teknakul.com` or PeerTube 403s local calls):
```bash
# oauth-clients/local → users/token (grant_type=password, username=root, password from .peertube-admin)
```
Then `PUT /api/v1/config/custom` (GET → merge → PUT the FULL object) for instance settings, or the
UI at `teknakul.com/admin`.

---

## 1. ⚠️ Permanent hostname
`teknakul.com` is the federation identity — baked into federated data on remote servers. **Never**
change it and **never** redirect the apex. `www.teknakul.com` is a separate concern (redirect to apex).

## 2. Front door (marketing landing)
The apex shows a custom marketing homepage (Option A), stored via
`PUT /api/v1/custom-pages/homepage/instance` (`{content: "<html>"}`), with the landing route set to
`/home` (`instance.defaultClientRoute` in config/custom). PeerTube sanitizes homepage HTML to an
allowlist — class attributes survive; style reusable classes in Admin → Config → Appearance CSS.

## 3. Transcoding (tuned 2026-08-11)
`threads: 2`, `concurrency: 1`, **HLS-only** (`webVideos.enabled: false`), resolutions **360/480/720/
1080** (144p/240p/1440p/2160p off), `alwaysTranscodeOriginalResolution: true`. Rationale: concurrency 1
bounds peak CPU to one job on a shared 4-vCPU box; HLS-only halves transcode work. **Scale path:** turn
on **remote runners** (Admin → System → Runners) to offload transcoding to a separate machine.

## 4. Object storage — Cloudflare R2 (⬜ REQUIRED before real video traffic)
Video **must** be served from R2, not the tunnel (Cloudflare CDN forbids serving video off-CF; the
shared tunnel must not carry video bytes). Config via `PEERTUBE_OBJECT_STORAGE_*` in `.env` (endpoint,
bucket names for web-videos + streaming-playlists, access key/secret, `BASE_URL` = the R2 public URL),
then `docker compose up -d`. Until wired, keep video traffic to test-only.

## 5. Email — Amazon SES (⬜ pending)
Wire `PEERTUBE_SMTP_HOSTNAME` (`email-smtp.<region>.amazonaws.com`), `_PORT=587`, `_USERNAME`,
`_PASSWORD`, `_TLS=true`, `_FROM=<verified sender>` in `.env` → `up -d`. Without SMTP, PeerTube logs
"lack of configuration" and can't send verification/notification email.

## 6. Auth — Microsoft + Google (⬜ pending)
Install `peertube-plugin-auth-openid-connect` (Admin → Plugins), configure each provider's discovery
URL + client id/secret; redirect URI `https://teknakul.com/plugins/auth-openid-connect/router/code-cb`.
**Note:** the plugin is single-provider — two providers (MS + Google) may need two plugin packages;
validate before finalizing. Aigartha ID added later the same way. Native email/password stays as fallback.

## 7. Live streaming (⬜ Phase 2)
RTMP ingest (:1935) can't cross the HTTP tunnel. Requires: owner UniFi port-forward WAN TCP 1935 →
linuxg1; a **DNS-only** `ingest.teknakul.com` A-record → public IP; open firewalld :1935 on linuxg1;
map `1935:1935` in compose; enable Live in Admin → Config → Live. Live HLS playback also via R2.

## 8. Backups
Back up **before** any destructive op. Postgres: `sudo docker compose exec -T postgres pg_dump -U
teknakul peertube | gzip > backup.sql.gz`. Data: `./data` (local video/thumbnails until R2). `.env` +
`.peertube-admin` hold secrets — back them up securely, never commit.

## 9. AGPL-3.0 (⬜ before public launch)
Members use it over the network → must publish the modified source under AGPL and link it from the
instance. Keep any external services (AI transcripts/co-pilot) as separate processes outside the tree.

## 10. Federation & moderation
PeerTube federates (ActivityPub). Admin → moderation tools: instance follows/followers, blocklists,
video/comment moderation, abuse reports. **Staff moderation before opening signups.**

## 10a. Live streaming (OBS / RTMP) — ENABLED
Live is enabled (`live.enabled=true`, `allowReplay=true`, maxInstanceLives 3 / maxUserLives 1).
RTMP ingest listens on **:1935** (container `0.0.0.0:1935`), exposed publicly via the owner's UniFi
port‑forward to **`ingest.teknakul.com`** (DNS‑only A record → `38.188.128.3`, **not** Cloudflare‑proxied
— RTMP can't traverse the HTTP tunnel). Verified reachable from the public internet.

- **RTMP URL (OBS "Server"):** `rtmp://ingest.teknakul.com:1935/live`
- **Stream key:** per‑live, generated when a creator makes a "Go live" video (Publish → Go live).
- **OBS:** Settings → Stream → Service **Custom** → Server = the RTMP URL → Stream Key = the key.
- **Encoder guidance (passthrough):** CBR, 3000–6000 Kbps, **keyframe interval 2s**, 720p/1080p, AAC 128k.
- **Live transcoding is OFF** (passthrough = single quality, lowest latency). For Twitch‑style adaptive
  multi‑resolution, enable `live.transcoding` and offload to the AI‑box remote runner.
- ⚠️ `PEERTUBE_LIVE_RTMP_PUBLIC_HOSTNAME=ingest.teknakul.com` must keep its DNS‑only record + the UniFi
  WAN TCP 1935 → linuxg1 forward. `teknakul.com:1935` is intentionally NOT reachable (proxied).

## 11. Fleet hygiene
This is a shared production box. Never restart/delete another project's container. After any infra
change, update `~/.claude/server-inventory.md` (linuxg1 section + "Last verified") and re-publish the
wiki copy (`SystemDocs/linuxg-fleet-inventory`).

## 12. Runbook Mode AI service (chapters + summaries)
`/home/lacy/teknakul/services/runbook-ai/runbook_ai.py` (stdlib Python 3, no deps). For each local
video with an English Whisper caption and no chapters, it fetches the VTT, sends it to the **Ollama box
`http://192.168.166.182:11434` (`llama3.3:70b`)**, and writes native PeerTube **chapters** plus an AI
**summary** (appended to the description behind a `<!-- teknakul-ai-summary -->` marker) via the local
API (`http://127.0.0.1:3050` + `Host: teknakul.com`). Idempotent — processed UUIDs recorded in
`state.json`; a video with chapters is skipped.

- **Schedule:** cron for user `lacy`, `*/10 * * * *` → `services/runbook-ai/runbook.log`.
- **Manual run:** `cd .../runbook-ai && python3 runbook_ai.py` (all pending) · `--video=<uuid>` (one) ·
  `--force` (re-process even if chapters exist).
- **Config via env:** `OLLAMA_URL`, `OLLAMA_MODEL`, `PEERTUBE_URL`, `PEERTUBE_HOST`, `PEERTUBE_ADMIN_FILE`.
- **Creds:** PeerTube admin from `/home/lacy/teknakul/.peertube-admin` (mode 600). No secrets in the repo.
- **Depends on:** the transcription runner (AI box `.168`) producing the caption first; and the Ollama
  box `.182` being reachable from linuxg1 (private LAN). If either is down, videos are simply skipped and
  retried next run.
- **Troubleshoot:** `skip(no-caption)` = transcript not ready yet (runner still working); `skip(empty-
  transcript)` = VTT parsed empty (check caption content); HTTP 403 = calling through the edge instead of
  loopback (must use `127.0.0.1:3050` + Host header).

### 12a. "Ask this video" co-pilot (API + watch-page plugin)
`services/runbook-ai/ask_server.py` — a stdlib HTTP API (systemd **`teknakul-ask.service`**, **:3081**)
that answers a question about ONE video from its transcript via Ollama and returns
`{answer, timecode, quote, found}`. Endpoints: `GET /health`, `GET /ask?videoId=&q=`,
`POST /ask {videoId,question}`. CORS locked to `https://teknakul.com` (`ASK_CORS_ORIGIN`).
Manage: `sudo systemctl {status|restart} teknakul-ask`.

The watch-page UI is the plugin **`peertube-plugin-teknakul-runbook`** (client scope `video-watch`):
it injects an "✨ Ask this video" panel, calls the API, and seeks the player to the returned timecode.
The plugin calls **`https://runbook.teknakul.com`** by default (override at runtime via
`window.TEKNAKUL_ASK_API`).

**Live:** CF route `runbook.teknakul.com → http://localhost:3081` is in place; verified public
(health 200, `/ask` returns answers + jump timecodes with the correct CORS header).

### 12b. Copyable commands + library-wide transcript search
Same `teknakul-ask` service (:3081) also serves:
- **`GET /commands?videoId=`** — extracts runnable commands/cmdlets from the transcript via Ollama
  (`{commands:[{command,description,timecode}]}`). Surfaced by the runbook plugin's watch-page
  "⌨️ Commands in this video" panel (copy buttons + jump). Verified (reconstructs
  `Connect-MgGraph -Scope …`, `Get-MgUser -All`, `docker compose up -d --build`, `az login`).
- **`GET /search?q=&k=`** — semantic transcript search. Cosine similarity of the query embedding
  against `rag_index.json` (built by `rag_index.py` → `nomic-embed-text` on `.182`, chunked ~45s/320c).
  Returns `{results:[{name,shortUUID,timecode,text,score}], indexed}`. Verified (correct chunk + timecode).
- **`GET /` or `/search-ui`** — a self-contained search page (**https://runbook.teknakul.com/search-ui**);
  results link to `teknakul.com/w/<shortUUID>?start=<tc>`. (Optional: add a left-nav link to it.)

**Index refresh:** `rag_index.py` via cron `17 * * * *` (user `lacy`) → `rag.log`. Indexes instance-owned
public+unlisted videos (skips private/internal). Rebuild manually: `python3 rag_index.py`.

## 13. Marketing site (`www.teknakul.com`)
Self-contained static page at `/home/lacy/teknakul-www/public/index.html`, served by a minimal Node
static server (`server.js`, no deps) on **127.0.0.1:3080** under systemd **`teknakul-www.service`**
(`Restart=always`, enabled at boot). Source of truth: repo `www/`.

- **Manage:** `sudo systemctl {status|restart} teknakul-www` · logs `journalctl -u teknakul-www`.
- **Update content:** edit `www/index.html` in the repo, `scp` to `.../teknakul-www/public/index.html`,
  no restart needed (static).
- **Go public (owner TODO):** add a Public Hostname to the linuxg1 Cloudflare token tunnel (Zero Trust →
  Networks → Tunnels → the linuxg1 tunnel → Public Hostname): subdomain `www`, domain `teknakul.com`,
  service `HTTP://localhost:3080`. **Do not** add an apex→www redirect — the apex `teknakul.com` serves
  the federated PeerTube app and its federation identity is permanent.
