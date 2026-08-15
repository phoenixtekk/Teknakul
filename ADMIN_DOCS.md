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

## 11. Fleet hygiene
This is a shared production box. Never restart/delete another project's container. After any infra
change, update `~/.claude/server-inventory.md` (linuxg1 section + "Last verified") and re-publish the
wiki copy (`SystemDocs/linuxg-fleet-inventory`).
