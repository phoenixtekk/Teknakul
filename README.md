# Teknakul

> The streaming platform for technical people — built by technical people. Watch, learn, and
> broadcast how to actually run the Modern Workplace, with AI as your force multiplier.

**Status:** 🚧 Phase 1 — VOD build (pivoted from a microblog to a video platform 2026-07-20).
**Domain:** `teknakul.com` (apex) · **Audience:** MSPs, IT pros, entrepreneurs, and technical creators.

## What this is

A federated (ActivityPub / Fediverse) **video streaming platform** — think YouTube/Twitch/Rumble,
but for the technical crowd and *owned by its creators* — built as a soft fork of
[PeerTube](https://github.com/Chocobozzz/PeerTube) (AGPL-3.0).

**The pivot:** this project began as a Misskey/Sharkey microblog. We scrapped that and rebuilt it as a
streaming platform on PeerTube, **carrying the brand, mission, audience, AI-confidence angle,
federation, and ecosystem integrations across** — video just fits the "watch someone do it" learning
model far better than text.

### The three things that make it different
1. **A video platform for technical people** — code-alongs, homelab tours, Intune/M365/Google Workspace
   walkthroughs, security demos, "build in public." Categories and discovery tuned to this audience.
2. **AI-native for technical learning** — auto transcripts, chapters, and summaries; transcript search;
   AI-generated highlight clips; and an AI co-pilot that answers *from the video library* ("show me the
   timestamp where they fix the Conditional Access policy").
3. **Creator-owned & federated** — videos federate across the Fediverse; creators own their audience and
   content. No algorithm holding your reach hostage.

**Positioning:** *"Twitch/YouTube for technical people — that you actually own."*

**The mission (carried over):** give somewhat-technical people the confidence *and the concrete method*
to run complex technology using AI as a force multiplier — now taught by watching real operators do it.

## Scope

- **Phase 1 (now): VOD** — upload-based video (YouTube-style) + AI features + federation.
- **Phase 2: Live** — Twitch-style live streaming. Deferred because RTMP ingest can't traverse the
  Cloudflare HTTP tunnel (needs a direct port or Cloudflare Spectrum). See `ADMIN_DOCS.md`.

## Architecture at a glance

- **Base:** PeerTube soft fork (Node.js + Angular, PostgreSQL, Redis, ffmpeg transcoding). Federated
  via ActivityPub — channels/accounts get `@handle@teknakul.com`.
- **Hosting:** standalone app container on `127.0.0.1:3050` on **linuxg1**, behind the existing
  Cloudflare tunnel (`teknakul.com → :3050`). Self-contained Postgres + Redis.
- **Video delivery:** **Cloudflare R2** (object storage) — *required*. Cloudflare's CDN restricts
  serving video unless it's on a Cloudflare service (Stream/Images/R2), and piping video through the
  shared tunnel would risk the whole fleet. App/API via tunnel; video bytes via R2.
- **Transcoding:** CPU-capped (2.5 vCPU) on the shared box; offload to PeerTube **remote runners** as
  volume grows.
- **Identity:** Aigartha ID SSO (Microsoft Entra + Google Workspace as connectors) — carried over.
- **AI:** transcripts via Whisper (Ollama AI box) + Claude for summaries/chapters/co-pilot; RAG over
  transcripts (Mibrow pattern).

⚠️ **The federation hostname (`teknakul.com`) is permanent** — same rule as any Fediverse app. The apex
serves the platform; a marketing site, if built, lives at `www.teknakul.com` (no apex→www redirect).

## Repository layout

| Path | What it is | License |
|---|---|---|
| `deploy/` | PeerTube compose + config for linuxg1 (the running deployment mirrors `/home/lacy/teknakul`) | — |
| `services/` | Satellite services (auth bridge, AI transcripts/co-pilot) — separate processes, outside the AGPL tree | ours |
| `brand/` | Teknakul brand assets (carried over) + `BRAND.md` | — |
| `.claude/agents/` | 263 Agency Agents (repo-local) | — |

## Docs

- [`FEATURES.md`](FEATURES.md) · [`ADMIN_DOCS.md`](ADMIN_DOCS.md) · [`HELP_CENTER.md`](HELP_CENTER.md) · [`BILLING.md`](BILLING.md) · [`brand/BRAND.md`](brand/BRAND.md)

---

## License & source (AGPL-3.0)

Teknakul is built on **PeerTube** (AGPL-3.0). We run the official PeerTube server
(unmodified — upstream source: https://github.com/Chocobozzz/PeerTube) plus the custom plugins and
deployment configuration in this repository.

This repository provides the **complete corresponding source of Teknakul's modifications**, as
required by the AGPL-3.0 network clause:

- `plugins/peertube-plugin-auth-openid-connect-google/` — a fork of the AGPL `auth-openid-connect`
  plugin (enables Google sign-in alongside Microsoft).
- `plugins/peertube-plugin-teknakul-categories/` — custom niche video categories.
- `plugins/peertube-plugin-teknakul-featured-channels/` — a "Featured Channels" sidebar section.
- Deployment configuration, operator/help docs, and brand assets.

Licensed under **AGPL-3.0** (see `LICENSE`). PeerTube © Chocobozzz and contributors.
