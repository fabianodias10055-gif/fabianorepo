# Link Analytics

## Click Tracking

Every redirect logs a click to the `clicks` table:

```python
def log_click(link_id, country, code, referrer) -> int:
    # Returns the rowid (click_id) for later country update
    with _conn() as db:
        cursor = db.execute(
            "INSERT INTO clicks (link_id, country, country_code, referrer) VALUES (?,?,?,?)",
            (link_id, country, code, referrer)
        )
        return cursor.lastrowid
```

**Why synchronous**: An earlier bug had the click logged in an async background
task — Python's GC killed the task before it ran, resulting in 0 clicks tracked.
Fix: log synchronously first, update country in background.

## Country Resolution

After logging the click, country is resolved in the background:

```python
async def _geo(cid, addr):
    country, code = await lookup_country(addr)
    if country != "Unknown":
        update_click_country(cid, country, code)

task = asyncio.create_task(_geo(click_id, ip))
_bg_tasks.add(task)  # prevent GC
task.add_done_callback(_bg_tasks.discard)
```

`lookup_country()` calls `ip-api.com` — free tier, no key required.

## `_bg_tasks` Set

```python
_bg_tasks: set = set()
```

asyncio tasks are weakly referenced by default. If nothing holds a strong
reference, the GC can kill the task mid-execution. Adding to `_bg_tasks`
keeps it alive until the `done_callback` discards it.

## get_stats()

Returns per-link statistics including country breakdown:

```python
def get_stats(slug, prefix="p") -> dict:
    # Returns: {total_clicks, by_country: [{country, code, count}], last_click}
```

Used by Claude for analytics context when a specific link is mentioned.

## Daily Click Report

Sent to the bot-reports channel at 9 AM São Paulo time alongside the Patreon
summary. Shows:
- Top links by clicks (last 24h)
- Country breakdown per link
- Referrer breakdown

## What Claude Sees

When you ask about a specific link or about analytics, Claude gets injected context:

```
[Link Analytics — locodev.dev/p/patreonbasic]
Total clicks (all time): 142
Last 30 days: 38 clicks
Top countries:
  Brazil: 21 clicks
  USA: 9 clicks
  ...
```
