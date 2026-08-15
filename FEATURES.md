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

## Phase 2 — AI-Confidence engine (video-native, the differentiator)
| Item | Status | Notes |
|---|---|---|
| Auto transcripts | 📋 | Whisper on the Ollama AI box; PeerTube has a transcription plugin hook |
| AI chapters + summaries | 📋 | Claude over transcripts |
| Transcript search + RAG co-pilot | 📋 | pgvector; "answer from the video library" (Mibrow pattern) |
| AI highlight/clip generation | 📋 | |
| "Manage X with AI" video tracks/playlists | 📋 | Linux, M365, Intune, Google Workspace, security |

## Phase 3 — Live + monetization
| Item | Status | Notes |
|---|---|---|
| Live streaming (RTMP) | 📋 | **Blocked on ingest:** RTMP can't cross the HTTP tunnel — needs direct port or CF Spectrum |
| Channel memberships / Pro tier | 📋 | Stripe; see `BILLING.md` |
| Creator payouts | 📋 | Revisit processor (Connect vs MoR) — payouts change the risk profile |
| Mentor/office-hours live | 📋 | |

## Cross-cutting
| Item | Status | Notes |
|---|---|---|
| Moderation + trust | 📋 | Federated → staffed moderation before opening signups |
| AGPL source repo | ⬜ | PeerTube is AGPL-3.0 — publish modified source before public launch |
| `www.teknakul.com` marketing site | ⬜ | Separate; apex serves the app (no apex→www redirect) |
