# Teknakul — Features

Living document. **Legend:** ✅ shipped/live · 🚧 in progress · 📋 planned · ⬜ not started

**Platform: PeerTube 7.3.0 (soft fork).** Pivoted from Sharkey/microblog 2026-07-20.
**Live at https://teknakul.com** (VOD; registration disabled).

---

## Phase 0 — Foundations
| Item | Status | Notes |
|---|---|---|
| PeerTube deployed on linuxg1 | ✅ | `chocobozzz/peertube:v7.3.0-bookworm`, standalone behind CF tunnel, `127.0.0.1:3050` |
| Self-contained Postgres + Redis | ✅ | Touches no shared service; CPU-capped (transcoding) |
| Reuse existing CF ingress | ✅ | `teknakul.com → :3050`, zero CF changes |
| Public + branded | ✅ | Name **Teknakul**, teal CSS, logo + banner (carried-over assets); page title "…- Teknakul" |
| Root admin + password rotated | ✅ | First-boot password leaked to logs → rotated; creds `/home/lacy/teknakul/.peertube-admin` (600) |
| Version pinned | ✅ | `v7.3.0-bookworm` (not floating `production`) |
| Brand assets carried over | ✅ | `brand/` (icon/wordmark/banner + `BRAND.md`) |

## Phase 1 — VOD platform (current)
| Item | Status | Notes |
|---|---|---|
| Marketing front door (Option A) | ✅ | Custom homepage at apex (`/custom-pages/homepage/instance`) + landing route `/home`. Live at teknakul.com; clean handles preserved. Owner TODO: CF redirect `www→apex`. |
| Video upload / channels / accounts | ✅ (base) | PeerTube core |
| ActivityPub federation | ✅ (base) | Handles `@channel@teknakul.com` |
| **Cloudflare R2 for video delivery** | ✅ | Complete + verified 2026-08-11: upload→transcode→stored in `teknakul-videos`, served from `videos.teknakul.com`, ACL nulled, **CORS live** (GET/HEAD, `*`, expose Content-Range/Accept-Ranges → seeking works). |
| Amazon SES email | 🚧 | SMTP wired + connected (us-east-1:587 STARTTLS, "Successfully connected to SMTP server"). **Owner TODO: verify teknakul.com in SES** (DKIM) or swap FROM to a verified sender — mail won't send until then. |
| Microsoft SSO | ✅ | `auth-openid-connect` plugin (v1.2.0), Entra tenant, discovery OK, button live on /login. |
| Google SSO | 🚧 | Forked plugin `auth-openid-connect-google` installed + configured, button live. **Owner TODO: add redirect URI `https://teknakul.com/plugins/auth-openid-connect-google/router/code-cb` to the Google OAuth app** (its callback differs from Microsoft's). See `plugins/…/README.md`. |
| Transcoding tuning | 📋 | Set low threads/concurrency in admin; remote runners as volume grows |
| Audience categories/tags | 📋 | Intune, M365, Google Workspace, Security, Linux, Homelab, Build-in-public |
| ~~Ecosystem deep-links~~ | ⛔ dropped | Owner 2026-08-11: **zero** ecosystem integrations — no Aigartha / Mibrow / TxtYa / Workplace store / Enogye / Analytikul Ops. Teknakul is fully standalone. |
| Deeper source-level rebrand | 📋 | Residual "PeerTube" strings; via plugin/theme, not hard fork |

## Phase 2 — AI-Confidence engine ("Runbook Mode", video-native, the differentiator)
| Item | Status | Notes |
|---|---|---|
| Auto transcripts | ✅ | Whisper (`whisper-ctranslate2`) on the AI box `.168` via PeerTube remote runner; VTT captions on every upload. Verified E2E. |
| AI chapters + summaries | ✅ | `services/runbook-ai/runbook_ai.py` → Ollama box `.182` (`llama3.3:70b`) reads the transcript, writes native PeerTube **chapters** + an AI **summary** into the description. Runs via cron `*/10` on linuxg1. Verified E2E (6 accurate chapters + summary). |
| "Ask this video" co-pilot | 🚧 next | Query API + watch-page player panel; answers from the transcript and jumps to the timestamp. |
| Copyable commands/code panel | 🚧 next | Extract spoken/shown commands into a copy-ready side panel. |
| Library-wide transcript search + RAG | 🚧 next | `nomic-embed-text` (on `.182`) → pgvector; "answer from the video library" (Mibrow pattern). |
| AI highlight/clip generation | 📋 | |

## Phase 3 — Live + monetization
| Item | Status | Notes |
|---|---|---|
| Live streaming (RTMP / OBS) | ✅ | **LIVE.** OBS → `rtmp://ingest.teknakul.com:1935/live` + per‑live stream key (Publish → Go live). Ingest on :1935 via UniFi forward to the DNS‑only `ingest.teknakul.com`. Verified publicly reachable. Passthrough (live transcoding off). |
| Channel memberships / Pro tier | 📋 | Stripe; see `BILLING.md` |
| Creator payouts | 📋 | Revisit processor (Connect vs MoR) — payouts change the risk profile |
| Mentor/office-hours live | 📋 | |

## Cross-cutting
| Item | Status | Notes |
|---|---|---|
| Marketing site (`www.teknakul.com`) | ✅ | Self-contained teal-on-charcoal site (`www/index.html`), Node static server under systemd `teknakul-www.service` on linuxg1 :3080. **Owner TODO:** add CF ingress `www.teknakul.com → localhost:3080` (no apex→www redirect). |
| Moderation + trust | 📋 | Federated → staffed moderation before opening signups |
| AGPL source repo | ✅ | Published to github.com/phoenixtekk/Teknakul (LICENSE + custom plugins + `services/` + `www/` + docs). |
| `www.teknakul.com` marketing site | ⬜ | Separate; apex serves the app (no apex→www redirect) |
