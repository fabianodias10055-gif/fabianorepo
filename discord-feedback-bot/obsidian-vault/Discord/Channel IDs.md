# Discord Channel IDs

## Guild

| Item | ID |
|------|----|
| Server (Guild) | `1158395981835010098` |

## Channels Used by the Bot

| Channel | ID | Purpose |
|---------|----|---------|
| Bot reports / Patreon private | `1158395982485147689` | All Patreon events, daily/weekly summaries |
| Public Patreon members | `1490377274749354207` | New paid member public announcements |
| Unreal Engine YouTube | `1481432850212585655` | New UE5 video notifications |

## Env Var Overrides

These channels can be overridden via Railway environment variables:
- `PATREON_ANNOUNCEMENT_CHANNEL_ID`
- `PATREON_PUBLIC_CHANNEL_ID`
- `YOUTUBE_NOTIFY_CHANNEL_ID`

## Channel Cache Issue (Fixed)

`client.get_channel(id)` returns `None` if the channel isn't in Discord's local
cache (common for channels the bot hasn't recently seen traffic in).

**Always use the pattern:**
```python
channel = client.get_channel(ID) or await client.fetch_channel(ID)
```

This was the cause of:
- YouTube notifications not posting to channel `1481432850212585655`
- Patreon announcements not posting to `1490377274749354207`
