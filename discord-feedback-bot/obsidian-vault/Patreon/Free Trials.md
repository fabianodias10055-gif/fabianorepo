# Patreon Free Trials

## What They Are

Patreon allows creators to offer free trials of paid tiers.
A trial member has access to paid content but hasn't been charged yet.

## Detection Logic

```python
trial_ends_at = attrs.get("trial_ends_at")       # set if on trial, None if not
is_free_trial = bool(trial_ends_at) and amount_cents == 0
```

**Critical**: use `currently_entitled_amount_cents`, NOT `will_pay_amount_cents`

```python
# WRONG — 0 is falsy, falls through to will_pay (full price)
amount_cents = _entitled or _will_pay or 0

# CORRECT — explicit None check
_entitled = attrs.get("currently_entitled_amount_cents")
_will_pay  = attrs.get("will_pay_amount_cents")
amount_cents = _entitled if _entitled is not None else (_will_pay or 0)
```

`will_pay_amount_cents` is the **future** amount if they convert. A trial member
has `currently_entitled_amount_cents = 0` (they pay nothing now).

## Trial States

| State | `amount_cents` | `trial_ends_at` | `is_free_trial` |
|-------|---------------|----------------|----------------|
| Active trial | 0 | future date | True |
| Trial expired (not converted) | 0 | past date | True (still) |
| Trial converted to paid | >0 | any | False |
| Regular paid member | >0 | None | False |

## Conversion Detection

When a `members:pledge:create` arrives for a member_id that previously had
a `is_trial=True` event in the log:

```python
if event == "members:pledge:create" and not is_free_trial and amount_cents > 0:
    prior = _load_events()
    had_trial = any(
        e.get("member_id") == member_id and e.get("is_trial") is True
        for e in prior
    )
    if had_trial:
        _entry["is_trial_conversion"] = True
```

Conversion triggers a special Pushover notification: "🔄 Trial Converted"

## Discord Messages

| Situation | Message |
|-----------|---------|
| Trial starts | 🆓 Name started a **free trial** of LocoBasic |
| Trial converts | 💎 Name joined LocoBasic for $X/month (+ pushover conversion alert) |
| Trial expires without converting | No message (no webhook event for expiry) |

## /trial_stats Command

Shows a summary for the past N days:
- Trials started
- Converted to paid
- Still on trial
- Expired without converting
- Conversion rate %

## Event Log Fields

```json
{
  "event": "members:pledge:create",
  "is_trial": true,
  "trial_ends_at": "2026-05-01T00:00:00+00:00",
  "is_trial_conversion": false
}
```
