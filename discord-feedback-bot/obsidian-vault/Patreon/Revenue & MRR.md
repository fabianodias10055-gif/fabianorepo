# Revenue & MRR

## How MRR is Estimated

The bot estimates MRR from the local event log, not from a Patreon API call.
It walks all events chronologically, tracking the latest pledge per member:

```python
active = {}  # member_id → amount
for e in sorted(events, key=lambda x: x["ts"]):
    mid = e.get("member_id")
    if e["event"] == "members:pledge:create" and not e.get("is_trial"):
        active[mid] = e["amount"]
    elif e["event"] == "members:pledge:update":
        active[mid] = e["amount"]
    elif e["event"] in ("members:pledge:delete", "members:delete"):
        active.pop(mid, None)

mrr = sum(active.values())
active_count = len(active)
```

## Limitations

- Only tracks members who joined **after** the bot started logging events
- Historical data before the bot was set up is missing
- Does not account for failed payments (declined status)
- Currency assumes USD

## What Claude Gets (Context Injection)

When you ask Claude about revenue/subscribers, it receives:

```
PATREON REVENUE & MEMBER DATA:
ESTIMATED MRR (based on active pledges in log): $XXX.XX/month
Active paid members tracked: N

LAST 30 DAYS:
  New paid subscribers: N
  Cancellations: N
  Net change: +N

RECENT EVENTS (last 7 days):
  2026-04-12 members:pledge:create — John Doe tier=LocoBasic amount=$5.00
  ...

PATREON LINK CLICKS vs CONVERSIONS (last 30 days):
  /p/patreonbasic — 42 clicks (last: 2026-04-11)
  ...
```

## Real-Time Data Source

For daily/weekly summaries, the bot also calls the Patreon API:
`_fetch_patreon_daily_activity(days=N)` — returns actual paid members
from Patreon's member list filtered by `last_charge_date`.

This is more accurate for "who joined this week" than the local log.
The local log is used for cancellations (Patreon API doesn't expose those easily).

## Pushover Alerts for Revenue Events

| Event | Alert |
|-------|-------|
| New paid member | 💰 New Patron — $X/month |
| Trial conversion | 🔄 Trial Converted — $X/month |
| Tier upgrade | ⬆️ Tier Upgrade — $X/month |
| Payment received | ✅ Payment received — $X |
| Free trial start | 🆓 Free Trial (sound: none) |
