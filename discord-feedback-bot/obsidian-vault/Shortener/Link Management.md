# Link Management

## CRUD Functions (shortener.py)

```python
create_link(slug, url, prefix="p") -> bool
get_link(slug, prefix="p") -> dict | None
update_link(slug, new_url, prefix="p") -> bool
delete_link(slug, prefix="p") -> bool
get_all_links() -> list[dict]
```

## Slash Commands

| Command | What it does |
|---------|-------------|
| `/create_link slug:patreonbasic url:https://... prefix:p` | Creates new short link |
| `/update_link slug:uecourse url:https://... prefix:p` | Updates destination URL |

## Creating Links via Chat (Claude)

You can ask the bot in natural language:
```
Create a short link locodev.dev/p/bowarrowsystem for patreon.com/posts/85419167
```

Claude outputs a `[CREATE_LINK]` marker which the bot intercepts and executes:
```
[CREATE_LINK: p/bowarrowsystem → https://patreon.com/posts/85419167]
```

See [[AI-Claude/CREATE LINK System]] for full details.

## Startup Link Patches

For one-off URL updates that need to happen on the live Railway DB,
add an entry to `_link_patches` in `bot.py`:

```python
_link_patches = [
    ("slug", "prefix", "https://new-url.com"),
]
```

Runs on every boot via `update_link()`. Safe to leave permanently — it's
idempotent (updates to same URL are a no-op).

## Slug Rules (enforced for Claude)

- Lowercase only
- No spaces (use hyphens)
- No special characters except `-`
- Must not already exist (Claude checks `get_all_links()` before suggesting)
- Short and descriptive

## CSV Migration

`dub_links.csv` format (from Dub export):
```csv
url,destinationUrl,clicks,createdAt
https://locodev.dev/p/patreonbasic,https://patreon.com/locodev,133,2026-02-25
```

The importer parses the `url` field to extract prefix and slug, then calls
`create_link()` with INSERT OR IGNORE — existing slugs are never overwritten.
