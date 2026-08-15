# Teknakul — Billing & Payments

**Status: Phase 0 — no payment processing implemented.** No processor is wired up, no keys exist.
This document records the *decision and its constraints* before any code is written.

---

## Processor decision

**Recommended: Stripe** — but not by default; by evaluation.

Per the standing payment rule, the processor is chosen **per product** based on freeze risk:

| Factor | Teknakul's profile |
|---|---|
| Category | B2B/professional SaaS subscription — **low risk** |
| Expected chargeback rate | Low (recurring, low-ticket, professional audience) |
| Volume pattern | Gradual community growth, not spiky launches |
| Would a freeze be existential? | **No** — the community itself doesn't depend on billing; a freeze pauses revenue, not the platform |

→ A direct processor is appropriate. **Stripe**, consistent with Mibrow, Enogye, TxtYa, Aigartha, and
the Workplace store. A Merchant of Record (Paddle/Polar) is **not** warranted here.

⚠️ **Re-evaluate if** the model shifts toward high-risk territory — e.g. an MSP marketplace taking a
cut of third-party transactions, affiliate payouts, or anything resembling money transmission. That is
a materially different risk profile and would justify revisiting MoR or Stripe Connect.

---

## Billing model (planned)

| Tier | Price | Includes |
|---|---|---|
| Free | $0 | Full social core, read the library, limited co-pilot usage |
| Pro | ⬜ TBD | Co-pilot power usage, private channels, mentor access, tracks |
| Team/MSP | ⬜ TBD | Seats for an MSP's staff |

⬜ **Pricing not set.** Should align with the ecosystem's existing ladders (Mibrow $8/$24/$16-seat;
TxtYa $12/$39/$149; Workplace memberships $499/$999/$1,499). Co-pilot usage carries real per-token
cost — model that before setting a price, and consider a usage-credit component like Enogye's.

---

## Anti-lock-in requirements (non-negotiable)

- **Never scatter `stripe.*` calls through the codebase.** All payment logic sits behind **one**
  internal billing module exposing `createCustomer` / `subscribe` / `cancel` / `handleWebhook`.
- **Normalize webhooks into internal domain events** so app logic never depends on Stripe's payload
  shape.
- Goal: adding a backup processor or swapping providers touches the billing module only.

## Entitlements

Entitlements resolve through **Aigartha ID**, not Stripe directly — the same identity backbone that
handles SSO. This keeps cross-product entitlements (community status unlocking tool trials or store
discounts) coherent, and means the entitlement layer survives a processor change.

⚠️ **Known ecosystem coupling to watch:** binding entitlements too tightly to any one vendor's billing
primitives recreates the Clerk-Billing-requires-Stripe trap. Keep entitlement state in our own
database, with the processor as an input to it — never as the source of truth.

## Security

- Keys in **environment variables only** — never hardcoded, never committed, never in `NEXT_PUBLIC_*`.
- Use **restricted keys** in dev/CI; full secret keys never leave the server env.
- **Never log card data or full payment payloads.**
- Processor-hosted checkout (Stripe Checkout / Payment Element) — **never raw card fields**, keeping
  PCI scope minimal.
- Verify webhook signatures; use idempotency keys.

## Migration notes

Stored payment methods can't be freely exported (PCI); switching processors requires a coordinated
processor-to-processor transfer and triggers card re-authorization (→ involuntary churn). The billing
module abstraction above is what keeps that cost bounded.

## Open items

- ⬜ Set Pro/Team pricing (model co-pilot token cost first)
- ⬜ Decide whether co-pilot usage is unlimited, metered, or credit-based
- ⬜ Confirm Stripe (vs. MoR) once the marketplace/payout question is settled
- ⬜ Implement the billing abstraction module before any Stripe call is written
