#!/usr/bin/env python3
"""Talk to Patreon without the access token dying once a month.

A Patreon access token expires after about thirty days. Nothing announces
it: calls simply start returning 401 with the same generic message they
return for a wrong token, so the failure reads as "revoked" and the fix
looks like "paste a new one", which buys another thirty days. That is how
the Discord bot's Patreon commands went quiet without anyone noticing.

The refresh token is what stops that. It mints a new access token on
demand, and Patreon hands back a new refresh token each time, so the new
one has to be stored or the next refresh fails. Everything here exists to
get that sequence right once.

Usage:
    python patreon_api.py --status      what is stored, and when it expires
    python patreon_api.py --refresh     mint a new access token now
    python patreon_api.py --check       call the API and report what came back
"""

import argparse
import json
import sys
import time
from urllib import error, parse, request

BASE = "https://www.patreon.com/api/oauth2"
TOKEN_URL = f"{BASE}/token"
UA = "LocoDevPanel/1.0"

# Stored beside the tokens so a refresh can happen before a call fails
# rather than after, which keeps the failure out of the collector's logs.
EXPIRY_KEY = "PATREON_TOKEN_EXPIRES_AT"


def _store():
    import secrets_store
    return secrets_store


def _expires_at() -> int:
    try:
        return int(_store().get_secret(EXPIRY_KEY, "0") or 0)
    except ValueError:
        return 0


def refresh_token() -> tuple[str, str]:
    """A new access token, or an empty one and the reason it failed.

    Patreon rotates the refresh token on every use. Storing the new one is
    not optional: keep the old and the next refresh is rejected, which
    looks exactly like the expiry this function exists to prevent.
    """
    ss = _store()
    refresh = ss.get_secret("PATREON_REFRESH_TOKEN")
    client_id = ss.get_secret("PATREON_CLIENT_ID")
    client_secret = ss.get_secret("PATREON_CLIENT_SECRET")
    missing = [n for n, v in (("PATREON_REFRESH_TOKEN", refresh),
                              ("PATREON_CLIENT_ID", client_id),
                              ("PATREON_CLIENT_SECRET", client_secret)) if not v]
    if missing:
        return "", f"not stored yet: {', '.join(missing)}"

    body = parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": refresh,
        "client_id": client_id, "client_secret": client_secret,
    }).encode()
    req = request.Request(TOKEN_URL, data=body, method="POST",
                          headers={"User-Agent": UA,
                                   "Content-Type": "application/x-www-form-urlencoded"})
    try:
        payload = json.load(request.urlopen(req, timeout=30))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        if "invalid_grant" in detail:
            return "", ("the refresh token is no longer valid; copy a new "
                        "pair from the Patreon portal")
        return "", f"HTTP {exc.code}: {detail}"
    except OSError as exc:
        return "", f"could not reach Patreon: {type(exc).__name__}"

    access = payload.get("access_token", "")
    if not access:
        return "", "Patreon returned no access token"
    ss.set_secret("PATREON_ACCESS_TOKEN", access)
    if payload.get("refresh_token"):
        ss.set_secret("PATREON_REFRESH_TOKEN", payload["refresh_token"])
    ss.set_secret(EXPIRY_KEY, str(int(time.time()) + int(payload.get("expires_in", 0) or 0)))
    return access, ""


def access_token(force: bool = False) -> tuple[str, str]:
    """A token that should work, refreshed early rather than on failure."""
    ss = _store()
    current = ss.get_secret("PATREON_ACCESS_TOKEN")
    expires = _expires_at()
    # A day's margin: a collector that starts just before the hour turns
    # should not be the thing that discovers the token died mid-run.
    stale = expires and expires - time.time() < 86400
    if force or not current or stale:
        fresh, why = refresh_token()
        if fresh:
            return fresh, ""
        if current and not force:
            return current, ""          # let the call try; it may still work
        return "", why
    return current, ""


def api_get(path: str, params: dict | None = None) -> tuple[dict, str]:
    """One GET, retried once against a fresh token if the answer is 401.

    Patreon says the same "Unauthorized" for an expired token and a wrong
    one, so the only way to tell them apart is to refresh and try again.
    """
    token, why = access_token()
    if not token:
        return {}, why

    def call(tok: str):
        url = BASE + "/v2" + path + (("?" + parse.urlencode(params)) if params else "")
        req = request.Request(url, headers={"Authorization": f"Bearer {tok}",
                                            "User-Agent": UA})
        return json.load(request.urlopen(req, timeout=45))

    try:
        return call(token), ""
    except error.HTTPError as exc:
        if exc.code != 401:
            return {}, f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:160]}"
    except OSError as exc:
        return {}, f"could not reach Patreon: {type(exc).__name__}"

    fresh, why = refresh_token()
    if not fresh:
        return {}, f"unauthorised, and the refresh failed: {why}"
    try:
        return call(fresh), ""
    except error.HTTPError as exc:
        return {}, (f"still unauthorised after refreshing (HTTP {exc.code}). "
                    f"The stored client id or secret may belong to another app.")
    except OSError as exc:
        return {}, f"could not reach Patreon: {type(exc).__name__}"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    ss = _store()

    if args.refresh:
        token, why = refresh_token()
        if not token:
            print(f"could not refresh: {why}")
            return 1
        print(f"new access token stored: {len(token)} characters, "
              f"good until {time.strftime('%Y-%m-%d %H:%M', time.localtime(_expires_at()))}")
        return 0

    if args.check:
        # pledge_sum belonged to v1 and makes v2 reject the whole request.
        # The monthly total is summed from the members instead.
        data, why = api_get("/campaigns", {
            "fields[campaign]": "creation_name,patron_count,published_at,vanity"})
        if why:
            print(f"the call failed: {why}")
            return 1
        for camp in data.get("data", []):
            a = camp.get("attributes", {})
            print(f"campaign {camp['id']}: {a.get('creation_name')}")
            print(f"  patrons right now: {a.get('patron_count')}")
            print(f"  online since: {(a.get('published_at') or '')[:10]}")
        return 0

    print("what is stored:")
    for key in ("PATREON_ACCESS_TOKEN", "PATREON_REFRESH_TOKEN",
                "PATREON_CLIENT_ID", "PATREON_CLIENT_SECRET"):
        val = ss.get_secret(key)
        print(f"  {key:24s} {'yes, ' + str(len(val)) + ' chars' if val else 'MISSING'}")
    exp = _expires_at()
    if exp:
        left = exp - time.time()
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(exp))
        print(f"\naccess token expires {when} "
              f"({'expired' if left < 0 else str(int(left // 86400)) + ' days left'})")
    else:
        print("\nno expiry recorded, so the age of the access token is unknown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
