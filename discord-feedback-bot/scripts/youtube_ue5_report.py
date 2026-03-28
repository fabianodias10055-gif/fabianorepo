from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error, parse, request

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"
EMBED_COLOR = 0x9B59B6
DEFAULT_USERNAME = "UE5 Daily Report"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def youtube_get(endpoint: str, params: dict) -> dict:
    query = parse.urlencode(params)
    req = request.Request(
        f"{YOUTUBE_API_URL}/{endpoint}?{query}",
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"YouTube API error {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach YouTube API: {exc.reason}") from exc


def search_ue5_videos(api_key: str, published_after: str, max_results: int = 50) -> list[dict]:
    data = youtube_get("search", {
        "part": "snippet",
        "q": "unreal engine 5 OR UE5",
        "type": "video",
        "publishedAfter": published_after,
        "maxResults": max_results,
        "key": api_key,
    })
    return data.get("items", [])


def get_video_stats(api_key: str, video_ids: list[str]) -> dict[str, dict]:
    if not video_ids:
        return {}
    data = youtube_get("videos", {
        "part": "statistics",
        "id": ",".join(video_ids),
        "key": api_key,
    })
    return {item["id"]: item.get("statistics", {}) for item in data.get("items", [])}


def aggregate_by_channel(videos: list[dict], stats: dict[str, dict]) -> list[dict]:
    channels: dict[str, dict] = {}
    for video in videos:
        snippet = video.get("snippet", {})
        channel_id = snippet.get("channelId", "")
        channel_title = snippet.get("channelTitle", "Unknown")
        video_id = video.get("id", {}).get("videoId", "")

        video_stats = stats.get(video_id, {})
        views = int(video_stats.get("viewCount", 0))

        if channel_id not in channels:
            channels[channel_id] = {
                "channel_id": channel_id,
                "channel_title": channel_title,
                "video_count": 0,
                "total_views": 0,
            }
        channels[channel_id]["video_count"] += 1
        channels[channel_id]["total_views"] += views

    return sorted(channels.values(), key=lambda c: c["total_views"], reverse=True)


def format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def build_embed(top_channels: list[dict], date_label: str) -> dict:
    medals = ["1.", "2.", "3.", "4.", "5."]
    lines = []
    for i, ch in enumerate(top_channels[:5]):
        title = ch["channel_title"]
        views = format_number(ch["total_views"])
        videos = ch["video_count"]
        video_word = "video" if videos == 1 else "videos"
        channel_url = f"https://www.youtube.com/channel/{ch['channel_id']}"
        lines.append(
            f"{medals[i]} **[{title}]({channel_url})** — {views} views ({videos} {video_word})"
        )

    description = "Most viewed channels posting about Unreal Engine 5 in the last 7 days\n\n"
    description += "\n".join(lines) if lines else "No UE5 channels found this week."

    return {
        "title": "Top 5 UE5 YouTube Channels Today",
        "description": description,
        "color": EMBED_COLOR,
        "fields": [
            {"name": "Report Date", "value": date_label, "inline": True},
            {"name": "Search Window", "value": "Last 7 days", "inline": True},
        ],
        "footer": {"text": "Data from YouTube Data API v3"},
    }


def send_to_discord(*, webhook_url: str, username: str, embed: dict) -> None:
    payload = json.dumps({"username": username, "embeds": [embed]}).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30):
            return
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Discord webhook error {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Discord webhook: {exc.reason}") from exc


def main() -> int:
    try:
        api_key = require_env("YOUTUBE_API_KEY")
        webhook_url = require_env("DISCORD_WEBHOOK_URL")
        username = (
            os.getenv("DISCORD_WEBHOOK_USERNAME", DEFAULT_USERNAME).strip()
            or DEFAULT_USERNAME
        )

        now = datetime.now(timezone.utc)
        published_after = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date_label = now.strftime("%b %d, %Y")

        videos = search_ue5_videos(api_key, published_after)
        if not videos:
            print("No UE5 videos found in the last 7 days.", file=sys.stderr)
            return 1

        video_ids = [
            v["id"]["videoId"]
            for v in videos
            if v.get("id", {}).get("videoId")
        ]
        stats = get_video_stats(api_key, video_ids)
        top_channels = aggregate_by_channel(videos, stats)

        embed = build_embed(top_channels, date_label)
        send_to_discord(webhook_url=webhook_url, username=username, embed=embed)
        print(f"Sent UE5 daily report to Discord ({len(top_channels)} channels found).")
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
