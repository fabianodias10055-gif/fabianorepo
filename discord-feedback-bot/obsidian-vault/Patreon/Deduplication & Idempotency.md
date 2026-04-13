# Deduplication & Idempotency

## Why It Matters

Patreon can retry webhook deliveries if the endpoint doesn't respond in time,
or when the bot restarts and misses events. Without dedup, a single cancellation
can appear 45+ times in Discord. This happened in production and was the main
reliability problem solved in this session.

## Three-Layer Defense

### Layer 1 — Body Hash (Persistent, Strongest)

```python
body_hash = hashlib.sha256(body).hexdigest()
# _webhook_seen_hashes loaded from /app/data/patreon_webhook_seen.json
if body_hash in _webhook_seen_hashes:
    return 200  # "OK (duplicate body)"
_webhook_seen_hashes[body_hash] = datetime.now(utc).isoformat()
_save_webhook_seen(_webhook_seen_hashes)
```

- Persists across restarts (file on Railway volume)
- 30-day TTL — old hashes pruned on load
- Catches **exact** retries (same payload bytes)

### Layer 2 — Historical Filter (for pledge:delete)

```python
last_charge_date = attrs.get("last_charge_date")
if event == "members:pledge:delete" and last_charge_date:
    age_days = (now - parse(last_charge_date)).days
    if age_days > 60:
        return 200  # "OK (historical)"
```

- Blocks cancellations where `last_charge_date` is >60 days ago
- Catches historical Patreon cleanups being replayed as fresh events
- Does NOT catch recent-ish cancellations (intentional — those are real)

### Layer 3 — In-Memory Cache (Fast, Non-Persistent)

```python
cache_key = (member_id, event)
dedup_seconds = 21600  # 6 hours for pledge events, 30s for others
if time.monotonic() - _patreon_event_cache.get(cache_key, 0) < dedup_seconds:
    return 200  # "Skipping duplicate"
_patreon_event_cache[cache_key] = time.monotonic()
```

- In-memory only — resets on restart
- 6-hour window for pledge events catches rapid retries
- Belt-and-suspenders behind the persistent layer

### Layer 4 — Startup Grace Period

```python
_WEBHOOK_STARTUP_TIME = datetime.now(utc)  # set at module load
_WEBHOOK_STARTUP_GRACE_SECS = 90

age = (datetime.now(utc) - _WEBHOOK_STARTUP_TIME).total_seconds()
if age < 90:
    # Log + hash the event but don't announce to Discord or send Pushover
```

- First 90 seconds after bot starts: events are logged and hashed but silent
- Absorbs the Patreon retry flood that always comes right after a redeploy
- Roles are still assigned even during grace period

## Files

- `/app/data/patreon_webhook_seen.json` — `{hash: iso_timestamp}` dict

## What's Not Deduplicated

- Different payloads for the same member+event (e.g., two status updates hours apart)
- `members:create` for a member who rejoins after leaving (correct — that's a real event)
