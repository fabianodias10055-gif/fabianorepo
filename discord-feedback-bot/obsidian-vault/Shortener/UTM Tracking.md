# UTM Tracking

## What UTMs Are

UTM parameters are query string tags that tell analytics platforms where traffic
came from. Example:
```
https://blueprint.locodev.dev/?utm_source=youtube&utm_medium=organic_video&utm_campaign=leads_abril
```

## Standard Parameters

| Parameter | What it means | Example |
|-----------|--------------|---------|
| `utm_source` | Where the traffic comes from | `youtube`, `instagram`, `discord` |
| `utm_medium` | How it was delivered | `organic_video`, `paid_ad`, `email` |
| `utm_campaign` | Which campaign | `leads_abril`, `launch_june` |
| `utm_content` | Which specific content (optional) | `pinned_comment`, `bio_link` |
| `utm_term` | Keyword (optional, for paid search) | rarely used |

## Recommended UTMs for LocoAI Videos

For a YouTube video pointing to a Patreon or course page:
```
?utm_source=youtube&utm_medium=organic_video&utm_campaign=<campaign_name>
```

Campaign name examples:
- `leads_abril` (leads from April)
- `ue5_locomotion_launch`
- `blueprint_mastery_promo`

## Creating a Tracked Short Link

Ask the bot in Discord:
```
Create a short link for patreon.com/locodev with utm_source=youtube&utm_medium=organic_video&utm_campaign=leads_abril
```

Bot will use the `[CREATE_LINK]` system to create it and return the short URL.

## Click vs Conversion Correlation

The bot can estimate which links drive free joins vs paid conversions by
comparing click timestamps with Patreon event timestamps:

```
PATREON LINK CLICKS vs CONVERSIONS (last 30 days):
  /p/patreonbasic — 42 clicks (last: 2026-04-11)
  /free/gaspals — 18 clicks (last: 2026-04-09)
```

> Note: Direct attribution isn't possible without user ID tracking. The
> bot correlates by time proximity — clicks shortly before a conversion are
> likely related.

## UTMs in the Shortener

UTM params are preserved through the redirect — the `url` stored in the DB
includes the full UTM query string. The shortener does a pure 302 redirect
with no modification to the destination URL.
