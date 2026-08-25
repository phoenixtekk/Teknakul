# Teknakul — Billing

## Processor
**Stripe** (subscriptions / Checkout Sessions). Low‑risk B2B/creator SaaS; direct processor is
appropriate. Isolated behind ONE module (`services/restream/billing.py`) — no Stripe SDK calls
scattered elsewhere.

- **Account:** `TEKNAKUL`
  - Live: `acct_1U5VfrCYsLQTww9W`
  - Sandbox (test): `acct_1U5VfxCqoxpfJ3P8`  ← current build/test target
- ⚠️ Verify the Stripe MCP is bound to **this** account (not "Orrdily") before any write:
  `list_available_accounts_or_orgs` must show TEKNAKUL.

## Model
Monthly recurring subscriptions. Entitlements drive the multistream gate (destination count).

| Plan | Price (test price id) | Multistream outputs |
|---|---|---|
| Free | — | 0 (no multistream) |
| **Pro** | $20/mo · `price_1U8OtzCqoxpfJ3P8EkxQ1hdX` (`prod_V8gGO3DmiTJHUV`) | 3 |
| **Studio** | $49/mo · `price_1U8Ou8CqoxpfJ3P8Hu0PsPba` (`prod_V8gGRu4nQAWnGy`) | 6 |
| +1 Network add‑on | $5/mo · `price_1U8OuHCqoxpfJ3P8FpIxpL6i` | +1 output |
| Network Pack (3) | $12/mo · `price_1U8OuQCqoxpfJ3P8DHWRc0GD` | +3 outputs |

Prices above are **test mode**. Re‑create identically in **live mode** before launch (same script,
`livemode:true`, `stripe_context=acct_1U5VfrCYsLQTww9W`), then update `billing_config.json`.

## How it works
- **Checkout:** `POST /billing/checkout {plan}` (in‑app, PeerTube‑authed) → creates a Checkout
  Session (subscription mode) with `client_reference_id = <teknakul username>` and
  `subscription_data.metadata.{teknakul_username,plan}` → returns the Stripe URL. Buttons live on the
  `/p/multistream` page.
- **Webhook:** `POST /billing/webhook` (`restream.teknakul.com`) — HMAC‑SHA256 signature verified.
  On `checkout.session.completed` / `customer.subscription.*` it maps the subscription back to the
  username and writes `services/restream/entitlements.json` (`{plan, max}`), which the restream
  service reads to gate destinations. Cancel/past‑due → downgraded to free. **Verified E2E** (signed
  event unlocks Pro; bad signature rejected).
- Webhook endpoint id (test): `we_1U8OuyCqoxpfJ3P8h5C67rTt`.

## Keys / secrets (never committed)
Stored in `services/restream/.env` (mode 600), loaded via systemd `EnvironmentFile`:
- `STRIPE_WEBHOOK_SECRET` — from the webhook endpoint (set ✅).
- `STRIPE_SECRET_KEY` — **restricted** key (Checkout Sessions write, Prices/Products read,
  Subscriptions read). **Owner action:** create in the Stripe dashboard (test mode) and paste in.
  Live launch needs the live restricted key.
- Price IDs live in `billing_config.json` (non‑secret, committed).

## Lock‑in / migration
Stripe‑specific surface is confined to `billing.py` (checkout + webhook). Entitlements are a plain
JSON contract (`{username: {plan, max}}`) independent of Stripe, so switching processors means
re‑implementing only `billing.py` against the same entitlement contract. If the category ever
becomes freeze‑prone, revisit a Merchant of Record (Paddle/Polar) per the billing rule.

## Dashboard‑only (owner)
- Provide the restricted `STRIPE_SECRET_KEY` (above).
- Platform statement descriptor + public display name (account settings, not API‑writable).
- Recreate products/prices in live mode when ready to launch.
