# Unreal Engine YouTube Watcher

## What It Does

Polls the Unreal Engine YouTube channel's RSS feed every 30 minutes.
When a new video is detected, posts it to the designated Discord channel.

## Channel

- **YouTube Channel**: Unreal Engine official (`UCBobmJyzsJ6Ll7UbfhI4iwQ`)
- **RSS URL**: `https://www.youtube.com/feeds/videos.xml?channel_id=UCBobmJyzsJ6Ll7UbfhI4iwQ`
- **Discord Channel**: `1481432850212585655` (configurable via `YOUTUBE_NOTIFY_CHANNEL_ID`)

## Discord Message Format

```
🎮 **Unreal Engine** just posted a new video!
**{video title}**
https://www.youtube.com/watch?v={video_id}
```

## Persistence

Seen video IDs are saved to `/app/data/ue_seen_videos.json` so restarts
don't re-announce old videos.

```python
def _load_seen() -> set:
    # Reads list from JSON, returns as set
    
def _save_seen(ids: set):
    # Writes set as list to JSON
```

## First-Run Behaviour

If the JSON file doesn't exist (fresh deploy or new volume):
1. Fetch current RSS feed
2. Seed all current videos into seen set WITHOUT announcing them
3. Save to file
4. From next poll onward, only new videos are announced

This prevents a flood of old video announcements on first deploy.

## Bug That Was Fixed

**Symptom**: Bot stopped posting new Unreal Engine videos.

**Root Cause 1 — Cache miss**:
`self.get_channel(ID)` returned `None` because the channel wasn't in
Discord's local cache. The `if channel:` check then silently skipped posting.

**Fix**: `channel = self.get_channel(ID) or await self.fetch_channel(ID)`

**Root Cause 2 — In-memory seen IDs lost on restart**:
`_ue_seen_video_ids` was a plain `set()` on the class — reset to empty on
every restart. On first poll after restart, ALL current videos got re-seeded
without announcement. If a video posted while the bot was down, it would
be seeded and never announced.

**Fix**: Load from `/app/data/ue_seen_videos.json` on startup.
Save after every new video found.

## Task Lifecycle

Started in `on_ready()`:
```python
if self._youtube_task is None or self._youtube_task.done():
    self._youtube_task = asyncio.create_task(self._watch_unreal_engine_youtube())
```

Exceptions are caught and logged — the task loop continues after any error.
The `await asyncio.sleep(1800)` is outside the try/except so it always runs.
