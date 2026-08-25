#!/usr/bin/env python3
"""Roll up the LocoAI / Wingman accounts from Supabase for the panel.

The panel's Wingman card reads Panel/wingman-users.json; this writes it. It
is the same shape as the other collectors: reads a source, writes a JSON
snapshot into the vault, and the panel only ever reads that file, so a
Supabase outage leaves the card stale rather than the page broken.

Two Supabase APIs, both dependency-free over urllib, so nothing here needs
psycopg or a change to the production schema:

  auth.users  -> the Auth Admin API (/auth/v1/admin/users), which is the
                 only place the email lives; needs the service-role key.
  public.*    -> PostgREST (/rest/v1/<table>) for profiles, usage, licenses
                 and subscriptions.

Credentials, read from clickup-mcp/.env or Windows Credential Manager:
  SUPABASE_URL                 e.g. https://xhvrbzzhsixystoqenuz.supabase.co
  SUPABASE_SERVICE_ROLE_KEY    Settings > API > service_role secret

The service-role key bypasses RLS and can read every account, so it stays
in the credential store, never in the page, and the emails it pulls are
written only into the vault's Panel/ folder, which does not leave this
machine.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse
from urllib import request as R

BASE_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

try:
    from secrets_store import get_secret
except ImportError:
    import os
    def get_secret(name, default=""):        # noqa: E306
        return os.getenv(name, default)

VAULT = Path(r"F:\LocoDev Vault")
OUT = VAULT / "Panel" / "wingman-users.json"

# What counts as a paying plugin plan, and how long a premium account has to
# sit unused before it reads as churning. One place, so the panel card and
# this collector cannot disagree about it.
PAYING_PLANS = ("premium", "standard")
POWER_FREE_MIN = 20      # generations that make a free user an upsell target
CHURN_DAYS = 21          # premium with no use in this long is at risk


def _now():
    return datetime.now(timezone.utc)


def _headers(key: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"}


def _get(url: str, key: str) -> list | dict:
    req = R.Request(url, headers=_headers(key))
    with R.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def fetch_auth_users(base: str, key: str) -> list[dict]:
    """Every account, from the Auth Admin API, paged. This is the only
    source that carries the email address."""
    out, page = [], 1
    while True:
        url = f"{base}/auth/v1/admin/users?" + parse.urlencode(
            {"page": page, "per_page": 1000})
        data = _get(url, key)
        users = data.get("users", data) if isinstance(data, dict) else data
        if not users:
            break
        out.extend(users)
        if len(users) < 1000:
            break
        page += 1
    return out


def fetch_table(base: str, key: str, table: str, select: str) -> list[dict]:
    """A public table over PostgREST, paged by Range so a table larger than
    the default cap still comes back whole."""
    out, step, offset = [], 1000, 0
    while True:
        url = f"{base}/rest/v1/{table}?" + parse.urlencode({"select": select})
        req = R.Request(url, headers={**_headers(key),
                                      "Range-Unit": "items",
                                      "Range": f"{offset}-{offset + step - 1}"})
        try:
            with R.urlopen(req, timeout=60) as resp:
                rows = json.load(resp)
        except error.HTTPError as exc:
            if exc.code == 416:      # asked past the end
                break
            raise
        if not rows:
            break
        out.extend(rows)
        if len(rows) < step:
            break
        offset += step
    return out


def _parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def build(users, profiles, usage, licenses, subs) -> dict:
    now = _now()
    prof = {p["id"]: p for p in profiles}
    lic = {l_["user_id"]: l_ for l_ in licenses}

    # Usage rolled up per user: total generations and the last time seen.
    gen_total: dict[str, int] = {}
    last_used: dict[str, datetime] = {}
    for r in usage:
        uid = r.get("user_id")
        if not uid:
            continue
        gen_total[uid] = gen_total.get(uid, 0) + (r.get("prompt_count") or 0) \
            + (r.get("polish_prompt_count") or 0)
        lu = _parse_ts(r.get("last_used_at"))
        if lu and (uid not in last_used or lu > last_used[uid]):
            last_used[uid] = lu

    def generated(uid):
        return gen_total.get(uid, 0) > 0

    def plan_of(uid):
        return (lic.get(uid) or {}).get("plan") or "free"

    def is_premium(uid):
        l_ = lic.get(uid) or {}
        return l_.get("plan") in PAYING_PLANS and l_.get("status") == "active"

    def emailable(u):
        return bool(u.get("email")) and bool(u.get("email_confirmed_at")) \
            and not u.get("banned_until")

    def within(dt, days):
        return dt is not None and (now - dt).total_seconds() <= days * 86400

    # Per-account fields.
    enriched = []
    for u in users:
        uid = u["id"]
        p = prof.get(uid) or {}
        enriched.append({
            "id": uid, "email": u.get("email"),
            "name": p.get("display_name") or (u.get("email") or "").split("@")[0],
            "created": _parse_ts(u.get("created_at")),
            "last_sign_in": _parse_ts(u.get("last_sign_in_at")),
            "emailable": emailable(u), "gen": gen_total.get(uid, 0),
            "plan": plan_of(uid), "premium": is_premium(uid),
            "last_used": last_used.get(uid),
            "source": p.get("signup_source"), "heard": p.get("heard_from"),
        })

    total = len(enriched)
    gen_users = [e for e in enriched if e["gen"] > 0]
    prem_users = [e for e in enriched if e["premium"]]

    summary = {
        "accounts": total,
        "emailable": sum(1 for e in enriched if e["emailable"]),
        "generated": len(gen_users),
        "active_7d": sum(1 for e in enriched if within(e["last_sign_in"], 7)),
        "active_30d": sum(1 for e in enriched if within(e["last_sign_in"], 30)),
        "new_7d": sum(1 for e in enriched if within(e["created"], 7)),
        "new_30d": sum(1 for e in enriched if within(e["created"], 30)),
        "premium": len(prem_users),
        "cakto_active": sum(1 for s in subs if s.get("status") == "active"),
    }

    def counts(field):
        c: dict[str, int] = {}
        for e in enriched:
            k = e.get(field) or ("unknown" if field == "heard" else "direct/unknown")
            c[k] = c.get(k, 0) + 1
        return sorted(({"label": k, "n": n} for k, n in c.items()),
                      key=lambda x: -x["n"])

    top_users = sorted(gen_users, key=lambda e: -e["gen"])[:15]
    premium_sorted = sorted(prem_users, key=lambda e: (e["created"] or now))

    def days_since_created(e):
        return int((now - e["created"]).total_seconds() // 86400) if e["created"] else 0

    segments = {
        "never_generated": {
            "count": sum(1 for e in enriched if e["gen"] == 0 and e["emailable"]),
            "emails": [e["email"] for e in enriched
                       if e["gen"] == 0 and e["emailable"]]},
        "new_7d": {
            "count": summary["new_7d"],
            "emails": [e["email"] for e in enriched
                       if within(e["created"], 7) and e["emailable"]]},
        "power_free": {
            "count": sum(1 for e in enriched
                         if e["plan"] == "free" and e["gen"] >= POWER_FREE_MIN),
            # The full audience for sending, and the short ranked cut for
            # display. The card shows top; the Email screen sends emails.
            "emails": [e["email"] for e in enriched
                       if e["plan"] == "free" and e["gen"] >= POWER_FREE_MIN
                       and e["emailable"]],
            "top": [{"email": e["email"], "prompts": e["gen"]}
                    for e in sorted((e for e in enriched
                                     if e["plan"] == "free" and e["gen"] >= POWER_FREE_MIN),
                                    key=lambda e: -e["gen"])[:15]]},
        "churning_premium": {
            "count": sum(1 for e in prem_users if not within(e["last_used"], CHURN_DAYS)),
            "emails": [e["email"] for e in prem_users
                       if not within(e["last_used"], CHURN_DAYS) and e["emailable"]],
            "users": [{"email": e["email"],
                       "last_used": e["last_used"].date().isoformat() if e["last_used"] else None}
                      for e in prem_users if not within(e["last_used"], CHURN_DAYS)]},
    }

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "sources": counts("source"),
        "heard_from": counts("heard"),
        "top_users": [{"name": e["name"], "email": e["email"],
                       "prompts": e["gen"], "plan": e["plan"]} for e in top_users],
        "premium": [{"name": e["name"], "email": e["email"], "plan": e["plan"],
                     "days": days_since_created(e)} for e in premium_sorted],
        "segments": segments,
    }


def main() -> int:
    base = (get_secret("SUPABASE_URL") or "").rstrip("/")
    key = get_secret("SUPABASE_SERVICE_ROLE_KEY")
    if not base or not key:
        print("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in "
              "clickup-mcp/.env (Supabase dashboard > Settings > API).")
        return 1

    t0 = time.time()
    try:
        users = fetch_auth_users(base, key)
        profiles = fetch_table(base, key, "profiles",
                               "id,display_name,created_at,last_seen_at,signup_source,heard_from")
        usage = fetch_table(base, key, "loco_usage",
                            "user_id,prompt_count,polish_prompt_count,last_used_at")
        licenses = fetch_table(base, key, "loco_licenses",
                               "user_id,plan,status,created_at,current_period_end")
        subs = fetch_table(base, key, "subscriptions", "status,plan")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:200]
        reason = ("the service-role key was rejected" if exc.code in (401, 403)
                  else f"HTTP {exc.code}")
        print(f"ERROR: Supabase read failed ({reason}): {body}")
        return 1
    except error.URLError as exc:
        print(f"ERROR: could not reach Supabase: {exc.reason}")
        return 1

    doc = build(users, profiles, usage, licenses, subs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(OUT)

    s = doc["summary"]
    print(f"wrote {OUT}")
    print(f"accounts: {s['accounts']} \u00b7 activated: {s['generated']} "
          f"\u00b7 premium: {s['premium']} \u00b7 emailable: {s['emailable']} "
          f"\u00b7 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
