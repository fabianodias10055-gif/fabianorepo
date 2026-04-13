# Environment Variables

Set in Railway → fabianorepo → Variables.

## Required

| Variable | Purpose |
|----------|---------|
| `DISCORD_BOT_TOKEN` | Discord bot authentication token |
| `ANTHROPIC_API_KEY` | Claude API key for AI responses |
| `PATREON_WEBHOOK_SECRET` | HMAC-MD5 signature key from Patreon webhook settings |
| `PATREON_ACCESS_TOKEN` | Patreon API token for fetching member data |
| `GUILD_ID` | Discord server ID (`1158395981835010098`) |

## Notifications

| Variable | Purpose |
|----------|---------|
| `PUSHOVER_USER_KEY` | Pushover account user key |
| `PUSHOVER_API_TOKEN` | Pushover application token |

## Channel IDs

| Variable | Default | Purpose |
|----------|---------|---------|
| `YOUTUBE_NOTIFY_CHANNEL_ID` | `1481432850212585655` | Where Unreal Engine videos are posted |
| `PATREON_ANNOUNCEMENT_CHANNEL_ID` | `1158395982485147689` | Bot reports / private Patreon events |
| `PATREON_PUBLIC_CHANNEL_ID` | `1490377274749354207` | Public new member announcements |

## Optional

| Variable | Purpose |
|----------|---------|
| `YOUTUBE_API_KEY` | Used by legacy `youtube_ue5_report.py` script (not the watcher) |

## Notes
- All channel ID vars have hardcoded defaults in `bot.py` — Railway vars override them
- Never commit `.env` — Railway injects these at runtime
- `PATREON_WEBHOOK_SECRET` must match exactly what's set in Patreon's webhook dashboard
