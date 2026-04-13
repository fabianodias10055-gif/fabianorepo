# Bug Fix Session Log

All bugs identified and fixed during the Claude Code session (April 2026).

---

## 1. Click Tracking Showing 0

**Symptom**: All links showed 0 clicks even though people were clicking.

**Root Cause**: `asyncio.create_task(_log())` without saving a reference.
Python's garbage collector killed the task before it executed.

**Fix**: Log the click synchronously first (`log_click()` returns `click_id`),
then update country in a background task held in `_bg_tasks` set.

```python
_bg_tasks: set = set()
task = asyncio.create_task(_geo(click_id, ip))
_bg_tasks.add(task)
task.add_done_callback(_bg_tasks.discard)
```

---

## 2. Pushover NameError (Notifications Not Firing)

**Symptom**: Pushover notifications never arrived. No error in logs.

**Root Cause**: `is_free_trial` was used on line ~3540 but not defined until
line ~3572. The NameError crashed the webhook handler silently (caught by a
broad `except Exception`). The 200 OK was still returned to Patreon.

**Fix**: Moved `trial_ends_at` and `is_free_trial` computation to the top
of the handler, before any code that uses them.

---

## 3. Pushover Priority 1 Rejected

**Symptom**: Pushover API returned an error when notifications were sent.

**Root Cause**: Pushover's priority level 1 (high) requires `retry` and
`expire` parameters. They were not included.

**Fix**: Changed to `priority: 0` (normal). Works without extra params.

---

## 4. Discord Channel Not Receiving Messages

**Symptom**: Patreon events not posting to `#1490377274749354207`.

**Root Cause**: `client.get_channel(ID)` returns `None` if the channel
isn't in Discord's local cache. The `if channel:` guard silently skipped posting.

**Fix**:
```python
channel = client.get_channel(ID) or await client.fetch_channel(ID)
```
Applied everywhere: Patreon announcements, YouTube watcher, weekly summaries.

---

## 5. Free Trial Treated as Paid Subscription

**Symptom**: Free trial members received paid member Pushover notifications.

**Root Cause**:
```python
amount_cents = _entitled or _will_pay or 0
```
When `_entitled = 0` (trial member, paying nothing), Python's `or` treats 0
as falsy and falls through to `_will_pay` (the full tier price they would pay).

**Fix**: Explicit None check:
```python
_entitled = attrs.get("currently_entitled_amount_cents")
_will_pay  = attrs.get("will_pay_amount_cents")
amount_cents = _entitled if _entitled is not None else (_will_pay or 0)
```

---

## 6. Bot Hallucinating Link Creation

**Symptom**: Claude would say "✅ Short link created!" but the link didn't exist.

**Root Cause**: Claude has no way to actually create database records.
It was generating plausible-looking success messages with no real action.

**Fix**: Implemented the `[CREATE_LINK: prefix/slug → url]` marker system.
Claude outputs the marker; the bot intercepts, executes, verifies, and shows
the real result. Marker is stripped from the displayed response.

---

## 7. Slug Collision (Claude Reusing Existing Slugs)

**Symptom**: Bot would fail to create a link because the slug already existed.
Claude was not aware of existing slugs.

**Root Cause**: Claude had no knowledge of which slugs were already in use.

**Fix**: Injected the full list of existing links into Claude's system prompt
with explicit instructions: "Never reuse an existing slug."

---

## 8. Weekly Summary Showing No Activity

**Symptom**: `/patreon_reports` weekly summary always said "No activity this week."

**Root Cause**: Weekly summary was reading from the local event log which
was empty (bot was new, hadn't logged enough events). No Patreon API call.

**Fix**: Changed weekly summary to call `_fetch_patreon_daily_activity(days=7)`
which queries the live Patreon API for actual member data.

---

## 9. YouTube Watcher Stopped Posting

**Symptom**: New Unreal Engine videos stopped appearing in `#1481432850212585655`.

**Root Cause 1**: `get_channel()` cache miss — channel not in Discord cache,
`if channel:` silently skipped the post.

**Root Cause 2**: `_ue_seen_video_ids` was an in-memory set, reset on every
restart. On first poll after restart, all current videos were re-seeded without
announcing. Videos posted while bot was down would be seeded and never posted.

**Fix**:
- `get_channel(ID) or await fetch_channel(ID)`
- Persist seen IDs to `/app/data/ue_seen_videos.json`

---

## 10. Historical Cancellations Replayed as Current

**Symptom**: 45-75 "❌ X cancelled their Patreon pledge" messages appeared
in rapid succession. All were months-old cancellations.

**Root Cause**: In-memory dedup `_patreon_event_cache` resets on restart.
Patreon retried a backlog of deliveries after a redeploy, and all passed dedup.
Each was stamped with `ts = now` in the event log, passing the 24h filter.

**Fix**:
1. **Body hash dedup** — SHA256 of request body, persisted to file (30-day TTL)
2. **Historical filter** — `pledge:delete` with `last_charge_date` > 60 days → skip
3. **Startup grace** — first 90s after boot: log+hash but don't announce

---

## 11. "No item with that key" Error in Analytics

**Symptom**: `WARNING: Conversion correlation error: No item with that key`
in logs whenever Claude answered a Patreon question.

**Root Cause**: The `_free_clicks` SQL query only selected `slug, url, cnt`
but the rendering loop accessed `_r['last_click']`.

**Fix**: Added `MIN(c.clicked_at) first_click, MAX(c.clicked_at) last_click`
to the `_free_clicks` SELECT.

---

## 12. Empty Message 400 Error

**Symptom**: `discord.errors.HTTPException: 400 Cannot send an empty message`
after Claude replied. User saw "Sorry, I couldn't process your question."

**Root Cause**: `await message.channel.send(answer[1900:])` was misindented
inside the `if kb_images:` block and executed unconditionally — including
when `answer` was ≤ 1900 chars, making `answer[1900:]` an empty string.

**Fix**: Moved the remainder send inside the `else` branch with a guard:
```python
else:
    await message.reply(answer[:1900])
    remainder = answer[1900:]
    if remainder.strip():
        await message.channel.send(remainder)
```
