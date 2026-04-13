# Railway Setup

## Service

- **Project**: fabianorepo
- **Service**: locodev.dev
- **Region**: us-west2
- **Replicas**: 1

## Volume

Mounted at `/app/data/` — **all persistent data lives here**.

Without the volume, data is lost on every redeploy. The volume survives:
- Redeploys
- Restarts
- Code updates

Files stored:
- `shortener.db` — all links and click history
- `patreon_events.json` — Patreon event log
- `patreon_webhook_seen.json` — webhook idempotency hashes
- `ue_seen_videos.json` — YouTube seen video IDs
- `knowledge_base.json` — bot Q&A knowledge base

## Port

Bot listens on **port 8080** (aiohttp). Railway routes external traffic to it.

## Auto-Deploy

Railway watches the `master` branch on GitHub. Any push to `master` triggers:
1. Docker build
2. Container swap (zero-downtime)
3. Bot restarts → startup grace period (90s) → normal operation

## Startup Sequence

```
1. setup_db()              — initialise SQLite if new volume
2. import_from_csv()       — migrate dub_links.csv (skips existing slugs)
3. link patches            — update_link() for any hardcoded URL changes
4. client.start(TOKEN)     — connect to Discord
5. on_ready()              — start background tasks
6. _watch_unreal_engine_youtube() — load seen IDs from file, begin polling
```

## Redeploy Workflow

1. Push code to `master` (or merge feature branch)
2. Railway detects push → builds → deploys
3. Check Railway logs for `Logged in as LocoDev#8301` — confirms healthy start
4. Check for `Link patch applied` lines if URL changes were made

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Bot offline | Railway logs for Python exceptions at startup |
| Links not redirecting | `shortener.db` on volume, check `setup_db()` ran |
| Patreon events missing | Check PATREON_WEBHOOK_SECRET matches Patreon dashboard |
| YouTube not posting | Check `ue_seen_videos.json` exists; look for watcher errors in logs |
