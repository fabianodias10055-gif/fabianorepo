# URL Shortener — How It Works

## Database Schema

SQLite at `/app/data/shortener.db`

```sql
CREATE TABLE links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    prefix     TEXT NOT NULL DEFAULT 'p',
    slug       TEXT NOT NULL,
    url        TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(prefix, slug)
);

CREATE TABLE clicks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id     INTEGER REFERENCES links(id),
    country     TEXT DEFAULT 'Unknown',
    country_code TEXT DEFAULT '??',
    referrer    TEXT DEFAULT 'direct',
    clicked_at  TEXT DEFAULT (datetime('now'))
);
```

## URL Format

| URL | prefix | slug |
|-----|--------|------|
| `locodev.dev/p/patreonbasic` | `p` | `patreonbasic` |
| `locodev.dev/download/ledgepremium/abc123` | `download` | `ledgepremium` |
| `locodev.dev/docs/weaponstandard` | `docs` | `weaponstandard` |
| `locodev.dev/uecourse` | `p` (default) | `uecourse` |

## Known Prefixes

| Prefix | Used for |
|--------|---------|
| `p` | Patreon page links |
| `download` | Patreon content download links |
| `docs` | Documentation links |
| `free` | Free tier links |
| `freebuild` | Free build content |

## Redirect Flow

```
User visits locodev.dev/p/patreonbasic
→ aiohttp matches route
→ get_link("patreonbasic", "p") queries SQLite
→ if found: log_click() synchronously (returns click_id)
→ background task: lookup_country(ip) → update_click_country(click_id)
→ return 302 redirect to stored URL
→ if not found: 404
```

## Link CSV Migration

On startup, `dub_links.csv` is imported via `import_from_csv()`.
Existing slugs are skipped (INSERT OR IGNORE). The CSV was exported from
the old Dub short link service before it was replaced with this custom shortener.

## Startup Link Patches

For one-off URL updates, a `_link_patches` list in `bot.py` runs `update_link()`
on every boot. It's idempotent — updating to the same URL has no side effect.

```python
_link_patches = [
    ("uecourse", "p", "https://blueprint.locodev.dev/?utm_source=youtube&..."),
]
```

## See Also
- [[Analytics]]
- [[UTM Tracking]]
- [[Link Management]]
