# Patreon Webhook Handler

## Endpoint

`POST /patreon/webhook`

Patreon calls this URL whenever a member event occurs.

## Signature Verification

```python
expected = hmac.new(PATREON_WEBHOOK_SECRET.encode(), body, hashlib.md5).hexdigest()
if not hmac.compare_digest(sig, expected):
    return 403
```

Header: `X-Patreon-Signature`
Algorithm: HMAC-MD5 of raw request body

## Event Types

| Event | When it fires |
|-------|--------------|
| `members:create` | Someone follows/joins the Patreon page (free) |
| `members:update` | Member info updated (payment status, pledge change, etc.) |
| `members:delete` | Member left the Patreon page entirely |
| `members:pledge:create` | New paid subscription (or free trial start) |
| `members:pledge:update` | Tier change or pledge amount change |
| `members:pledge:delete` | Cancelled paid subscription |
| `posts:publish` | New post published on Patreon |
| `posts:update` | Post edited |
| `posts:delete` | Post deleted |

## Processing Flow

```
1. Read body + signature header
2. Verify HMAC signature → 403 if invalid
3. Parse JSON
4. Idempotency check (body hash) → skip if seen before
5. Historical filter (pledge:delete older than 60 days) → skip
6. Parse attributes: name, amount_cents, trial info, Discord ID, tier
7. In-memory dedup check (_patreon_event_cache)
8. Check startup grace period (first 90s after boot)
9. Log event to patreon_events.json
10. Detect trial conversion (pledge:create for known trial member)
11. Assign/remove Discord roles
12. Send Discord message to announcement channel
13. Send public message to public channel (paid new members only)
14. Send Pushover notification (if not in startup grace)
15. Return 200 OK
```

## Key Attributes Parsed

```python
attrs = data["data"]["attributes"]
member_id = data["data"]["id"]
included = data["included"]  # contains user (Discord ID) and tier objects

full_name = attrs["full_name"]
# Free trial detection — use explicit None check, not 'or'
_entitled = attrs.get("currently_entitled_amount_cents")
_will_pay  = attrs.get("will_pay_amount_cents")
amount_cents = _entitled if _entitled is not None else (_will_pay or 0)

trial_ends_at = attrs.get("trial_ends_at")
is_free_trial = bool(trial_ends_at) and amount_cents == 0

# Discord ID from included[].attributes.social_connections.discord.user_id
# Tier title from included[].attributes.title (type == "tier")
```

## Discord Messages Sent

| Event | Message format |
|-------|---------------|
| `members:pledge:create` (paid) | 💎 Name joined LocoBasic for $X/month |
| `members:pledge:create` (trial) | 🆓 Name started a free trial of LocoBasic |
| `members:create` | 🎉 Name just joined LocoDev on Patreon for free |
| `members:pledge:delete` | ❌ Name just cancelled their Patreon pledge |
| `members:pledge:update` | 🔄 Name updated their pledge — now $X/month |
| `members:update` (declined) | ⚠️ Name's payment was declined |
| `members:update` (active) | ✅ Name's payment was successful |
| `members:delete` | 👋 Name just left LocoDev on Patreon |

## See Also
- [[Deduplication & Idempotency]]
- [[Events & Roles]]
- [[Free Trials]]
- [[Discord/Pushover Notifications]]
