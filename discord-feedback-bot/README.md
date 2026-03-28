# Discord Feedback Bot

Python bot that scans readable Discord text channels, finds appreciation comments about your work, and saves the results to JSON.

## What It Does

- Adds `/scan_feedback` to scan all readable text channels in a server
- Adds `/scan_channel` to scan one selected text channel
- Scores messages with a gratitude-and-praise detector
- Exports results into `data/*.json`

## Requirements

- Python 3.11+
- A Discord bot application
- Bot permissions to view channels and read message history
- Message Content intent enabled in the Discord Developer Portal

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your values.
   - Set `CREATOR_ALIASES` to names people use for you or your brand
4. In the Discord Developer Portal:
   - Enable `MESSAGE CONTENT INTENT`
   - Invite the bot with permissions to read channels and message history
5. Start the bot:

```bash
python bot.py
```

## Commands

- `/scan_feedback`
- `/scan_feedback limit_per_channel:500`
- `/scan_channel channel:#feedback`

If `DISCORD_GUILD_ID` is set, slash commands sync faster for that server while you test.

## Notes

- This starter scans standard text channels, not forum posts or threads.
- The detector is tuned for praise and gratitude such as `thank you`, `saved my day`, or `great tutorial`.
- `CREATOR_ALIASES` helps match comments aimed at you, such as `locodev` or `locodevbot`.
- Results are saved locally on the machine running the bot.

## Next Improvements

- Save to CSV or SQLite
- Add better NLP or AI classification
- Support forum channels and threads
- Filter to channels with names like `feedback`, `suggestions`, or `bug-reports`

## Dub Daily Report

This repo also includes a small script that pulls your top Dub links for the day and posts the winner to a Discord webhook.

### Extra setup

Add these values to `.env`:

```bash
DUB_API_KEY=your-dub-workspace-api-key
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DUB_TIMEZONE=America/Sao_Paulo
DUB_REPORT_LIMIT=5
DUB_FETCH_LIMIT=200
DUB_EXCLUDED_KEYS=_root
DISCORD_WEBHOOK_USERNAME=Dub Daily Report
DISCORD_DM_USER_ID=your-discord-user-id-for-bot-dms
```

### Test the report without sending

```bash
py scripts/dub_daily_report.py --window today --dry-run
```

### Send the report to Discord

```bash
py scripts/dub_daily_report.py --window today
```

If you schedule it to run after midnight, use `--window yesterday` so the report covers the full completed day.

For a rolling report that covers the last 24 hours instead of a calendar day, use:

```bash
py scripts/dub_daily_report.py --window last-24h
```

To send the remaining links after the top 5, use:

```bash
py scripts/dub_daily_report.py --window last-24h --segment others
```

If `DISCORD_DM_USER_ID` is set, the same report is also sent as a private DM using your bot token.

If you want to ignore specific short links entirely, set `DUB_EXCLUDED_KEYS` to a comma-separated list such as `_root`.

### Run it in the cloud with GitHub Actions

This repo includes a workflow at `.github/workflows/dub-daily-report.yml`.

It is scheduled for `12:00 UTC` every day, which is `9:00 AM` in `America/Sao_Paulo` on March 27, 2026.

To enable it:

1. Push this repository to GitHub.
2. In your GitHub repository, add these Actions secrets:
   - `DUB_API_KEY`
   - `DISCORD_WEBHOOK_URL`
3. Keep the workflow file on the default branch.
4. Optionally run it once from the Actions tab with `workflow_dispatch`.

If you keep the Windows scheduled task enabled after turning on GitHub Actions, you will get duplicate Discord messages.
