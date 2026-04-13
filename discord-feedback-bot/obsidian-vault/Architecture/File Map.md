# File Map

## Repository Root
```
fabianorepo/
└── discord-feedback-bot/
    ├── bot.py              ← Main bot file (~4200 lines)
    ├── shortener.py        ← URL shortener + click tracking
    ├── migrate_dub.py      ← One-time CSV importer from Dub
    ├── dub_links.csv       ← Exported links from old Dub account
    ├── requirements.txt    ← Python dependencies
    ├── Dockerfile          ← Container build for Railway
    ├── scripts/
    │   └── youtube_ue5_report.py   ← Standalone YouTube report script (legacy)
    └── obsidian-vault/     ← This vault
```

## bot.py Sections (top → bottom)

| Line range | What's there |
|-----------|-------------|
| 1–30 | Imports, constants, env vars |
| 31–110 | Feedback scoring config |
| 399–800 | `message_is_feedback()` and helpers |
| 819–1200 | `/scan_feedback` slash command |
| 1200–1600 | Report slash commands (testimonials, appreciation, etc.) |
| 2200–2310 | `/patreon_reports` slash command |
| 2310–2450 | `/update_link`, `/create_link` slash commands |
| 2450–2520 | `DiscordBot` class init |
| 2520–2640 | `_daily_summary()` background task |
| 2641–2690 | `_watch_unreal_engine_youtube()` background task |
| 2691–2780 | `_weekly_summary()` background task |
| 2780–2820 | `on_ready()` — starts all background tasks |
| 2820–2980 | `on_member_join()` — welcome DM |
| 2982–3760 | `on_message()` — Claude AI responder |
| 3660–3770 | Dedup/idempotency helpers for Patreon |
| 3759–3960 | `patreon_webhook_handler()` |
| 3960–4000 | `start_webhook_server()` |
| 4000–4185 | `main()` — entry point |

## shortener.py Sections

| Section | What's there |
|---------|-------------|
| DB init | `setup_db()`, SQLite schema |
| CRUD | `create_link()`, `get_link()`, `update_link()`, `delete_link()` |
| Stats | `get_stats()`, `get_all_links()` |
| Clicks | `log_click()` → returns click_id, `update_click_country()` |
| Geo | `lookup_country(ip)` — async, uses ip-api.com |
| GC guard | `_bg_tasks` set — prevents asyncio task GC |
| Redirect | `_do_redirect()` — logs click sync, geo in background |
| Routes | `setup_routes()` — registers all URL patterns with aiohttp |
| CSV import | `import_from_csv()` |
