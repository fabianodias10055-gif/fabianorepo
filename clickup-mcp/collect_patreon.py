#!/usr/bin/env python3
"""Bring the paying side of the community into the vault.

Until now the panel knew what people asked and nothing about who they are.
Patreon holds the other half: a real name, an email, which tier, how much
per month, how much over the whole relationship, and since when. It also
holds the one field that joins the two worlds, the Discord account a patron
linked to their Patreon, which turns an anonymous handle in a support
channel into a customer with a history.

Emails and payment amounts live here, so this writes only into the vault on
this machine and prints counts rather than people.

Usage:
    python collect_patreon.py --dry-run
    python collect_patreon.py
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import panel            # noqa: E402  (for VAULT)
import patreon_api      # noqa: E402

OUT_NAME = "patreon-members.json"

MEMBER_FIELDS = ",".join((
    "full_name", "email", "patron_status", "currently_entitled_amount_cents",
    "campaign_lifetime_support_cents", "last_charge_date", "last_charge_status",
    "pledge_relationship_start", "will_pay_amount_cents", "note",
))


def campaign_id() -> tuple[str, str]:
    data, why = patreon_api.api_get("/campaigns", {"fields[campaign]": "creation_name"})
    if why:
        return "", why
    rows = data.get("data") or []
    if not rows:
        return "", "this token can see no campaign"
    return rows[0]["id"], ""


def fetch_members(cid: str) -> tuple[list[dict], str]:
    """Every member, one page at a time, with their tier and Discord link."""
    out: list[dict] = []
    cursor = ""
    while True:
        params = {
            "fields[member]": MEMBER_FIELDS,
            "fields[tier]": "title,amount_cents,discord_role_ids",
            "fields[user]": "full_name,social_connections,image_url,url",
            "include": "currently_entitled_tiers,user",
            "page[count]": "500",
        }
        if cursor:
            params["page[cursor]"] = cursor
        data, why = patreon_api.api_get(f"/campaigns/{cid}/members", params)
        if why:
            return out, why

        # The tiers and users arrive alongside the members rather than
        # inside them, so they are indexed once per page and looked up.
        tiers, users = {}, {}
        for inc in data.get("included", []):
            if inc.get("type") == "tier":
                tiers[inc["id"]] = inc.get("attributes", {})
            elif inc.get("type") == "user":
                users[inc["id"]] = inc.get("attributes", {})

        for m in data.get("data", []):
            a = m.get("attributes", {})
            rel = m.get("relationships", {})
            uid = ((rel.get("user") or {}).get("data") or {}).get("id", "")
            user = users.get(uid, {})
            social = user.get("social_connections") or {}
            tier_ids = [t["id"] for t in ((rel.get("currently_entitled_tiers") or {})
                                          .get("data") or [])]
            out.append({
                "patreon_id": m.get("id", ""),
                "user_id": uid,
                "name": (a.get("full_name") or user.get("full_name") or "").strip(),
                "email": (a.get("email") or "").strip(),
                "status": a.get("patron_status") or "",
                "monthly_cents": a.get("currently_entitled_amount_cents") or 0,
                "lifetime_cents": a.get("campaign_lifetime_support_cents") or 0,
                "since": (a.get("pledge_relationship_start") or "")[:10],
                "last_charge": (a.get("last_charge_date") or "")[:10],
                "last_charge_status": a.get("last_charge_status") or "",
                "tiers": [tiers.get(t, {}).get("title", "") for t in tier_ids],
                "discord_role_ids": sorted({r for t in tier_ids
                                            for r in (tiers.get(t, {})
                                                      .get("discord_role_ids") or [])}),
                # The join. Patreon publishes it when the patron linked their
                # account, so it is fact rather than a guess from a name.
                "discord_id": str((social.get("discord") or {}).get("user_id") or ""),
                "profile": user.get("url", ""),
            })

        cursor = (((data.get("meta") or {}).get("pagination") or {})
                  .get("cursors") or {}).get("next") or ""
        if not cursor:
            return out, ""


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(panel.VAULT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    vault = Path(args.vault)

    cid, why = campaign_id()
    if why:
        print(f"could not read the campaign: {why}")
        print("patreon_api.py --status shows what is stored.")
        return 1

    members, why = fetch_members(cid)
    if why and not members:
        print(f"could not read the members: {why}")
        return 1
    if why:
        print(f"WARNING: stopped early after {len(members)} members: {why}")

    active = [m for m in members if m["status"] == "active_patron"]
    linked = [m for m in members if m["discord_id"]]
    with_email = [m for m in members if m["email"]]
    monthly = sum(m["monthly_cents"] for m in active)
    lifetime = sum(m["lifetime_cents"] for m in members)

    print(f"members on the campaign: {len(members)}")
    print(f"  paying right now: {len(active)}")
    print(f"  with an email: {len(with_email)}")
    print(f"  with a Discord account linked: {len(linked)}")
    print(f"  monthly from active members: US$ {monthly / 100:,.2f}")
    print(f"  paid over the whole relationship: US$ {lifetime / 100:,.2f}")

    by_tier: dict[str, int] = {}
    for m in active:
        for t in (m["tiers"] or ["(no tier)"]):
            by_tier[t] = by_tier.get(t, 0) + 1
    print("\n  by tier:")
    for t, n in sorted(by_tier.items(), key=lambda kv: -kv[1]):
        print(f"    {n:4d}  {t}")

    out = vault / "Panel" / OUT_NAME
    if args.dry_run:
        print(f"\n(simulation: would write {out})")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "campaign": cid,
        "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "members": members,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwritten: {out} ({out.stat().st_size / 1024:,.0f} KB)")
    print("It holds names, emails and amounts, so it stays on this machine: "
          "the Drive mirror and the bot export both skip Panel/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
