from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from urllib import error, parse, request
from zoneinfo import ZoneInfo

import discord
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DEFAULT_ANALYTICS_URL = "https://api.dub.co/analytics"
DEFAULT_TIMEZONE = "America/Sao_Paulo"
DEFAULT_REPORT_LIMIT = 5
DEFAULT_FETCH_LIMIT = 200
DEFAULT_USERNAME = "Dub Daily Report"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)
EMBED_COLOR = 0xF97316
FALLBACK_TIMEZONES: dict[str, tzinfo] = {
    "America/Sao_Paulo": timezone(timedelta(hours=-3), name="America/Sao_Paulo"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a Dub top-links report to Discord."
    )
    parser.add_argument(
        "--window",
        choices=("today", "yesterday", "last-24h"),
        default="today",
        help="Which time window to report on.",
    )
    parser.add_argument(
        "--segment",
        choices=("top", "others"),
        default="top",
        help="Whether to report the main top links or the remaining links after the top list.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report instead of sending it to Discord.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def resolve_timezone(timezone_name: str) -> tzinfo:
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        fallback = FALLBACK_TIMEZONES.get(timezone_name)
        if fallback is not None:
            return fallback
        raise RuntimeError(
            f"No time zone found with key {timezone_name!r}. "
            "Install the Python tzdata package or use a supported timezone value."
        )


def compute_window(window: str, timezone_name: str) -> tuple[datetime, datetime, str]:
    tz = resolve_timezone(timezone_name)
    now = datetime.now(tz)
    target_date = now.date()
    end = now

    if window == "last-24h":
        start = now - timedelta(hours=24)
        label = f"{start.strftime('%b %d, %Y %H:%M')} to {end.strftime('%b %d, %Y %H:%M')}"
        return start, end, label

    if window == "yesterday":
        target_date = target_date - timedelta(days=1)
        end = datetime.combine(
            target_date + timedelta(days=1),
            datetime.min.time(),
            tzinfo=tz,
        )

    start = datetime.combine(target_date, datetime.min.time(), tzinfo=tz)
    label = target_date.strftime("%b %d, %Y")
    return start, end, label


def fetch_top_links(
    *,
    api_key: str,
    analytics_url: str,
    timezone_name: str,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    query = parse.urlencode(
        {
            "event": "clicks",
            "groupBy": "top_links",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timezone": timezone_name,
            "limit": str(limit),
        }
    )
    api_request = request.Request(
        f"{analytics_url}?{query}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="GET",
    )

    try:
        with request.urlopen(api_request, timeout=30) as response:
            payload = json.load(response)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Dub API request failed with {exc.code} {exc.reason}: {body}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Dub API: {exc.reason}") from exc

    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Dub analytics response: {payload!r}")

    return payload[:limit]


def parse_csv_env(name: str) -> set[str]:
    raw_value = os.getenv(name, "")
    return {
        item.strip().lower()
        for item in raw_value.split(",")
        if item.strip()
    }


def normalize_entry(entry: dict[str, Any], index: int) -> dict[str, Any]:
    normalized = dict(entry)
    normalized["label"] = entry_label(entry, index)
    normalized["clicks"] = int(entry.get("clicks") or 0)
    return normalized


def filter_and_merge_top_links(
    top_links: list[dict[str, Any]],
    *,
    excluded_keys: set[str],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for index, entry in enumerate(top_links, start=1):
        key = str(entry.get("key") or "").strip().lower()
        label = entry_label(entry, index)
        if key in excluded_keys or label.lower() in excluded_keys:
            continue

        normalized = normalize_entry(entry, index)
        existing = merged.get(label)
        if existing is None:
            merged[label] = normalized
            continue

        existing["clicks"] = int(existing.get("clicks") or 0) + normalized["clicks"]

    filtered = sorted(
        merged.values(),
        key=lambda item: int(item.get("clicks") or 0),
        reverse=True,
    )
    return filtered


def entry_label(entry: dict[str, Any], index: int) -> str:
    existing_label = str(entry.get("label") or "").strip()
    if existing_label:
        return existing_label
    key = str(entry.get("key") or "").strip()
    short_link = str(entry.get("shortLink") or "").strip()
    if key:
        return f"/{key}"
    if short_link:
        return short_link
    return f"Link {index}"


def compact_label(label: str, max_length: int = 34) -> str:
    if len(label) <= max_length:
        return label
    return label[: max_length - 3] + "..."


def window_label(window: str) -> str:
    if window == "last-24h":
        return "Last 24 Hours"
    if window == "today":
        return "Today"
    if window == "yesterday":
        return "Yesterday"
    return window.replace("-", " ").title()


def leaderboard_lines(top_links: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, entry in enumerate(top_links, start=1):
        label = compact_label(entry_label(entry, index))
        clicks = int(entry.get("clicks") or 0)
        click_word = "click" if clicks == 1 else "clicks"
        lines.append(f"{index}. **{label}** - {clicks} {click_word}")
    return lines


def split_lines_into_fields(
    lines: list[str],
    *,
    field_name: str,
    limit: int = 1024,
) -> list[dict[str, Any]]:
    if not lines:
        return []

    fields: list[dict[str, Any]] = []
    current_lines: list[str] = []
    current_length = 0

    for line in lines:
        addition = len(line) + (1 if current_lines else 0)
        if current_lines and current_length + addition > limit:
            fields.append(
                {
                    "name": field_name if not fields else f"{field_name} (cont.)",
                    "value": "\n".join(current_lines),
                    "inline": False,
                }
            )
            current_lines = [line]
            current_length = len(line)
            continue

        current_lines.append(line)
        current_length += addition

    if current_lines:
        fields.append(
            {
                "name": field_name if not fields else f"{field_name} (cont.)",
                "value": "\n".join(current_lines),
                "inline": False,
            }
        )

    return fields


def build_report_message(
    *,
    report_label: str,
    window: str,
    top_links: list[dict[str, Any]],
    segment: str,
) -> str:
    report_title = "Dub Click Report" if segment == "top" else "Dub Other Clicks Report"
    if not top_links:
        return f"{report_title}\n{window_label(window)}\n{report_label}\nNo clicks recorded."

    winner = top_links[0]
    winner_label = entry_label(winner, 1)
    winner_clicks = int(winner.get("clicks") or 0)
    total_clicks = sum(int(entry.get("clicks") or 0) for entry in top_links)

    lines = [
        report_title,
        f"Window: {window_label(window)}",
        f"Period: {report_label}",
        f"Winner: {winner_label} with {winner_clicks} clicks",
        f"{'Top' if segment == 'top' else 'Other'} {len(top_links)} total: {total_clicks} clicks",
        "",
        "Leaderboard:",
    ]
    lines.extend(line.replace("**", "") for line in leaderboard_lines(top_links))
    return "\n".join(lines)


def build_report_embed(
    *,
    report_label: str,
    window: str,
    top_links: list[dict[str, Any]],
    segment: str,
) -> dict[str, Any]:
    report_title = "Dub Click Report" if segment == "top" else "Dub Other Clicks Report"
    if not top_links:
        return {
            "title": report_title,
            "description": "No clicks were recorded in this period.",
            "color": EMBED_COLOR,
            "fields": [
                {"name": "Window", "value": window_label(window), "inline": True},
                {"name": "Report Period", "value": report_label, "inline": False},
            ],
        }

    winner = top_links[0]
    winner_label = entry_label(winner, 1)
    winner_clicks = int(winner.get("clicks") or 0)
    total_clicks = sum(int(entry.get("clicks") or 0) for entry in top_links)
    winner_share = round((winner_clicks / total_clicks) * 100) if total_clicks else 0
    leaderboard_name = "Top 5 Leaderboard" if segment == "top" else "Other Clicks"
    fields: list[dict[str, Any]] = [
        {"name": "Report Period", "value": report_label, "inline": False},
        {"name": "Top Link", "value": f"**{winner_label}**", "inline": True},
        {"name": "Winner Clicks", "value": f"**{winner_clicks}**", "inline": True},
        {"name": "Winner Share", "value": f"**{winner_share}%**", "inline": True},
        {
            "name": "Top 5 Total" if segment == "top" else "Other Clicks Total",
            "value": f"**{total_clicks}** clicks",
            "inline": False,
        },
    ]
    fields.extend(
        split_lines_into_fields(
            leaderboard_lines(top_links),
            field_name=leaderboard_name,
        )
    )

    return {
        "title": report_title,
        "description": (
            f"Performance overview for **{window_label(window)}**"
            if segment == "top"
            else f"All remaining clicked links for **{window_label(window)}** after the top 5"
        ),
        "color": EMBED_COLOR,
        "fields": fields,
    }


def send_to_discord(
    *,
    webhook_url: str,
    username: str,
    embed: dict[str, Any],
) -> None:
    payload = json.dumps({"username": username, "embeds": [embed]}).encode("utf-8")
    webhook_request = request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="POST",
    )

    try:
        with request.urlopen(webhook_request, timeout=30):
            return
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Discord webhook request failed with {exc.code} {exc.reason}: {body}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Discord webhook: {exc.reason}") from exc


def send_bot_dm(*, bot_token: str, user_id: str, embed_payload: dict[str, Any]) -> None:
    async def _send() -> None:
        intents = discord.Intents.none()
        client = discord.Client(intents=intents)

        @client.event
        async def on_ready() -> None:
            try:
                user = await client.fetch_user(int(user_id))
                await user.send(embed=discord.Embed.from_dict(embed_payload))
            finally:
                await client.close()

        await client.start(bot_token)

    try:
        asyncio.run(_send())
    except Exception as exc:
        raise RuntimeError(f"Discord bot DM failed: {exc}") from exc


def main() -> int:
    args = parse_args()

    try:
        api_key = require_env("DUB_API_KEY")
        timezone_name = os.getenv("DUB_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
        analytics_url = os.getenv("DUB_ANALYTICS_URL", DEFAULT_ANALYTICS_URL).strip() or DEFAULT_ANALYTICS_URL
        report_limit = int(os.getenv("DUB_REPORT_LIMIT", str(DEFAULT_REPORT_LIMIT)))
        fetch_limit = int(os.getenv("DUB_FETCH_LIMIT", str(DEFAULT_FETCH_LIMIT)))
        webhook_username = os.getenv("DISCORD_WEBHOOK_USERNAME", DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
        excluded_keys = parse_csv_env("DUB_EXCLUDED_KEYS")
        start, end, report_label = compute_window(args.window, timezone_name)

        raw_top_links = fetch_top_links(
            api_key=api_key,
            analytics_url=analytics_url,
            timezone_name=timezone_name,
            start=start,
            end=end,
            limit=max(report_limit, fetch_limit),
        )
        merged_links = filter_and_merge_top_links(
            raw_top_links,
            excluded_keys=excluded_keys,
        )
        if args.segment == "top":
            selected_links = merged_links[:report_limit]
        else:
            selected_links = merged_links[report_limit:]

        embed = build_report_embed(
            report_label=report_label,
            window=args.window,
            top_links=selected_links,
            segment=args.segment,
        )

        if args.dry_run:
            print(
                build_report_message(
                    report_label=report_label,
                    window=args.window,
                    top_links=selected_links,
                    segment=args.segment,
                )
            )
            return 0

        webhook_url = require_env("DISCORD_WEBHOOK_URL")
        send_to_discord(
            webhook_url=webhook_url,
            username=webhook_username,
            embed=embed,
        )

        dm_user_id = os.getenv("DISCORD_DM_USER_ID", "").strip()
        if dm_user_id:
            bot_token = require_env("DISCORD_BOT_TOKEN")
            send_bot_dm(
                bot_token=bot_token,
                user_id=dm_user_id,
                embed_payload=embed,
            )
            print("Sent Dub daily report to Discord webhook and bot DM.")
            return 0

        print("Sent Dub daily report to Discord.")
        return 0
    except Exception as exc:  # pragma: no cover - CLI entrypoint
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
