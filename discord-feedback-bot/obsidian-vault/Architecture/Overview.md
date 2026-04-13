# Architecture Overview

## What the Bot Is

A **Discord.py bot** combined with an **aiohttp web server**, both running in the same process on Railway. It handles:
- Discord messages and slash commands
- Patreon webhook events
- URL shortener redirects and click tracking
- YouTube RSS polling

## Process Structure

```
python bot.py
├── asyncio event loop
│   ├── Discord client (discord.py)
│   │   ├── on_message → Claude AI responder
│   │   ├── on_member_join → welcome DM + role
│   │   └── Slash commands (/scan_feedback, /patreon_reports, /fix_roles, etc.)
│   ├── Background tasks
│   │   ├── _rotate_status() — cycles bot status message
│   │   ├── _daily_summary() — 9 AM São Paulo daily Patreon report
│   │   ├── _weekly_summary() — Monday 9 AM weekly report
│   │   └── _watch_unreal_engine_youtube() — polls RSS every 30 min
│   └── aiohttp web server (port 8080)
│       ├── POST /patreon/webhook → patreon_webhook_handler()
│       └── URL shortener routes (shortener.py)
```

## Persistent Data (Railway Volume at `/app/data/`)

| File | Purpose |
|------|---------|
| `shortener.db` | SQLite — links + clicks tables |
| `patreon_events.json` | Patreon event log (90-day rolling) |
| `patreon_webhook_seen.json` | SHA256 hashes of processed webhooks (30-day TTL) |
| `ue_seen_videos.json` | YouTube video IDs already announced |
| `knowledge_base.json` | Bot Q&A knowledge base from Discord |

## Key Design Decisions

- **Single process** — Discord + HTTP in one asyncio loop; no separate workers
- **SQLite not Postgres** — simple, file-based, zero infra; fine for current scale
- **aiohttp not FastAPI** — lightweight, already a dependency of discord.py
- **Railway volume** — data survives redeploys; path `/app/data/` hardcoded
- **Claude via Anthropic API** — `claude-sonnet-4-6` (or latest) for all AI responses

## See Also
- [[File Map]]
- [[Environment Variables]]
- [[Deployment/Railway Setup]]
