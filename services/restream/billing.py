#!/usr/bin/env python3
"""
Teknakul billing bridge (Phase 2). Stdlib-only Stripe integration:
  - create_checkout(username, plan)  -> a Stripe Checkout Session URL (subscription mode)
  - handle_webhook(payload, sig)     -> verifies the signature and writes entitlements

Entitlements are written to the same entitlements.json the restream service reads, so a
paid subscription immediately unlocks multistream destinations. No Stripe SDK; Checkout
Session creation is a form POST to the Stripe API and webhook verification is HMAC-SHA256.

Secrets come from the environment (restricted key + webhook secret); price IDs from
billing_config.json. AGPL-3.0.
"""

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "billing_config.json")
ENT_FILE = os.environ.get("RESTREAM_ENTITLEMENTS", os.path.join(HERE, "entitlements.json"))
STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_APP = os.environ.get("PUBLIC_APP_URL", "https://teknakul.com")
MARKETING = os.environ.get("PUBLIC_MARKETING_URL", "https://www.teknakul.com")
STRIPE_API = "https://api.stripe.com/v1"


def _config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"plans": {}, "addons": {}}


# ---- entitlements (shared with restream_server) --------------------------------
def _load_ent():
    try:
        with open(ENT_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_ent(ent):
    tmp = ENT_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ent, f, indent=2)
    os.replace(tmp, ENT_FILE)


def set_entitlement(username, plan, max_destinations):
    ent = _load_ent()
    ent[username] = {"plan": plan, "max": int(max_destinations),
                     "updated": int(time.time())}
    _save_ent(ent)


def clear_entitlement(username):
    ent = _load_ent()
    if username in ent:
        ent[username] = {"plan": "free", "max": 0, "updated": int(time.time())}
        _save_ent(ent)


# ---- stripe form encoding (nested dict/list -> bracket notation) ----------------
def _flatten(obj, prefix=""):
    items = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}[{k}]" if prefix else str(k)
            items += _flatten(v, key)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            items += _flatten(v, f"{prefix}[{i}]")
    else:
        if isinstance(obj, bool):
            obj = "true" if obj else "false"
        items.append((prefix, str(obj)))
    return items


def _stripe(path, params):
    body = urllib.parse.urlencode(_flatten(params)).encode()
    req = urllib.request.Request(STRIPE_API + path, data=body, method="POST",
                                 headers={"Authorization": "Bearer " + STRIPE_SECRET,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


# ---- checkout -------------------------------------------------------------------
def create_checkout(username, plan):
    cfg = _config()
    p = cfg.get("plans", {}).get(plan)
    if not p:
        raise ValueError("unknown plan")
    if not STRIPE_SECRET:
        raise RuntimeError("billing not configured (missing STRIPE_SECRET_KEY)")
    session = _stripe("/checkout/sessions", {
        "mode": "subscription",
        "line_items": [{"price": p["price"], "quantity": 1}],
        "client_reference_id": username,
        "subscription_data": {"metadata": {"teknakul_username": username, "plan": plan}},
        "success_url": PUBLIC_APP + "/p/multistream?upgraded=1",
        "cancel_url": MARKETING + "/pricing.html",
        "allow_promotion_codes": True,
    })
    return session.get("url")


# ---- webhook --------------------------------------------------------------------
def verify(payload_bytes, sig_header):
    if not STRIPE_WEBHOOK_SECRET or not sig_header:
        return False
    try:
        parts = dict(kv.split("=", 1) for kv in sig_header.split(",") if "=" in kv)
        signed = parts["t"].encode() + b"." + payload_bytes
        expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts.get("v1", ""))
    except Exception:  # noqa
        return False


def _plan_from(plan_key):
    cfg = _config()
    p = cfg.get("plans", {}).get(plan_key)
    return (plan_key, p["max"]) if p else (None, 0)


def handle_webhook(payload_bytes, sig_header):
    """Returns (status_code, message). Verifies signature, then applies entitlement."""
    if not verify(payload_bytes, sig_header):
        return 400, "bad signature"
    try:
        event = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return 400, "bad json"
    typ = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    if typ == "checkout.session.completed":
        username = obj.get("client_reference_id")
        # plan is in the subscription metadata we set; fall back to session metadata
        plan_key = (obj.get("metadata") or {}).get("plan")
        if username and plan_key:
            plan, mx = _plan_from(plan_key)
            if plan:
                set_entitlement(username, plan, mx)
                return 200, f"entitled {username} -> {plan}"
        return 200, "ignored (no username/plan)"
    if typ in ("customer.subscription.created", "customer.subscription.updated"):
        meta = obj.get("metadata") or {}
        username = meta.get("teknakul_username")
        plan_key = meta.get("plan")
        status = obj.get("status")
        if username and plan_key:
            if status in ("active", "trialing"):
                plan, mx = _plan_from(plan_key)
                set_entitlement(username, plan, mx)
                return 200, f"updated {username} -> {plan} ({status})"
            if status in ("canceled", "unpaid", "past_due", "incomplete_expired"):
                clear_entitlement(username)
                return 200, f"downgraded {username} ({status})"
        return 200, "ignored"
    if typ == "customer.subscription.deleted":
        username = (obj.get("metadata") or {}).get("teknakul_username")
        if username:
            clear_entitlement(username)
            return 200, f"downgraded {username} (deleted)"
        return 200, "ignored"
    return 200, "ignored " + typ
