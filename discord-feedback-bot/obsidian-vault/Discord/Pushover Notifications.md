# Pushover Notifications

Mobile push notifications sent to the owner's phone via Pushover API.

## Setup

- **User Key**: `PUSHOVER_USER_KEY` env var
- **App Token**: `PUSHOVER_API_TOKEN` env var
- API endpoint: `https://api.pushover.net/1/messages.json`

## Events That Trigger Pushover

| Event | Title | Sound |
|-------|-------|-------|
| New paid member | 💰 New Patron — $X/month | cashregister |
| Trial conversion | 🔄 Trial Converted — $X/month | cashregister |
| Tier upgrade (`pledge:update`) | ⬆️ Tier Upgrade — $X/month | cashregister |
| Payment received (`members:update` active) | ✅ Payment received — $X | cashregister |
| Free trial start | 🆓 Free Trial — TierName | none |

## Events That Do NOT Trigger Pushover

- `members:create` (free join) — no notification
- `members:pledge:delete` (cancellation) — no notification
- `members:update` (declined payment) — Discord only, no push

## Priority Setting

Pushover has priority levels:
- Priority 0 (normal) — no acknowledgement required
- Priority 1 (high) — requires `retry` + `expire` params or API rejects it

**The bot uses priority 0** for all notifications. Priority 1 was tried but
Patreon API rejects requests that are missing the required retry/expire fields.

## Startup Grace

During the first 90 seconds after boot, Pushover is suppressed even if events
arrive. This prevents a flood of "new member" notifications for events that
Patreon retried while the bot was down.

## Implementation

```python
async def _send_pushover(title: str, message: str, sound: str = "pushover"):
    async with aiohttp.ClientSession() as session:
        await session.post("https://api.pushover.net/1/messages.json", data={
            "token": PUSHOVER_API_TOKEN,
            "user": PUSHOVER_USER_KEY,
            "title": title,
            "message": message,
            "sound": sound,
            "priority": 0,
        })
```
