import asyncio
import csv
import json
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

import discord
from discord import app_commands
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data"
TESTIMONIALS_PATH = OUTPUT_DIR / "testimonials.json"
MESSAGE_LINK_RE = re.compile(
    r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)"
)
CHANNEL_LINK_RE = re.compile(
    r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)(?:/(\d+))?"
)

load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
PATREON_WEBHOOK_SECRET = os.getenv("PATREON_WEBHOOK_SECRET", "")
PATREON_ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("PATREON_ANNOUNCEMENT_CHANNEL_ID", "1487222304277663794"))
PATREON_PUBLIC_CHANNEL_ID = int(os.getenv("PATREON_PUBLIC_CHANNEL_ID", "1158395982485147689"))
YOUTUBE_NOTIFY_CHANNEL_ID = int(os.getenv("YOUTUBE_NOTIFY_CHANNEL_ID", "1481432850212585655"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MAX_MESSAGES_PER_CHANNEL = int(os.getenv("MAX_MESSAGES_PER_CHANNEL", "250"))
PROJECTS_FORUM_CHANNEL_ID = os.getenv("PROJECTS_FORUM_CHANNEL_ID")
CREATOR_ALIASES = tuple(
    alias.strip().lower()
    for alias in os.getenv("CREATOR_ALIASES", "locodev,locodevbot,loco").split(",")
    if alias.strip()
)
OUTPUT_DIR.mkdir(exist_ok=True)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord-feedback-bot")


GRATITUDE_KEYWORDS = {
    "thank you": 4,
    "thanks": 3,
    "tysm": 4,
    "appreciate": 4,
    "grateful": 4,
    "saved my day": 5,
    "saved me": 4,
    "helped me": 4,
    "helpful": 3,
    "this helped": 4,
    "super helpful": 4,
    "so helpful": 4,
}

PRAISE_KEYWORDS = {
    "amazing": 2,
    "awesome": 2,
    "great": 1,
    "love this": 3,
    "legend": 3,
    "goat": 3,
    "incredible": 2,
    "perfect": 2,
    "fantastic": 2,
    "brilliant": 2,
    "fire": 1,
}

WORK_KEYWORDS = {
    "tutorial": 3,
    "system": 3,
    "guide": 3,
    "course": 3,
    "video": 2,
    "tool": 2,
    "bot": 2,
    "setup": 2,
    "method": 2,
    "workflow": 2,
    "community": 1,
    "server": 1,
    "content": 2,
}

ISSUE_KEYWORDS = {
    "feedback": 4,
    "suggestion": 3,
    "recommend": 3,
    "improve": 3,
    "issue": 2,
    "problem": 2,
    "bug": 3,
    "broken": 3,
    "feature": 2,
    "idea": 2,
    "wish": 2,
    "request": 2,
    "confusing": 2,
    "difficult": 2,
    "annoying": 2,
    "please add": 3,
    "would like": 3,
    "could you": 3,
    "it would be nice": 3,
    "should have": 2,
    "i want": 2,
    "i wish": 2,
    "please fix": 4,
    "not working": 4,
}

POSITIVE_SENTIMENT = {
    "thank you": 3,
    "thanks": 2,
    "amazing": 2,
    "awesome": 2,
    "great": 1,
    "helpful": 2,
    "love": 2,
    "perfect": 2,
    "incredible": 2,
    "best": 2,
    "saved": 2,
}

NEGATIVE_SENTIMENT = {
    "bug": 2,
    "broken": 3,
    "issue": 2,
    "problem": 2,
    "bad": 2,
    "hate": 2,
    "confusing": 2,
    "hard": 1,
    "difficult": 2,
    "annoying": 2,
    "not working": 3,
    "please fix": 3,
}

TARGET_PRONOUNS = ("you", "your", "ur")
STRONG_APPRECIATION_PHRASES = (
    "thank you so much",
    "thanks so much",
    "thank you for",
    "thanks for",
    "you saved my day",
    "you saved me",
    "love your",
    "great tutorial",
    "great guide",
    "amazing tutorial",
    "amazing guide",
)
STRONG_ISSUE_PHRASES = (
    "would be better",
    "doesn't work",
    "does not work",
    "hard to use",
    "please fix",
    "not working",
    "can you add",
)


@dataclass
class MatchResult:
    score: int
    reasons: list[str]
    metadata: dict[str, str] | None = None


def clamp_limit(limit: int) -> int:
    return max(1, min(limit, 2000))


def contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def clean_snippet(text: str, limit: int = 140) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def export_path(guild: discord.Guild, kind: str, extension: str = "json") -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_name = "".join(char if char.isalnum() or char in "-_" else "-" for char in guild.name)
    return OUTPUT_DIR / f"{safe_name}-{guild.id}-{kind}-{timestamp}.{extension}"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def write_csv(path: Path, results: list[dict]) -> None:
    fieldnames = [
        "guild_name",
        "channel_name",
        "author_name",
        "created_at",
        "score",
        "content",
        "jump_url",
        "reasons",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "guild_name": item.get("guild_name", ""),
                    "channel_name": item.get("channel_name", ""),
                    "author_name": item.get("author_name", ""),
                    "created_at": item.get("created_at", ""),
                    "score": item.get("score", ""),
                    "content": item.get("content", ""),
                    "jump_url": item.get("jump_url", ""),
                    "reasons": "; ".join(item.get("reasons", [])),
                }
            )


def load_latest_payload(kind: str) -> tuple[dict, Path] | None:
    matches = sorted(OUTPUT_DIR.glob(f"*-{kind}-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        return None

    path = matches[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload, path


def load_testimonials() -> list[dict]:
    if not TESTIMONIALS_PATH.exists():
        return []
    return json.loads(TESTIMONIALS_PATH.read_text(encoding="utf-8"))


def save_testimonials(entries: list[dict]) -> None:
    write_json(TESTIMONIALS_PATH, entries)


def is_command_like(content: str) -> bool:
    return content.startswith(("!", "/", "."))


def creator_alias_hits(lowered: str) -> list[str]:
    return [alias for alias in CREATOR_ALIASES if contains_phrase(lowered, alias)]


def pronoun_targeted(lowered: str) -> bool:
    return any(contains_phrase(lowered, pronoun) for pronoun in TARGET_PRONOUNS)


def work_reference_hits(lowered: str) -> list[str]:
    return [phrase for phrase in WORK_KEYWORDS if phrase in lowered]


def creator_or_work_context(lowered: str) -> bool:
    return bool(creator_alias_hits(lowered) or pronoun_targeted(lowered) or work_reference_hits(lowered))


def normalize_channel_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def find_projects_forum_channel(guild: discord.Guild) -> discord.ForumChannel | None:
    if PROJECTS_FORUM_CHANNEL_ID:
        channel = guild.get_channel(int(PROJECTS_FORUM_CHANNEL_ID))
        if isinstance(channel, discord.ForumChannel):
            return channel

    preferred_names = {
        "projectslocodev",
        "projectlocodev",
        "locodevprojects",
        "projects",
    }

    for channel in guild.forums:
        if normalize_channel_name(channel.name) in preferred_names:
            return channel

    return None


async def resolve_project_post(
    guild: discord.Guild,
    post_link: str,
) -> tuple[discord.Thread, discord.Message] | tuple[None, None]:
    match = CHANNEL_LINK_RE.fullmatch(post_link.strip())
    if not match:
        return None, None

    guild_id, channel_or_thread_id, message_id = (match.group(1), match.group(2), match.group(3))
    if int(guild_id) != guild.id:
        return None, None

    channel = guild.get_channel(int(channel_or_thread_id))
    if channel is None:
        try:
            channel = await guild.fetch_channel(int(channel_or_thread_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None, None

    if not isinstance(channel, discord.Thread):
        return None, None

    if not isinstance(channel.parent, discord.ForumChannel):
        return None, None

    starter_message_id = int(message_id) if message_id else channel.id
    try:
        starter_message = await channel.fetch_message(starter_message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None, None

    return channel, starter_message


def appreciation_from_text(content: str) -> MatchResult | None:
    text = content.strip()
    if len(text) < 8 or is_command_like(text):
        return None

    lowered = text.lower()
    score = 0
    reasons: list[str] = []
    has_gratitude = False
    has_target = False
    has_work_reference = False

    for phrase, weight in GRATITUDE_KEYWORDS.items():
        if phrase in lowered:
            score += weight
            reasons.append(f"gratitude '{phrase}'")
            has_gratitude = True

    for phrase, weight in PRAISE_KEYWORDS.items():
        if phrase in lowered:
            score += weight
            reasons.append(f"praise '{phrase}'")

    for phrase, weight in WORK_KEYWORDS.items():
        if phrase in lowered:
            score += weight
            reasons.append(f"work reference '{phrase}'")
            has_work_reference = True

    for alias in creator_alias_hits(lowered):
        score += 4
        reasons.append(f"creator alias '{alias}'")
        has_target = True

    if pronoun_targeted(lowered):
        score += 2
        reasons.append("directed at creator")
        has_target = True

    if any(phrase in lowered for phrase in STRONG_APPRECIATION_PHRASES):
        score += 3
        reasons.append("strong appreciation phrase")
        has_gratitude = True
        has_target = True

    if not has_gratitude:
        return None

    if not (has_target or has_work_reference):
        return None

    if score < 6:
        return None

    return MatchResult(score=score, reasons=reasons)


def message_is_feedback(message: discord.Message) -> MatchResult | None:
    return appreciation_from_text(message.content or "")


def issue_from_text(content: str) -> MatchResult | None:
    text = content.strip()
    if len(text) < 8 or is_command_like(text):
        return None

    lowered = text.lower()
    score = 0
    reasons: list[str] = []
    has_issue = False
    has_context = False

    for phrase, weight in ISSUE_KEYWORDS.items():
        if phrase in lowered:
            score += weight
            reasons.append(f"issue '{phrase}'")
            has_issue = True

    for phrase, weight in WORK_KEYWORDS.items():
        if phrase in lowered:
            score += weight
            reasons.append(f"work reference '{phrase}'")
            has_context = True

    for alias in creator_alias_hits(lowered):
        score += 3
        reasons.append(f"creator alias '{alias}'")
        has_context = True

    if pronoun_targeted(lowered):
        score += 1
        reasons.append("directed at creator")
        has_context = True

    if any(phrase in lowered for phrase in STRONG_ISSUE_PHRASES):
        score += 2
        reasons.append("strong issue phrase")
        has_issue = True

    if "?" in lowered and any(word in lowered for word in ("could", "would", "can", "why")):
        score += 1
        reasons.append("question-shaped request")
        has_issue = True

    if not has_issue or not has_context or score < 5:
        return None

    return MatchResult(score=score, reasons=reasons)


def creator_mention_from_text(content: str) -> MatchResult | None:
    text = content.strip()
    if len(text) < 3 or is_command_like(text):
        return None

    lowered = text.lower()
    aliases = creator_alias_hits(lowered)
    if not aliases:
        return None

    reasons = [f"creator alias '{alias}'" for alias in aliases]
    score = 3 * len(aliases)

    if appreciation_from_text(text):
        score += 3
        reasons.append("appreciation context")
    elif issue_from_text(text):
        score += 2
        reasons.append("issue context")

    return MatchResult(score=score, reasons=reasons)


def sentiment_from_text(content: str) -> MatchResult | None:
    text = content.strip()
    if len(text) < 5 or is_command_like(text):
        return None

    lowered = text.lower()
    if not creator_or_work_context(lowered):
        return None

    positive = 0
    negative = 0
    reasons: list[str] = []

    for phrase, weight in POSITIVE_SENTIMENT.items():
        if phrase in lowered:
            positive += weight
            reasons.append(f"positive '{phrase}'")

    for phrase, weight in NEGATIVE_SENTIMENT.items():
        if phrase in lowered:
            negative += weight
            reasons.append(f"negative '{phrase}'")

    if positive == 0 and negative == 0:
        label = "neutral"
        score = 1
        reasons.append("creator/work context")
    elif positive > negative:
        label = "positive"
        score = positive - negative
    elif negative > positive:
        label = "negative"
        score = negative - positive
    else:
        label = "neutral"
        score = positive

    return MatchResult(score=max(1, score), reasons=reasons, metadata={"sentiment": label})


def build_record(
    guild: discord.Guild,
    channel: discord.abc.GuildChannel,
    message: discord.Message,
    match: MatchResult,
) -> dict:
    record = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "channel_id": channel.id,
        "channel_name": channel.name,
        "message_id": message.id,
        "author_id": message.author.id,
        "author_name": str(message.author),
        "created_at": message.created_at.isoformat(),
        "jump_url": message.jump_url,
        "content": message.content,
        "score": match.score,
        "reasons": match.reasons,
    }
    if match.metadata:
        record.update(match.metadata)
    return record


async def scan_text_channels(
    guild: discord.Guild,
    channels: Iterable[discord.TextChannel],
    limit_per_channel: int,
    matcher: Callable[[discord.Message], MatchResult | None],
    *,
    after: datetime | None = None,
    author_id: int | None = None,
) -> tuple[list[dict], list[str]]:
    results: list[dict] = []
    skipped: list[str] = []
    me = guild.me

    for channel in channels:
        permissions = channel.permissions_for(me) if me else None
        if not permissions or not permissions.view_channel or not permissions.read_message_history:
            skipped.append(f"{channel.name}: missing permissions")
            continue

        logger.info("Scanning #%s in guild %s", channel.name, guild.name)
        try:
            async for message in channel.history(limit=limit_per_channel, after=after):
                if message.author.bot:
                    continue
                if author_id is not None and message.author.id != author_id:
                    continue

                match = matcher(message)
                if not match:
                    continue

                results.append(build_record(guild, channel, message, match))
        except discord.Forbidden:
            skipped.append(f"{channel.name}: Discord denied history access")
        except discord.HTTPException as exc:
            skipped.append(f"{channel.name}: HTTP error {exc.status}")

        await asyncio.sleep(0)

    results.sort(key=lambda item: item["score"], reverse=True)
    return results, skipped


async def scan_bug_praise_channels(
    guild: discord.Guild,
    channels: Iterable[discord.TextChannel],
    limit_per_channel: int,
    *,
    after: datetime | None = None,
) -> tuple[list[dict], list[dict], list[str]]:
    praise_results: list[dict] = []
    issue_results: list[dict] = []
    skipped: list[str] = []
    me = guild.me

    for channel in channels:
        permissions = channel.permissions_for(me) if me else None
        if not permissions or not permissions.view_channel or not permissions.read_message_history:
            skipped.append(f"{channel.name}: missing permissions")
            continue

        logger.info("Scanning split view for #%s in guild %s", channel.name, guild.name)
        try:
            async for message in channel.history(limit=limit_per_channel, after=after):
                if message.author.bot:
                    continue

                praise = message_is_feedback(message)
                if praise:
                    praise_results.append(build_record(guild, channel, message, praise))

                issue = issue_from_text(message.content or "")
                if issue:
                    issue_results.append(build_record(guild, channel, message, issue))
        except discord.Forbidden:
            skipped.append(f"{channel.name}: Discord denied history access")
        except discord.HTTPException as exc:
            skipped.append(f"{channel.name}: HTTP error {exc.status}")

        await asyncio.sleep(0)

    praise_results.sort(key=lambda item: item["score"], reverse=True)
    issue_results.sort(key=lambda item: item["score"], reverse=True)
    return praise_results, issue_results, skipped


def extract_reason_values(results: list[dict], prefix: str) -> Counter:
    counter: Counter = Counter()
    prefix_text = f"{prefix} '"
    for item in results:
        for reason in item.get("reasons", []):
            if not reason.startswith(prefix_text):
                continue
            value = reason[len(prefix_text) : -1]
            counter[value] += 1
    return counter


def format_top_results(results: list[dict], limit: int = 5) -> str:
    if not results:
        return "No matching comments found."

    lines: list[str] = []
    for index, item in enumerate(results[:limit], start=1):
        snippet = clean_snippet(item["content"], 120)
        lines.append(
            f"{index}. #{item['channel_name']} | {item['author_name']} | score {item['score']} | {snippet}"
        )
    return "\n".join(lines)


def format_quotes(results: list[dict], limit: int = 5) -> str:
    if not results:
        return "No quotes available."

    lines: list[str] = []
    for index, item in enumerate(results[:limit], start=1):
        quote = clean_snippet(item["content"], 150)
        lines.append(f"{index}. \"{quote}\"")
        lines.append(f"   - {item['author_name']} in #{item['channel_name']}")
    return "\n".join(lines)


def summarize_appreciation(payload: dict) -> str:
    results = payload.get("results", [])
    if not results:
        return "No appreciation comments were found in the latest scan."

    unique_authors = len({item["author_id"] for item in results})
    top_channels = Counter(item["channel_name"] for item in results).most_common(3)
    top_work_refs = extract_reason_values(results, "work reference").most_common(3)
    top_gratitude = extract_reason_values(results, "gratitude").most_common(3)

    lines = [
        f"{len(results)} appreciation comments from {unique_authors} members.",
        "Top channels: "
        + (", ".join(f"#{name} ({count})" for name, count in top_channels) if top_channels else "none"),
        "Most praised work types: "
        + (", ".join(f"{name} ({count})" for name, count in top_work_refs) if top_work_refs else "none"),
        "Most common gratitude phrases: "
        + (", ".join(f"{name} ({count})" for name, count in top_gratitude) if top_gratitude else "none"),
        "Strongest comment:",
        format_top_results(results, limit=1),
    ]
    return "\n".join(lines)


def build_stats_text(payload: dict) -> str:
    results = payload.get("results", [])
    if not results:
        return "No appreciation stats available because the latest scan found no comments."

    top_channel, top_channel_count = Counter(item["channel_name"] for item in results).most_common(1)[0]
    average_score = sum(item["score"] for item in results) / len(results)
    unique_authors = len({item["author_id"] for item in results})
    return "\n".join(
        [
            f"Appreciation comments: {len(results)}",
            f"Scanned channels: {payload.get('scanned_channels', 0)}",
            f"Unique members: {unique_authors}",
            f"Average score: {average_score:.1f}",
            f"Top channel: #{top_channel} ({top_channel_count})",
            f"Skipped channels: {len(payload.get('skipped_channels', []))}",
        ]
    )


def build_channel_leaderboard(results: list[dict], limit: int = 10) -> str:
    counts = Counter(item["channel_name"] for item in results)
    if not counts:
        return "No appreciation comments available for a leaderboard."

    lines = []
    for index, (channel_name, count) in enumerate(counts.most_common(limit), start=1):
        lines.append(f"{index}. #{channel_name} - {count}")
    return "\n".join(lines)


def build_digest_text(results: list[dict], days: int) -> str:
    if not results:
        return f"No appreciation comments were found in the last {days} days."

    top_channels = Counter(item["channel_name"] for item in results).most_common(3)
    top_work_refs = extract_reason_values(results, "work reference").most_common(3)
    lines = [
        f"Weekly digest for the last {days} days",
        f"Total appreciation comments: {len(results)}",
        "Top channels: "
        + (", ".join(f"#{name} ({count})" for name, count in top_channels) if top_channels else "none"),
        "Top praised work: "
        + (", ".join(f"{name} ({count})" for name, count in top_work_refs) if top_work_refs else "none"),
        "Top comments:",
        format_top_results(results, limit=3),
    ]
    return "\n".join(lines)


def build_draft_post(results: list[dict]) -> str:
    if not results:
        return "I do not have any appreciation comments to turn into a draft post yet."

    quotes = results[:3]
    quote_lines = "\n".join(f"- \"{clean_snippet(item['content'], 140)}\"" for item in quotes)
    return "\n".join(
        [
            "Community appreciation draft",
            "",
            "Reading comments like these keeps me going. Thank you all for the support and for taking the time to share how the work is helping you.",
            "",
            quote_lines,
            "",
            "I appreciate every bit of support, and I’m excited to keep building more systems, tutorials, and tools for the community.",
        ]
    )


def latest_results_or_none(kind: str = "appreciation") -> tuple[dict, Path] | None:
    return load_latest_payload(kind)


def truncate_response(text: str, limit: int = 1800) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


async def ensure_guild(interaction: discord.Interaction) -> discord.Guild | None:
    if interaction.guild is None:
        await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
        return None
    return interaction.guild


async def run_appreciation_scan(
    interaction: discord.Interaction,
    channels: list[discord.TextChannel],
    *,
    limit_per_channel: int,
    after: datetime | None = None,
    kind: str = "appreciation",
    summary_label: str,
) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    results, skipped = await scan_text_channels(
        guild,
        channels,
        clamp_limit(limit_per_channel),
        message_is_feedback,
        after=after,
    )

    path = export_path(guild, kind)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "scanned_channels": len(channels),
        "limit_per_channel": clamp_limit(limit_per_channel),
        "appreciation_count": len(results),
        "skipped_channels": skipped,
        "results": results,
    }
    write_json(path, payload)

    await interaction.followup.send(
        truncate_response(
            f"Found {len(results)} likely appreciation comments across {summary_label}. "
            f"Saved results to `{path}`."
        ),
        ephemeral=True,
    )


@app_commands.command(
    name="scan_feedback",
    description="Scan readable text channels and export appreciation comments about your work.",
)
@app_commands.describe(limit_per_channel="Maximum number of recent messages to scan per text channel.")
async def scan_feedback(interaction: discord.Interaction, limit_per_channel: int = MAX_MESSAGES_PER_CHANNEL) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return
    await run_appreciation_scan(
        interaction,
        guild.text_channels,
        limit_per_channel=limit_per_channel,
        summary_label=f"{len(guild.text_channels)} text channels",
    )


@app_commands.command(
    name="scan_thanks",
    description="Scan all readable text channels for thank-you and praise comments about your work.",
)
@app_commands.describe(limit_per_channel="Maximum number of recent messages to scan per text channel.")
async def scan_thanks(interaction: discord.Interaction, limit_per_channel: int = MAX_MESSAGES_PER_CHANNEL) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return
    await run_appreciation_scan(
        interaction,
        guild.text_channels,
        limit_per_channel=limit_per_channel,
        summary_label=f"{len(guild.text_channels)} text channels",
    )


@app_commands.command(
    name="scan_channel",
    description="Scan one text channel and export appreciation comments about your work.",
)
@app_commands.describe(
    channel="The text channel to scan.",
    limit="Maximum number of recent messages to scan.",
)
async def scan_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    limit: int = MAX_MESSAGES_PER_CHANNEL,
) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    await run_appreciation_scan(
        interaction,
        [channel],
        limit_per_channel=limit,
        summary_label=f"#{channel.name}",
        kind="appreciation",
    )


@app_commands.command(
    name="summary_thanks",
    description="Summarize the latest appreciation scan into quick themes and highlights.",
)
async def summary_thanks(interaction: discord.Interaction) -> None:
    latest = latest_results_or_none("appreciation")
    if latest is None:
        await interaction.response.send_message(
            "No appreciation scan found yet. Run `/scan_feedback` first.",
            ephemeral=True,
        )
        return

    payload, path = latest
    summary = summarize_appreciation(payload)
    await interaction.response.send_message(
        truncate_response(f"{summary}\n\nSource: `{path}`"),
        ephemeral=True,
    )


@app_commands.command(
    name="top_comments",
    description="Show the strongest appreciation comments from the latest scan.",
)
@app_commands.describe(limit="How many comments to show.")
async def top_comments(interaction: discord.Interaction, limit: int = 5) -> None:
    latest = latest_results_or_none("appreciation")
    if latest is None:
        await interaction.response.send_message(
            "No appreciation scan found yet. Run `/scan_feedback` first.",
            ephemeral=True,
        )
        return

    payload, _ = latest
    message = format_top_results(payload.get("results", []), limit=max(1, min(limit, 10)))
    await interaction.response.send_message(truncate_response(message), ephemeral=True)


@app_commands.command(
    name="search_praise",
    description="Search the latest appreciation scan for a keyword like tutorial or system.",
)
@app_commands.describe(keyword="Word or phrase to search for in appreciation comments.")
async def search_praise(interaction: discord.Interaction, keyword: str) -> None:
    latest = latest_results_or_none("appreciation")
    if latest is None:
        await interaction.response.send_message(
            "No appreciation scan found yet. Run `/scan_feedback` first.",
            ephemeral=True,
        )
        return

    payload, _ = latest
    lowered = keyword.lower()
    filtered = [item for item in payload.get("results", []) if lowered in item["content"].lower()]
    message = format_top_results(filtered, limit=10)
    await interaction.response.send_message(
        truncate_response(f"Matches for `{keyword}`:\n{message}"),
        ephemeral=True,
    )


@app_commands.command(
    name="export_csv",
    description="Convert the latest appreciation scan into a CSV export.",
)
async def export_csv_command(interaction: discord.Interaction) -> None:
    latest = latest_results_or_none("appreciation")
    if latest is None:
        await interaction.response.send_message(
            "No appreciation scan found yet. Run `/scan_feedback` first.",
            ephemeral=True,
        )
        return

    payload, path = latest
    csv_path = path.with_suffix(".csv")
    write_csv(csv_path, payload.get("results", []))
    await interaction.response.send_message(
        f"Exported the latest appreciation scan to `{csv_path}`.",
        ephemeral=True,
    )


@app_commands.command(
    name="stats_thanks",
    description="Show quick stats from the latest appreciation scan.",
)
async def stats_thanks(interaction: discord.Interaction) -> None:
    latest = latest_results_or_none("appreciation")
    if latest is None:
        await interaction.response.send_message(
            "No appreciation scan found yet. Run `/scan_feedback` first.",
            ephemeral=True,
        )
        return

    payload, _ = latest
    await interaction.response.send_message(
        truncate_response(build_stats_text(payload)),
        ephemeral=True,
    )


@app_commands.command(
    name="recent_thanks",
    description="Scan recent channels activity for appreciation comments from the last N days.",
)
@app_commands.describe(
    days="How many days back to scan.",
    limit_per_channel="Maximum number of recent messages to scan per text channel.",
)
async def recent_thanks(
    interaction: discord.Interaction,
    days: int = 7,
    limit_per_channel: int = MAX_MESSAGES_PER_CHANNEL,
) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    bounded_days = max(1, min(days, 365))
    after = datetime.now(timezone.utc) - timedelta(days=bounded_days)
    await run_appreciation_scan(
        interaction,
        guild.text_channels,
        limit_per_channel=limit_per_channel,
        after=after,
        kind="recent-appreciation",
        summary_label=f"{len(guild.text_channels)} text channels from the last {bounded_days} days",
    )


@app_commands.command(
    name="user_love",
    description="Show appreciation comments from one specific member in the latest scan.",
)
@app_commands.describe(user="The member whose appreciation comments you want to review.")
async def user_love(interaction: discord.Interaction, user: discord.Member) -> None:
    latest = latest_results_or_none("appreciation")
    if latest is None:
        await interaction.response.send_message(
            "No appreciation scan found yet. Run `/scan_feedback` first.",
            ephemeral=True,
        )
        return

    payload, _ = latest
    filtered = [item for item in payload.get("results", []) if item["author_id"] == user.id]
    message = format_top_results(filtered, limit=10)
    await interaction.response.send_message(
        truncate_response(f"Appreciation comments from {user.display_name}:\n{message}"),
        ephemeral=True,
    )


@app_commands.command(
    name="channel_leaderboard",
    description="Rank channels by how many appreciation comments they contain.",
)
@app_commands.describe(limit="How many channels to show.")
async def channel_leaderboard(interaction: discord.Interaction, limit: int = 10) -> None:
    latest = latest_results_or_none("appreciation")
    if latest is None:
        await interaction.response.send_message(
            "No appreciation scan found yet. Run `/scan_feedback` first.",
            ephemeral=True,
        )
        return

    payload, _ = latest
    leaderboard = build_channel_leaderboard(payload.get("results", []), limit=max(1, min(limit, 20)))
    await interaction.response.send_message(truncate_response(leaderboard), ephemeral=True)


@app_commands.command(
    name="quote_testimonials",
    description="Show the best quotes you could reuse as testimonials.",
)
@app_commands.describe(limit="How many quotes to show.")
async def quote_testimonials(interaction: discord.Interaction, limit: int = 5) -> None:
    testimonials = load_testimonials()
    source = "saved testimonials"
    if testimonials:
        results = sorted(testimonials, key=lambda item: item.get("score", 0), reverse=True)
    else:
        latest = latest_results_or_none("appreciation")
        if latest is None:
            await interaction.response.send_message(
                "No testimonials or appreciation scan found yet. Run `/scan_feedback` first.",
                ephemeral=True,
            )
            return
        payload, _ = latest
        results = payload.get("results", [])
        source = "latest appreciation scan"

    quotes = format_quotes(results, limit=max(1, min(limit, 10)))
    await interaction.response.send_message(
        truncate_response(f"Quotes from {source}:\n{quotes}"),
        ephemeral=True,
    )


@app_commands.command(
    name="save_testimonial",
    description="Save a specific Discord message link into your testimonials file.",
)
@app_commands.describe(message_link="Paste the Discord message link you want to save.")
async def save_testimonial(interaction: discord.Interaction, message_link: str) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    match = MESSAGE_LINK_RE.fullmatch(message_link.strip())
    if not match:
        await interaction.response.send_message(
            "That does not look like a valid Discord message link.",
            ephemeral=True,
        )
        return

    guild_id, channel_id, message_id = (int(value) for value in match.groups())
    if guild_id != guild.id:
        await interaction.response.send_message(
            "Save testimonials from the current server only.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(thinking=True)
    try:
        channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.followup.send("That message is not in a text channel or thread.", ephemeral=True)
            return
        message = await channel.fetch_message(message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        await interaction.followup.send("I could not fetch that message.", ephemeral=True)
        return

    detected = appreciation_from_text(message.content or "")
    entry = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "channel_id": channel.id,
        "channel_name": channel.name,
        "message_id": message.id,
        "author_id": message.author.id,
        "author_name": str(message.author),
        "created_at": message.created_at.isoformat(),
        "jump_url": message.jump_url,
        "content": message.content,
        "score": detected.score if detected else 0,
        "reasons": detected.reasons if detected else [],
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "manual_save": True,
    }

    testimonials = load_testimonials()
    if any(item["message_id"] == message.id for item in testimonials):
        await interaction.followup.send("That testimonial is already saved.", ephemeral=True)
        return

    testimonials.append(entry)
    save_testimonials(testimonials)

    await interaction.followup.send(
        f"Saved that message to `{TESTIMONIALS_PATH}`.",
        ephemeral=True,
    )


@app_commands.command(
    name="draft_post",
    description="Draft a short appreciation post from your saved testimonials or latest scan.",
)
async def draft_post(interaction: discord.Interaction) -> None:
    testimonials = load_testimonials()
    if testimonials:
        results = sorted(testimonials, key=lambda item: item.get("score", 0), reverse=True)
    else:
        latest = latest_results_or_none("appreciation")
        if latest is None:
            await interaction.response.send_message(
                "No testimonials or appreciation scan found yet. Run `/scan_feedback` first.",
                ephemeral=True,
            )
            return
        payload, _ = latest
        results = payload.get("results", [])

    draft = build_draft_post(results)
    await interaction.response.send_message(truncate_response(draft), ephemeral=True)


@app_commands.command(
    name="create_project_post",
    description="Create a new forum post in your projects locodev channel.",
)
@app_commands.describe(
    title="The forum post title.",
    content="The body content for the new project post.",
    image="Optional image to include in the project post.",
)
async def create_project_post(
    interaction: discord.Interaction,
    title: str,
    content: str,
    image: discord.Attachment | None = None,
) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    forum = find_projects_forum_channel(guild)
    if forum is None:
        await interaction.response.send_message(
            "I could not find a forum channel for `projects locodev`. Set `PROJECTS_FORUM_CHANNEL_ID` in `.env` or rename the forum channel to something like `projects-locodev`.",
            ephemeral=True,
        )
        return

    me = guild.me
    permissions = forum.permissions_for(me) if me else None
    if not permissions or not permissions.view_channel or not permissions.send_messages:
        await interaction.response.send_message(
            f"I do not have permission to create posts in #{forum.name}.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(thinking=True)
    try:
        create_kwargs = {
            "name": title.strip(),
            "content": content.strip(),
            "reason": "Created via /create_project_post",
        }
        if image is not None:
            if image.content_type and not image.content_type.startswith("image/"):
                await interaction.followup.send(
                    "The uploaded file is not recognized as an image.",
                    ephemeral=True,
                )
                return
            create_kwargs["file"] = await image.to_file()

        thread_with_message = await forum.create_thread(**create_kwargs)
    except discord.HTTPException:
        await interaction.followup.send(
            "Discord rejected the post creation request. Check forum permissions and post requirements.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        truncate_response(
            f"Created a new post in #{forum.name}: {thread_with_message.thread.jump_url}"
        ),
        ephemeral=True,
    )


@app_commands.command(
    name="edit_project_post",
    description="Edit an existing project forum post title, body, or image.",
)
@app_commands.describe(
    post_link="Paste the Discord link for the project post thread or starter message.",
    title="Optional new title for the post.",
    content="Optional new body content for the post.",
    image="Optional new image to replace the current image with.",
    remove_image="Set true to remove existing images from the starter post.",
)
async def edit_project_post(
    interaction: discord.Interaction,
    post_link: str,
    title: str | None = None,
    content: str | None = None,
    image: discord.Attachment | None = None,
    remove_image: bool = False,
) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    if title is None and content is None and image is None and not remove_image:
        await interaction.response.send_message(
            "Provide at least one change: title, content, image, or remove_image.",
            ephemeral=True,
        )
        return

    thread, starter_message = await resolve_project_post(guild, post_link)
    if thread is None or starter_message is None:
        await interaction.response.send_message(
            "I could not resolve that project post link. Use a link to the forum post thread or its starter message.",
            ephemeral=True,
        )
        return

    me = guild.me
    permissions = thread.permissions_for(me) if me else None
    if not permissions or not permissions.view_channel or not permissions.send_messages:
        await interaction.response.send_message(
            f"I do not have permission to edit posts in #{thread.parent.name}.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(thinking=True)

    try:
        if title is not None and title.strip():
            await thread.edit(name=title.strip(), reason="Edited via /edit_project_post")

        attachments: list[discord.Attachment | discord.File] = list(starter_message.attachments)
        if remove_image:
            attachments = [
                attachment
                for attachment in attachments
                if not (attachment.content_type and attachment.content_type.startswith("image/"))
            ]

        if image is not None:
            if image.content_type and not image.content_type.startswith("image/"):
                await interaction.followup.send(
                    "The uploaded file is not recognized as an image.",
                    ephemeral=True,
                )
                return

            attachments = [
                attachment
                for attachment in attachments
                if not (attachment.content_type and attachment.content_type.startswith("image/"))
            ]
            attachments.append(await image.to_file())

        message_kwargs = {}
        if content is not None:
            message_kwargs["content"] = content.strip()
        if image is not None or remove_image:
            message_kwargs["attachments"] = attachments

        if message_kwargs:
            await starter_message.edit(**message_kwargs)
    except discord.HTTPException:
        await interaction.followup.send(
            "Discord rejected the edit request. Check permissions and make sure the post still exists.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        truncate_response(f"Updated project post: {thread.jump_url}"),
        ephemeral=True,
    )


@app_commands.command(
    name="digest_weekly",
    description="Scan the last 7 days and generate a weekly appreciation digest.",
)
@app_commands.describe(
    days="How many days back to scan.",
    limit_per_channel="Maximum number of recent messages to scan per text channel.",
)
async def digest_weekly(
    interaction: discord.Interaction,
    days: int = 7,
    limit_per_channel: int = MAX_MESSAGES_PER_CHANNEL,
) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    bounded_days = max(1, min(days, 365))
    await interaction.response.defer(thinking=True)
    after = datetime.now(timezone.utc) - timedelta(days=bounded_days)
    results, skipped = await scan_text_channels(
        guild,
        guild.text_channels,
        clamp_limit(limit_per_channel),
        message_is_feedback,
        after=after,
    )
    path = export_path(guild, "weekly-digest")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "scanned_channels": len(guild.text_channels),
        "limit_per_channel": clamp_limit(limit_per_channel),
        "days": bounded_days,
        "skipped_channels": skipped,
        "results": results,
        "digest": build_digest_text(results, bounded_days),
    }
    write_json(path, payload)
    await interaction.followup.send(
        truncate_response(f"{payload['digest']}\n\nSaved digest to `{path}`."),
        ephemeral=True,
    )


@app_commands.command(
    name="scan_bug_praise_split",
    description="Scan channels and split appreciation comments from bugs and requests.",
)
@app_commands.describe(limit_per_channel="Maximum number of recent messages to scan per text channel.")
async def scan_bug_praise_split(
    interaction: discord.Interaction,
    limit_per_channel: int = MAX_MESSAGES_PER_CHANNEL,
) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    await interaction.response.defer(thinking=True)
    praise, issues, skipped = await scan_bug_praise_channels(
        guild,
        guild.text_channels,
        clamp_limit(limit_per_channel),
    )
    path = export_path(guild, "bug-praise-split")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "scanned_channels": len(guild.text_channels),
        "limit_per_channel": clamp_limit(limit_per_channel),
        "appreciation_count": len(praise),
        "issue_count": len(issues),
        "skipped_channels": skipped,
        "appreciation": praise,
        "issues": issues,
    }
    write_json(path, payload)
    await interaction.followup.send(
        truncate_response(
            f"Found {len(praise)} appreciation comments and {len(issues)} issue/request comments. "
            f"Saved split results to `{path}`."
        ),
        ephemeral=True,
    )


@app_commands.command(
    name="scan_creator_mentions",
    description="Scan channels for comments that mention your creator aliases directly.",
)
@app_commands.describe(limit_per_channel="Maximum number of recent messages to scan per text channel.")
async def scan_creator_mentions(
    interaction: discord.Interaction,
    limit_per_channel: int = MAX_MESSAGES_PER_CHANNEL,
) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    await interaction.response.defer(thinking=True)
    results, skipped = await scan_text_channels(
        guild,
        guild.text_channels,
        clamp_limit(limit_per_channel),
        lambda message: creator_mention_from_text(message.content or ""),
    )
    path = export_path(guild, "creator-mentions")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "scanned_channels": len(guild.text_channels),
        "limit_per_channel": clamp_limit(limit_per_channel),
        "mention_count": len(results),
        "skipped_channels": skipped,
        "results": results,
    }
    write_json(path, payload)
    await interaction.followup.send(
        truncate_response(f"Found {len(results)} direct creator mentions. Saved results to `{path}`."),
        ephemeral=True,
    )


@app_commands.command(
    name="sentiment_report",
    description="Build a positive, neutral, and negative sentiment report about your work.",
)
@app_commands.describe(
    days="How many days back to scan.",
    limit_per_channel="Maximum number of recent messages to scan per text channel.",
)
async def sentiment_report(
    interaction: discord.Interaction,
    days: int = 30,
    limit_per_channel: int = MAX_MESSAGES_PER_CHANNEL,
) -> None:
    guild = await ensure_guild(interaction)
    if guild is None:
        return

    bounded_days = max(1, min(days, 365))
    await interaction.response.defer(thinking=True)
    after = datetime.now(timezone.utc) - timedelta(days=bounded_days)
    results, skipped = await scan_text_channels(
        guild,
        guild.text_channels,
        clamp_limit(limit_per_channel),
        lambda message: sentiment_from_text(message.content or ""),
        after=after,
    )
    sentiment_counts = Counter(item.get("sentiment", "unknown") for item in results)
    path = export_path(guild, "sentiment-report")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "scanned_channels": len(guild.text_channels),
        "limit_per_channel": clamp_limit(limit_per_channel),
        "days": bounded_days,
        "sentiment_counts": dict(sentiment_counts),
        "skipped_channels": skipped,
        "results": results,
    }
    write_json(path, payload)
    report_lines = [
        f"Positive: {sentiment_counts.get('positive', 0)}",
        f"Neutral: {sentiment_counts.get('neutral', 0)}",
        f"Negative: {sentiment_counts.get('negative', 0)}",
        f"Saved report to `{path}`.",
    ]
    await interaction.followup.send(truncate_response("\n".join(report_lines)), ephemeral=True)



DUB_API_KEY = os.getenv("DUB_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
PATREON_ACCESS_TOKEN = os.getenv("PATREON_ACCESS_TOKEN", "")
_REPORT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def _http_get_report(url: str, headers: dict | None = None) -> dict:
    from urllib import request as _req, error as _err
    req = _req.Request(url, headers={**(headers or {}), "User-Agent": _REPORT_USER_AGENT})
    with _req.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _build_dub_embed() -> discord.Embed:
    from urllib import parse as _parse
    try:
        from zoneinfo import ZoneInfo
        _tz = ZoneInfo("America/Sao_Paulo")
    except Exception:
        _tz = timezone(timedelta(hours=-3))
    now = datetime.now(_tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = now.isoformat()
    query = _parse.urlencode({
        "event": "clicks", "groupBy": "top_links",
        "start": start, "end": end,
        "timezone": "America/Sao_Paulo", "limit": "5",
    })
    data = _http_get_report(
        f"https://api.dub.co/analytics?{query}",
        {"Authorization": f"Bearer {DUB_API_KEY}", "Accept": "application/json"},
    )
    if not data:
        return discord.Embed(title="Dub Click Report", description="No clicks today.", color=0xF97316)
    lines = []
    for i, entry in enumerate(data[:5], 1):
        label = entry.get("label") or entry.get("key") or f"Link {i}"
        clicks = int(entry.get("clicks") or 0)
        lines.append(f"{i}. **{label}** — {clicks} click{'s' if clicks != 1 else ''}")
    total = sum(int(e.get("clicks") or 0) for e in data[:5])
    today_str = now.strftime("%b %d, %Y")
    embed = discord.Embed(
        title="Dub Click Report",
        description=f"Top 5 clicked links today ({today_str})\n\n" + "\n".join(lines),
        color=0xF97316,
    )
    embed.add_field(name="Total Clicks", value=str(total), inline=True)
    embed.set_footer(text="Data from Dub.co API")
    return embed


def _build_ue5_embed() -> discord.Embed:
    from urllib import parse as _parse
    now = datetime.now(timezone.utc)
    published_after = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = _parse.urlencode({
        "part": "snippet", "q": "unreal engine 5 OR UE5",
        "type": "video", "publishedAfter": published_after,
        "maxResults": "50", "key": YOUTUBE_API_KEY,
    })
    search_data = _http_get_report(f"https://www.googleapis.com/youtube/v3/search?{query}")
    videos = search_data.get("items", [])
    if not videos:
        return discord.Embed(title="Top 5 UE5 YouTube Channels", description="No UE5 videos found this week.", color=0x9B59B6)
    video_ids = [v["id"]["videoId"] for v in videos if v.get("id", {}).get("videoId")]
    stats_query = _parse.urlencode({"part": "statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY})
    stats_data = _http_get_report(f"https://www.googleapis.com/youtube/v3/videos?{stats_query}")
    stats = {item["id"]: item.get("statistics", {}) for item in stats_data.get("items", [])}
    channels: dict = {}
    for video in videos:
        snippet = video.get("snippet", {})
        channel_id = snippet.get("channelId", "")
        channel_title = snippet.get("channelTitle", "Unknown")
        video_id = video.get("id", {}).get("videoId", "")
        views = int(stats.get(video_id, {}).get("viewCount", 0))
        if channel_id not in channels:
            channels[channel_id] = {"title": channel_title, "views": 0, "videos": 0}
        channels[channel_id]["views"] += views
        channels[channel_id]["videos"] += 1
    top = sorted(channels.values(), key=lambda c: c["views"], reverse=True)[:5]
    lines = []
    for i, ch in enumerate(top, 1):
        v = ch["views"]
        vs = f"{v/1_000_000:.1f}M" if v >= 1_000_000 else f"{v/1_000:.1f}K" if v >= 1_000 else str(v)
        n = ch["videos"]
        lines.append(f"{i}. **{ch['title']}** — {vs} views ({n} video{'s' if n != 1 else ''})")
    embed = discord.Embed(
        title="Top 5 UE5 YouTube Channels",
        description="Most viewed channels about UE5 in the last 7 days\n\n" + "\n".join(lines),
        color=0x9B59B6,
    )
    embed.set_footer(text="Data from YouTube Data API v3")
    return embed


@app_commands.command(name="report", description="Send a Dub or UE5 YouTube report instantly.")
@app_commands.describe(type="Which report to send.")
@app_commands.choices(type=[
    app_commands.Choice(name="Dub Click Report (last 24h)", value="dub"),
    app_commands.Choice(name="UE5 YouTube Top Channels", value="ue5"),
])
async def report_command_slash(
    interaction: discord.Interaction,
    type: app_commands.Choice[str],
) -> None:
    await interaction.response.defer(thinking=True)
    try:
        loop = asyncio.get_event_loop()
        if type.value == "dub":
            if not DUB_API_KEY:
                await interaction.followup.send("DUB_API_KEY is not configured.")
                return
            embed = await loop.run_in_executor(None, _build_dub_embed)
        else:
            if not YOUTUBE_API_KEY:
                await interaction.followup.send("YOUTUBE_API_KEY is not configured.")
                return
            embed = await loop.run_in_executor(None, _build_ue5_embed)
        await interaction.followup.send(embed=embed)
    except Exception as exc:
        await interaction.followup.send(f"Error generating report: {exc}")


def _fetch_patreon_member_by_discord_id(discord_user_id: str) -> dict | None:
    from urllib import request as _req, parse as _parse
    # Get campaign ID
    req = _req.Request(
        "https://www.patreon.com/api/oauth2/v2/campaigns",
        headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
    )
    with _req.urlopen(req, timeout=30) as resp:
        campaigns = json.load(resp)
    campaign_id = campaigns["data"][0]["id"]

    # Paginate through members
    cursor = None
    while True:
        params: dict = {
            "include": "user,currently_entitled_tiers",
            "fields[member]": "patron_status,currently_entitled_amount_cents,full_name,last_charge_status",
            "fields[user]": "social_connections,full_name",
            "fields[tier]": "title",
            "page[count]": "1000",
        }
        if cursor:
            params["page[cursor]"] = cursor
        req = _req.Request(
            f"https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members?{_parse.urlencode(params)}",
            headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
        )
        with _req.urlopen(req, timeout=30) as resp:
            data = json.load(resp)

        # Map patreon user id -> discord user id and tier
        user_discord_map: dict = {}
        tier_map: dict = {}
        for inc in data.get("included", []):
            if inc.get("type") == "user":
                social = inc.get("attributes", {}).get("social_connections") or {}
                disc = social.get("discord") or {}
                uid = disc.get("user_id")
                if uid:
                    user_discord_map[inc["id"]] = uid
            if inc.get("type") == "tier":
                tier_map[inc["id"]] = inc.get("attributes", {}).get("title", "Unknown")

        for member in data.get("data", []):
            patreon_uid = member.get("relationships", {}).get("user", {}).get("data", {}).get("id")
            if user_discord_map.get(patreon_uid) == discord_user_id:
                tiers = [
                    tier_map.get(t["id"], "Unknown")
                    for t in member.get("relationships", {}).get("currently_entitled_tiers", {}).get("data", [])
                ]
                return {
                    "full_name": member["attributes"].get("full_name", "Unknown"),
                    "patron_status": member["attributes"].get("patron_status"),
                    "amount_cents": member["attributes"].get("currently_entitled_amount_cents") or 0,
                    "last_charge_status": member["attributes"].get("last_charge_status"),
                    "tiers": tiers,
                }

        next_cursor = data.get("meta", {}).get("pagination", {}).get("cursors", {}).get("next")
        if not next_cursor:
            break
        cursor = next_cursor
    return None


@app_commands.command(name="check_patron", description="Check if a Discord user has an active Patreon subscription.")
@app_commands.describe(user="The Discord user to check.")
async def check_patron_slash(interaction: discord.Interaction, user: discord.Member) -> None:
    # Restrict to LocoDev role only
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    if not PATREON_ACCESS_TOKEN:
        await interaction.followup.send("PATREON_ACCESS_TOKEN is not configured.", ephemeral=True)
        return
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch_patreon_member_by_discord_id, str(user.id))
        if result is None:
            await interaction.followup.send(
                f"**{user.display_name}** was not found on Patreon or hasn't linked their Discord account.",
                ephemeral=True,
            )
            return
        status = result["patron_status"] or "unknown"
        amount = result["amount_cents"] / 100
        tiers = ", ".join(result["tiers"]) if result["tiers"] else "None"
        charge = result["last_charge_status"] or "N/A"
        embed = discord.Embed(title=f"Patreon — {result['full_name']}", color=0xF96854)
        embed.add_field(name="Status", value=status.replace("_", " ").title(), inline=True)
        embed.add_field(name="Tier(s)", value=tiers, inline=True)
        embed.add_field(name="Amount", value=f"${amount:.2f}/month", inline=True)
        embed.add_field(name="Last Charge", value=charge, inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as exc:
        await interaction.followup.send(f"Error checking Patreon: {exc}", ephemeral=True)


async def _send_chunked(channel, lines: list[str]) -> None:
    """Send lines as Discord messages, splitting at 1900 chars."""
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 1900:
            await channel.send(chunk)
            chunk = line
        else:
            chunk = (chunk + "\n" + line).strip()
    if chunk:
        await channel.send(chunk)


def _fetch_patreon_daily_activity() -> dict:
    """Fetch members who joined or have declined status in last 24h from Patreon API."""
    from urllib import request as _req, parse as _parse
    from datetime import timezone
    req = _req.Request(
        "https://www.patreon.com/api/oauth2/v2/campaigns",
        headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
    )
    with _req.urlopen(req, timeout=30) as resp:
        campaigns = json.load(resp)
    campaign_id = campaigns["data"][0]["id"]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    joined = []
    declined = []
    cursor = None

    while True:
        params: dict = {
            "include": "currently_entitled_tiers",
            "fields[member]": "patron_status,full_name,currently_entitled_amount_cents,lifetime_support_cents,pledge_relationship_start",
            "fields[tier]": "title",
            "page[count]": "1000",
        }
        if cursor:
            params["page[cursor]"] = cursor
        req = _req.Request(
            f"https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members?{_parse.urlencode(params)}",
            headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
        )
        with _req.urlopen(req, timeout=30) as resp:
            data = json.load(resp)

        tier_map = {
            inc["id"]: inc.get("attributes", {}).get("title", "Unknown")
            for inc in data.get("included", [])
            if inc.get("type") == "tier"
        }

        for member in data.get("data", []):
            attrs = member.get("attributes", {})
            status = attrs.get("patron_status")
            name = attrs.get("full_name", "Unknown")
            amount_cents = attrs.get("currently_entitled_amount_cents") or 0
            tiers = [
                tier_map.get(t["id"], "Unknown")
                for t in member.get("relationships", {}).get("currently_entitled_tiers", {}).get("data", [])
            ]
            tier_str = ", ".join(tiers) if tiers else None
            # Correct tier by amount
            def _correct(t, c):
                if c <= 700: return "LocoBasic"
                elif c <= 1500: return "LocoStandard"
                else: return "LocoPremium"
            if amount_cents > 0:
                tier_str = _correct(tier_str, amount_cents)

            start_str = attrs.get("pledge_relationship_start")
            if start_str:
                try:
                    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    if start_dt >= cutoff and status == "active_patron":
                        joined.append({"name": name, "tier": tier_str, "amount": amount_cents / 100})
                except Exception:
                    pass

            if status == "declined_patron":
                declined.append({"name": name, "tier": tier_str, "amount": amount_cents / 100})

        next_cursor = data.get("meta", {}).get("pagination", {}).get("cursors", {}).get("next")
        if not next_cursor:
            break
        cursor = next_cursor

    return {"joined": joined, "declined": declined}


def _fetch_top_patrons(limit: int = 10) -> list[dict]:
    from urllib import request as _req, parse as _parse
    req = _req.Request(
        "https://www.patreon.com/api/oauth2/v2/campaigns",
        headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
    )
    with _req.urlopen(req, timeout=30) as resp:
        campaigns = json.load(resp)
    campaign_id = campaigns["data"][0]["id"]

    members = []
    cursor = None
    while True:
        params: dict = {
            "include": "currently_entitled_tiers",
            "fields[member]": "patron_status,currently_entitled_amount_cents,full_name,lifetime_support_cents",
            "fields[tier]": "title",
            "page[count]": "1000",
        }
        if cursor:
            params["page[cursor]"] = cursor
        req = _req.Request(
            f"https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members?{_parse.urlencode(params)}",
            headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
        )
        with _req.urlopen(req, timeout=30) as resp:
            data = json.load(resp)

        tier_map = {
            inc["id"]: inc.get("attributes", {}).get("title", "Unknown")
            for inc in data.get("included", [])
            if inc.get("type") == "tier"
        }

        for member in data.get("data", []):
            attrs = member.get("attributes", {})
            if attrs.get("patron_status") != "active_patron":
                continue
            tiers = [
                tier_map.get(t["id"], "Unknown")
                for t in member.get("relationships", {}).get("currently_entitled_tiers", {}).get("data", [])
            ]
            members.append({
                "full_name": attrs.get("full_name", "Unknown"),
                "amount_cents": attrs.get("currently_entitled_amount_cents") or 0,
                "lifetime_cents": attrs.get("lifetime_support_cents") or 0,
                "tiers": ", ".join(tiers) if tiers else "None",
            })

        next_cursor = data.get("meta", {}).get("pagination", {}).get("cursors", {}).get("next")
        if not next_cursor:
            break
        cursor = next_cursor

    members.sort(key=lambda m: m["lifetime_cents"], reverse=True)
    return members[:limit]


@app_commands.command(name="top_patrons", description="Show top Patreon members by pledge amount.")
async def top_patrons_slash(interaction: discord.Interaction) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    if not PATREON_ACCESS_TOKEN:
        await interaction.followup.send("PATREON_ACCESS_TOKEN is not configured.", ephemeral=True)
        return
    try:
        loop = asyncio.get_event_loop()
        patrons = await loop.run_in_executor(None, _fetch_top_patrons)
        if not patrons:
            await interaction.followup.send("No active patrons found.", ephemeral=True)
            return
        lines = [
            f"{i}. **{p['full_name']}** — ${p['amount_cents']/100:.2f}/month | {p['tiers']} | lifetime: ${p['lifetime_cents']/100:.2f}"
            for i, p in enumerate(patrons, 1)
        ]
        embed = discord.Embed(
            title="Top Patrons by Pledge Amount",
            description="\n".join(lines),
            color=0xF96854,
        )
        embed.set_footer(text="Active patrons only • Data from Patreon API")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as exc:
        await interaction.followup.send(f"Error fetching patrons: {exc}", ephemeral=True)


def _fetch_recent_posts(tier_name: str = "LocoStandard", limit: int = 5) -> list[dict]:
    from urllib import request as _req, parse as _parse
    req = _req.Request(
        "https://www.patreon.com/api/oauth2/v2/campaigns",
        headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
    )
    with _req.urlopen(req, timeout=30) as resp:
        campaigns = json.load(resp)
    campaign_id = campaigns["data"][0]["id"]

    posts = []
    cursor = None
    while True:
        params: dict = {
            "fields[post]": "title,url,published_at",
            "page[count]": "500",
        }
        if cursor:
            params["page[cursor]"] = cursor
        req = _req.Request(
            f"https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/posts?{_parse.urlencode(params)}",
            headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
        )
        with _req.urlopen(req, timeout=30) as resp:
            data = json.load(resp)

        for post in data.get("data", []):
            attrs = post.get("attributes", {})
            title = attrs.get("title") or "Untitled"
            url = attrs.get("url", "")
            if url and not url.startswith("http"):
                url = f"https://www.patreon.com{url}"
            published_at = (attrs.get("published_at") or "")[:10]
            if published_at:
                posts.append({"title": title, "url": url, "published_at": published_at})

        next_cursor = data.get("meta", {}).get("pagination", {}).get("cursors", {}).get("next")
        if not next_cursor:
            break
        cursor = next_cursor

    posts.sort(key=lambda p: p["published_at"], reverse=True)
    return posts[:limit]


@app_commands.command(name="recent_posts", description="Show the 5 most recent LocoStandard Patreon posts.")
async def recent_posts_slash(interaction: discord.Interaction) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    if not PATREON_ACCESS_TOKEN:
        await interaction.followup.send("PATREON_ACCESS_TOKEN is not configured.", ephemeral=True)
        return
    try:
        loop = asyncio.get_event_loop()
        posts = await loop.run_in_executor(None, _fetch_recent_posts)
        if not posts:
            await interaction.followup.send("No posts found.", ephemeral=True)
            return
        lines = [
            f"{i}. **{p['title']}** ({p['published_at']})\n> {p['url']}"
            for i, p in enumerate(posts, 1)
        ]
        embed = discord.Embed(
            title="5 Most Recent Patreon Posts",
            description="\n\n".join(lines),
            color=0xF96854,
        )
        embed.set_footer(text="Data from Patreon API")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as exc:
        await interaction.followup.send(f"Error fetching posts: {exc}", ephemeral=True)


META_PIXEL_ID = os.getenv("META_PIXEL_ID", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")


def _send_meta_conversion(name: str, phone: str, email: str, value: float) -> str:
    import hmac, hashlib, time
    from urllib import request as _req, parse as _parse

    def _hash(val: str) -> str:
        return hashlib.sha256(val.strip().lower().encode()).hexdigest()

    payload = json.dumps({
        "data": [{
            "event_name": "Purchase",
            "event_time": int(time.time()),
            "action_source": "other",
            "user_data": {
                "em": [_hash(email)] if email else [],
                "ph": [_hash(phone.replace("+", "").replace(" ", ""))] if phone else [],
                "fn": [_hash(name.split()[0])] if name else [],
                "ln": [_hash(name.split()[-1])] if name and len(name.split()) > 1 else [],
            },
            "custom_data": {
                "value": value,
                "currency": "BRL",
            },
        }]
    }).encode()

    url = f"https://graph.facebook.com/v21.0/{META_PIXEL_ID}/events?access_token={META_ACCESS_TOKEN}"
    from urllib.error import HTTPError
    req = _req.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _req.urlopen(req, timeout=30) as resp:
            result = json.load(resp)
        return str(result.get("events_received", 0))
    except HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"Meta API error {e.code}: {error_body}")


@app_commands.command(name="meta_conversion", description="Send a purchase conversion event to Meta Ads.")
@app_commands.describe(
    name="Full name of the customer",
    phone="Phone number (e.g. +5511999999999)",
    email="Email address",
    value="Purchase value in BRL (default 50)",
)
async def meta_conversion_slash(
    interaction: discord.Interaction,
    name: str,
    phone: str,
    email: str,
    value: float = 50.0,
) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    if not META_PIXEL_ID or not META_ACCESS_TOKEN:
        await interaction.followup.send("META_PIXEL_ID or META_ACCESS_TOKEN is not configured.", ephemeral=True)
        return
    try:
        loop = asyncio.get_event_loop()
        received = await loop.run_in_executor(None, _send_meta_conversion, name, phone, email, value)
        await interaction.followup.send(
            f"✅ Purchase event sent to Meta!\n**Name:** {name}\n**Phone:** {phone}\n**Email:** {email}\n**Value:** R${value:.2f}\n**Events received:** {received}",
        )
    except Exception as exc:
        await interaction.followup.send(f"Error sending to Meta: {exc}", ephemeral=True)


@app_commands.command(name="test_reports", description="Send daily summary and weekly leaderboard now (test).")
async def test_reports_slash(interaction: discord.Interaction) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)

    channel = client.get_channel(PATREON_ANNOUNCEMENT_CHANNEL_ID)
    if not channel:
        await interaction.followup.send("Announcement channel not found.", ephemeral=True)
        return

    # --- Daily summary (live from Patreon API) ---
    try:
        loop = asyncio.get_event_loop()
        activity = await loop.run_in_executor(None, _fetch_patreon_daily_activity)
        joined = activity["joined"]
        from datetime import timezone as _tz
        cutoff_24h = (datetime.now(_tz.utc) - timedelta(hours=24)).isoformat()
        all_logged = _load_events()
        cancels = [e for e in all_logged if e["event"] in ("members:pledge:delete", "members:delete") and e.get("ts", "") >= cutoff_24h]

        lines = ["📊 **Daily Patreon Summary** (last 24h)\n"]
        if joined:
            lines.append(f"💎 **{len(joined)}** new paid subscriber(s):")
            for e in joined:
                tier = f" ({e['tier']})" if e["tier"] else ""
                lines.append(f"  • **{e['name']}**{tier} — ${e['amount']:.2f}/mo")
        if cancels:
            lines.append(f"❌ **{len(cancels)}** cancellation(s):")
            for e in cancels:
                tier = f" ({e['tier']})" if e["tier"] else ""
                lines.append(f"  • **{e['name']}**{tier}")
        if len(lines) == 1:
            await channel.send("📊 **Daily Patreon Summary** — No new subscribers or cancellations in the last 24h.")
        else:
            lines.append(f"\n**Net change: {len(joined) - len(cancels):+d}**")
            await _send_chunked(channel, lines)
    except Exception as exc:
        await channel.send(f"📊 **Daily Patreon Summary** — Error: {exc}"[:1900])

    # --- Weekly summary (from persisted log) ---
    from datetime import timezone as _tz
    cutoff_7d = (datetime.now(_tz.utc) - timedelta(days=7)).isoformat()
    w_events = [e for e in _load_events() if e.get("ts", "") >= cutoff_7d]
    w_paid = [e for e in w_events if e["event"] == "members:pledge:create"]
    w_free = [e for e in w_events if e["event"] == "members:create"]
    w_cancels = [e for e in w_events if e["event"] in ("members:pledge:delete", "members:delete")]
    w_new = len(w_paid) + len(w_free)
    w_cancel = len(w_cancels)

    if w_new == 0 and w_cancel == 0:
        await channel.send("📅 **Weekly Patreon Summary** — No activity this week.")
    else:
        lines = ["📅 **Weekly Patreon Summary**\n"]
        if w_paid:
            lines.append(f"💎 **{len(w_paid)}** new paid subscriber(s):")
            for e in w_paid:
                tier = f" ({e['tier']})" if e["tier"] else ""
                lines.append(f"  • **{e['name']}**{tier} — ${e['amount']:.2f}/mo")
        if w_free:
            lines.append(f"👋 **{len(w_free)}** new free member(s):")
            for e in w_free:
                lines.append(f"  • **{e['name']}**")
        if w_cancels:
            lines.append(f"❌ **{len(w_cancels)}** cancellation(s):")
            for e in w_cancels:
                lines.append(f"  • **{e['name']}**")
        lines.append(f"\n**Net change this week: {w_new - w_cancel:+d}**")
        await channel.send("\n".join(lines))

    await interaction.followup.send("✅ Reports sent!", ephemeral=True)


class FeedbackBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.synced = False
        self._status_task: asyncio.Task | None = None
        self._daily_task: asyncio.Task | None = None
        self._weekly_task: asyncio.Task | None = None
        self._youtube_task: asyncio.Task | None = None
        self._ue_seen_video_ids: set[str] = set()
        self._conversation_history: dict[int, list[dict]] = {}
        self._processed_messages: set[int] = set()

    def _clean_post_title(self, title: str) -> str:
        import re
        # Remove common suffixes from Patreon post titles
        noise = [
            r"\s*[-–]\s*(Premium|Standard|Basic)\s+Project\s+Files?",
            r"\s*[-–]\s*(Premium|Standard|Basic)\s+Animations?\s+Pack",
            r"\s*[-–]\s*Project\s+Files?",
            r"\s*[-–]\s*Animations?\s+Pack",
            r"\s*(Premium|Standard|Basic)\s+Project\s+Files?",
        ]
        for pattern in noise:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)
        return title.strip()

    async def _rotate_status(self) -> None:
        import random
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                statuses = []

                # 1. Latest Patreon post title
                if PATREON_ACCESS_TOKEN:
                    try:
                        loop = asyncio.get_event_loop()
                        posts = await loop.run_in_executor(None, _fetch_recent_posts, "LocoStandard", 1)
                        if posts:
                            clean = self._clean_post_title(posts[0]["title"])
                            statuses.append(discord.Activity(type=discord.ActivityType.playing, name=clean))
                    except Exception:
                        pass

                # 2. Live patron count
                if PATREON_ACCESS_TOKEN:
                    try:
                        loop = asyncio.get_event_loop()
                        patrons = await loop.run_in_executor(None, _fetch_top_patrons, 1000)
                        statuses.append(discord.Activity(type=discord.ActivityType.watching, name=f"{len(patrons)} patrons"))
                    except Exception:
                        pass

                # 3. Live server member count
                if GUILD_ID:
                    guild = self.get_guild(int(GUILD_ID))
                    if guild:
                        statuses.append(discord.Activity(type=discord.ActivityType.watching, name=f"{guild.member_count} devs 🎮"))

                # 4. Fixed statuses
                statuses.append(discord.Activity(type=discord.ActivityType.listening, name="LocoDev"))
                statuses.append(discord.Activity(type=discord.ActivityType.watching, name="UE5 Devs build"))
                statuses.append(discord.Game(name="Unreal Engine 5"))

                if statuses:
                    await self.change_presence(activity=random.choice(statuses))
            except Exception as exc:
                logger.warning("Status rotation error: %s", exc)

            await asyncio.sleep(600)  # 10 minutes

    async def _daily_summary(self) -> None:
        """Every day at midnight Sao Paulo, post a summary of the day's Patreon events."""
        from zoneinfo import ZoneInfo
        await self.wait_until_ready()
        sp = ZoneInfo("America/Sao_Paulo")
        while not self.is_closed():
            try:
                now = datetime.now(sp)
                # Calculate seconds until next 9 AM SP
                next_9am = now.replace(hour=9, minute=0, second=0, microsecond=0)
                if now >= next_9am:
                    next_9am += timedelta(days=1)
                wait_secs = (next_9am - now).total_seconds()
                await asyncio.sleep(wait_secs)

                channel = self.get_channel(PATREON_ANNOUNCEMENT_CHANNEL_ID)
                if not channel:
                    continue

                # Fetch live data from Patreon API
                loop = asyncio.get_event_loop()
                activity = await loop.run_in_executor(None, _fetch_patreon_daily_activity)
                joined = activity["joined"]

                from datetime import timezone as _tz
                cutoff_24h = (datetime.now(_tz.utc) - timedelta(hours=24)).isoformat()
                all_logged = _load_events()
                cancels = [e for e in all_logged if e["event"] in ("members:pledge:delete", "members:delete") and e.get("ts", "") >= cutoff_24h]
                _daily_events.clear()

                lines = ["📊 **Daily Patreon Summary** (last 24h)\n"]
                if joined:
                    lines.append(f"💎 **{len(joined)}** new paid subscriber(s):")
                    for e in joined:
                        tier = f" ({e['tier']})" if e["tier"] else ""
                        lines.append(f"  • **{e['name']}**{tier} — ${e['amount']:.2f}/mo")
                if cancels:
                    lines.append(f"❌ **{len(cancels)}** cancellation(s):")
                    for e in cancels:
                        tier = f" ({e['tier']})" if e["tier"] else ""
                        lines.append(f"  • **{e['name']}**{tier}")

                if len(lines) == 1:
                    await channel.send("📊 **Daily Patreon Summary** — No new subscribers or cancellations in the last 24h.")
                else:
                    net = len(joined) - len(cancels)
                    lines.append(f"\n**Net change: {net:+d}**")
                    await _send_chunked(channel, lines)

            except Exception as exc:
                logger.warning("Daily summary error: %s", exc)
                await asyncio.sleep(60)

    async def _watch_unreal_engine_youtube(self) -> None:
        """Poll Unreal Engine YouTube RSS feed every 10 minutes and post new videos."""
        import xml.etree.ElementTree as ET
        from urllib import request as _req
        await self.wait_until_ready()
        RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id=UCBobmJyzsJ6Ll7UbfhI4iwQ"
        while not self.is_closed():
            try:
                loop = asyncio.get_event_loop()
                def _fetch_rss():
                    req = _req.Request(RSS_URL, headers={"User-Agent": "LocoDev Bot"})
                    with _req.urlopen(req, timeout=15) as resp:
                        return resp.read()
                xml_data = await loop.run_in_executor(None, _fetch_rss)
                root = ET.fromstring(xml_data)
                ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
                entries = root.findall("atom:entry", ns)
                if not entries:
                    await asyncio.sleep(600)
                    continue
                latest = entries[0]
                video_id = latest.findtext("yt:videoId", namespaces=ns)
                title = latest.findtext("atom:title", namespaces=ns, default="New video")
                link_el = latest.find("atom:link", ns)
                url = link_el.get("href", "") if link_el is not None else f"https://www.youtube.com/watch?v={video_id}"

                if not self._ue_seen_video_ids:
                    # On first run seed with all current videos, don't announce
                    for entry in entries:
                        vid = entry.findtext("yt:videoId", namespaces=ns)
                        if vid:
                            self._ue_seen_video_ids.add(vid)
                else:
                    for entry in entries:
                        vid = entry.findtext("yt:videoId", namespaces=ns)
                        if not vid or vid in self._ue_seen_video_ids:
                            continue
                        self._ue_seen_video_ids.add(vid)
                        t = entry.findtext("atom:title", namespaces=ns, default="New video")
                        l_el = entry.find("atom:link", ns)
                        u = l_el.get("href", "") if l_el is not None else f"https://www.youtube.com/watch?v={vid}"
                        channel = self.get_channel(YOUTUBE_NOTIFY_CHANNEL_ID)
                        if channel:
                            await channel.send(
                                f"🎮 **Unreal Engine** just posted a new video!\n**{t}**\n{u}"
                            )
            except Exception as exc:
                logger.warning("YouTube watcher error: %s", exc)
            await asyncio.sleep(1800)  # check every 30 minutes

    async def _weekly_summary(self) -> None:
        """Every Monday at 9 AM Sao Paulo, post a weekly Patreon summary."""
        from zoneinfo import ZoneInfo
        await self.wait_until_ready()
        sp = ZoneInfo("America/Sao_Paulo")
        while not self.is_closed():
            try:
                now = datetime.now(sp)
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0 and now.hour >= 9:
                    days_until_monday = 7
                next_monday = (now + timedelta(days=days_until_monday)).replace(
                    hour=9, minute=0, second=0, microsecond=0
                )
                wait_secs = (next_monday - now).total_seconds()
                await asyncio.sleep(wait_secs)

                from datetime import timezone as _tz
                cutoff_7d = (datetime.now(_tz.utc) - timedelta(days=7)).isoformat()
                events = [e for e in _load_events() if e.get("ts", "") >= cutoff_7d]
                _weekly_events.clear()

                channel = self.get_channel(PATREON_ANNOUNCEMENT_CHANNEL_ID)
                if not channel:
                    continue

                paid_subs = [e for e in events if e["event"] == "members:pledge:create"]
                free_joins = [e for e in events if e["event"] == "members:create"]
                cancels = [e for e in events if e["event"] in ("members:pledge:delete", "members:delete")]
                total_new = len(paid_subs) + len(free_joins)
                total_cancel = len(cancels)

                if total_new == 0 and total_cancel == 0:
                    await channel.send("📅 **Weekly Patreon Summary** — No activity this week.")
                    continue

                lines = ["📅 **Weekly Patreon Summary**\n"]

                if paid_subs:
                    lines.append(f"💎 **{len(paid_subs)}** new paid subscriber(s):")
                    for e in paid_subs:
                        tier = f" ({e['tier']})" if e["tier"] else ""
                        lines.append(f"  • **{e['name']}**{tier} — ${e['amount']:.2f}/mo")

                if free_joins:
                    lines.append(f"👋 **{len(free_joins)}** new free member(s):")
                    for e in free_joins:
                        lines.append(f"  • **{e['name']}**")

                if cancels:
                    lines.append(f"❌ **{len(cancels)}** cancellation(s):")
                    for e in cancels:
                        lines.append(f"  • **{e['name']}**")

                lines.append(f"\n**Net change this week: {total_new - total_cancel:+d}**")
                await channel.send("\n".join(lines))

            except Exception as exc:
                logger.warning("Weekly summary error: %s", exc)
                await asyncio.sleep(60)

    async def setup_hook(self) -> None:
        self.tree.add_command(report_command_slash)
        self.tree.add_command(check_patron_slash)
        self.tree.add_command(top_patrons_slash)
        self.tree.add_command(recent_posts_slash)
        self.tree.add_command(meta_conversion_slash)
        self.tree.add_command(test_reports_slash)

    async def on_ready(self) -> None:
        if not self.synced:
            # Clear global commands to remove duplicates
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            # Re-add commands and sync to guild
            self.tree.add_command(report_command_slash)
            self.tree.add_command(check_patron_slash)
            self.tree.add_command(top_patrons_slash)
            self.tree.add_command(recent_posts_slash)
            self.tree.add_command(meta_conversion_slash)
            self.tree.add_command(test_reports_slash)
            if GUILD_ID:
                guild = discord.Object(id=int(GUILD_ID))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info("Synced commands to guild %s", GUILD_ID)
            else:
                await self.tree.sync()
                logger.info("Synced global commands")
            self.synced = True

        if self._status_task is None or self._status_task.done():
            self._status_task = asyncio.create_task(self._rotate_status())
        if self._daily_task is None or self._daily_task.done():
            self._daily_task = asyncio.create_task(self._daily_summary())
        if self._weekly_task is None or self._weekly_task.done():
            self._weekly_task = asyncio.create_task(self._weekly_summary())
        if self._youtube_task is None or self._youtube_task.done():
            self._youtube_task = asyncio.create_task(self._watch_unreal_engine_youtube())
        assert self.user is not None
        logger.info("Logged in as %s (%s)", self.user, self.user.id)

    async def on_member_join(self, member: discord.Member) -> None:
        message = (
            f"Hey {member.mention}! 👋\n\n"
            "Welcome to the **LocoDev UE5 Discord Server** 🚀\n"
            "Glad to have you here!\n\n"
            "This server is focused on high-quality **Unreal Engine 5** gameplay systems, especially Blueprint-driven AAA mechanics like locomotion, climbing, animation logic, and debugging workflows.\n\n"
            "───────────────────\n\n"
            "🔥 **START HERE**\n\n"
            "📺 **Free UE5 Tutorials (YouTube)**\n"
            "Learn real production systems, explained step-by-step:\n"
            "> https://www.youtube.com/@LocoDev/videos\n\n"
            "💎 **Premium Systems & Full Projects (Patreon)**\n"
            "Ready-to-use systems, clean Blueprints, docs, and continuous updates:\n"
            "> https://www.patreon.com/LocoDev\n\n"
            "**Patreon includes:**\n"
            "> ⚙️ Advanced locomotion & traversal systems\n"
            "> 🧱 Clean, scalable Blueprint architecture\n"
            "> 🎬 Animation-driven gameplay logic\n"
            "> 🐛 Debug tools & AAA-style polish\n"
            "> 📁 Exclusive projects and updates\n"
            "> 📄 Documents to follow along\n"
            "> 👕 Physical merch rewards\n\n"
            "───────────────────\n\n"
            "💬 **NEED HELP?**\n"
            "> • Ask questions in the Discord channels\n"
            "> • Share your work and get feedback\n"
            "> • Learn from other devs building real systems\n"
            "> • This community is about learning by building, not shortcuts\n\n"
            "🔗 **ALREADY A PATREON MEMBER?**\n"
            "> Go to your Patreon → connect your Discord account → unlock exclusive text channels here on the server.\n\n"
            "───────────────────\n\n"
            "Happy developing 🔧\n"
            "— **LocoDev** 🚀"
        )
        try:
            await member.send(message)
            logger.info("Sent welcome DM to %s", member)
        except discord.Forbidden:
            logger.warning("Could not DM %s (DMs disabled)", member)
        role = discord.utils.get(member.guild.roles, name="Member")
        if role:
            try:
                await member.add_roles(role)
                logger.info("Assigned 'Member' role to %s", member)
            except discord.Forbidden:
                logger.warning("Missing permissions to assign 'Member' role to %s", member)
        else:
            logger.warning("Role 'Member' not found in guild %s", member.guild.name)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if self.user not in message.mentions:
            return
        if not ANTHROPIC_API_KEY:
            return
        if message.id in self._processed_messages:
            return
        self._processed_messages.add(message.id)
        # Keep set size bounded
        if len(self._processed_messages) > 1000:
            self._processed_messages.clear()

        question = message.content.replace(f"<@{self.user.id}>", "").strip()
        _image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        def _is_image_attachment(a):
            if a.content_type and a.content_type.startswith("image/"):
                return True
            import os as _os
            ext = _os.path.splitext(a.filename)[1].lower()
            return ext in _image_exts

        # Collect attachments from this message AND the replied-to message
        all_attachments = list(message.attachments)
        if message.reference and message.reference.resolved:
            ref_msg = message.reference.resolved
            if hasattr(ref_msg, "attachments"):
                all_attachments.extend(ref_msg.attachments)

        has_images = any(_is_image_attachment(a) for a in all_attachments)
        if not question and not has_images:
            await message.reply("Hey! How can I help? 😊")
            return

        # Build user message content (text + images)
        user_content: list = []
        image_count = 0
        for attachment in all_attachments:
            if _is_image_attachment(attachment):
                import aiohttp as _aiohttp
                async with _aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                        if resp.status == 200:
                            img_bytes = await resp.read()
                            import base64 as _base64
                            img_b64 = _base64.b64encode(img_bytes).decode("utf-8")
                            # Detect actual image type from bytes (Discord may report wrong content_type)
                            if img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                                media_type = "image/png"
                            elif img_bytes[:3] == b'\xff\xd8\xff':
                                media_type = "image/jpeg"
                            elif img_bytes[:4] == b'GIF8':
                                media_type = "image/gif"
                            elif img_bytes[:4] == b'RIFF' and img_bytes[8:12] == b'WEBP':
                                media_type = "image/webp"
                            else:
                                ct = attachment.content_type or "image/png"
                                media_type = ct.split(";")[0].strip()
                            user_content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": img_b64,
                                }
                            })
                            image_count += 1
        # Add text after images so Claude sees the image first
        prompt_text = question if question else ("Please describe and analyze what you see in this image." if image_count > 0 else "")
        if image_count > 0 and not question:
            user_content.append({"type": "text", "text": "Please describe and analyze what you see in this image."})
        elif question:
            user_content.append({"type": "text", "text": question})
        if not user_content:
            await message.reply("Hey! How can I help? 😊")
            return

        # Build conversation history for this user (last 10 exchanges)
        user_id = message.author.id
        if user_id not in self._conversation_history:
            self._conversation_history[user_id] = []
        history = self._conversation_history[user_id]
        # Store text-only summary in history (no base64) to keep memory light
        history_text = (f"[User shared {image_count} image(s)] " if image_count > 0 else "") + (question or "")
        history.append({"role": "user", "content": user_content if image_count > 0 else history_text.strip()})
        # Keep only last 10 messages to avoid token limits
        if len(history) > 10:
            history = history[-10:]
            self._conversation_history[user_id] = history

        async with message.channel.typing():
            try:
                import anthropic as _anthropic
                loop = asyncio.get_event_loop()
                msgs = list(history)
                def _ask():
                    ai = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                    resp = ai.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=1024,
                        system=(
                            "You are LocoBOT, the official assistant of the LocoDev Discord server. "
                            "Always reply in English in a friendly and direct tone. "
                            "Talk about LocoDev as if you are part of the team.\n\n"
                            "ABOUT LOCODEV:\n"
                            "- Creator: LocoDev, developer with 4+ years of Unreal Engine 5 experience\n"
                            "- Focus: AAA gameplay systems with Blueprints (locomotion, climbing, combat, animation, AI)\n"
                            "- Free YouTube: youtube.com/@LocoDev/videos\n"
                            "- Premium content on Patreon: patreon.com/LocoDev\n\n"
                            "PATREON PLANS:\n"
                            "- LocoBasic: R$5/month — basic systems access\n"
                            "- LocoStandard: R$10/month — intermediate systems + project files\n"
                            "- LocoPremium: R$20/month — everything + complete projects, PDFs, merch, priority support, weekly calls\n\n"
                            "ALL PLANS INCLUDE:\n"
                            "- Lifetime access to tier content\n"
                            "- Exclusive Discord community\n"
                            "- Support from experienced devs\n\n"
                            "IMPORTANT: Only mention Patreon or the plans if someone specifically asks about them. "
                            "Focus on actually helping with the question. Do not add Patreon plugs at the end of replies.\n\n"
                            "If you don't know the answer, say so honestly and suggest contacting LocoDev."
                        ),
                        messages=msgs
                    )
                    return resp.content[0].text
                answer = await loop.run_in_executor(None, _ask)
                # Store bot reply in history
                self._conversation_history[user_id].append({"role": "assistant", "content": answer})
                if len(answer) <= 1900:
                    await message.reply(answer)
                else:
                    await message.reply(answer[:1900])
                    await message.channel.send(answer[1900:])
            except Exception as exc:
                logger.warning("AI responder error: %s", exc, exc_info=True)
                await message.reply(f"Sorry, I couldn't process your question right now. Try again! 🙏")


# Dedup cache: (member_id, event) -> timestamp, to avoid duplicate announcements
_patreon_event_cache: dict[tuple, float] = {}
_PATREON_DEDUP_SECONDS = 30

# Event trackers for scheduled summaries
_EVENTS_LOG_PATH = "/app/patreon_events.json"

def _load_events() -> list[dict]:
    """Load persisted events, dropping entries older than 8 days."""
    from datetime import timezone
    try:
        with open(_EVENTS_LOG_PATH, "r") as f:
            events = json.load(f)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        return [e for e in events if e.get("ts", "") >= cutoff]
    except Exception:
        return []

def _save_events(events: list[dict]) -> None:
    try:
        with open(_EVENTS_LOG_PATH, "w") as f:
            json.dump(events, f)
    except Exception as exc:
        logger.warning("Could not save events log: %s", exc)

def _append_event(entry: dict) -> None:
    events = _load_events()
    events.append(entry)
    _save_events(events)

# In-memory lists still used for dedup, backed by file
_daily_events: list[dict] = []   # {"event": str, "name": str, "tier": str|None, "amount": float, "ts": str}
_weekly_events: list[dict] = []  # same structure

async def patreon_webhook_handler(request):
    import hmac, hashlib, time
    from aiohttp import web
    body = await request.read()
    sig = request.headers.get("X-Patreon-Signature", "")
    if PATREON_WEBHOOK_SECRET:
        expected = hmac.new(PATREON_WEBHOOK_SECRET.encode(), body, hashlib.md5).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return web.Response(status=403, text="Invalid signature")
    event = request.headers.get("X-Patreon-Event", "")
    try:
        data = json.loads(body)
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    attrs = data.get("data", {}).get("attributes", {})
    member_id = data.get("data", {}).get("id", "")
    included = data.get("included", [])
    full_name = attrs.get("full_name", "Someone")
    amount_cents = attrs.get("currently_entitled_amount_cents") or attrs.get("will_pay_amount_cents") or 0
    lifetime_cents = attrs.get("lifetime_support_cents") or 0
    is_returning = lifetime_cents > amount_cents

    # Dedup check — use 6 hours for payment events, 30s for others
    cache_key = (member_id, event)
    now = time.monotonic()
    dedup_seconds = 21600 if event in ("members:update", "members:pledge:create", "members:pledge:delete") else 30
    if now - _patreon_event_cache.get(cache_key, 0) < dedup_seconds:
        logger.info("Skipping duplicate Patreon event %s for %s", event, member_id)
        return web.Response(status=200, text="OK")
    _patreon_event_cache[cache_key] = now

    # Track event for daily and weekly summaries
    from datetime import timezone as _tz
    _entry = {
        "event": event,
        "name": full_name,
        "tier": None,  # filled below after tier extraction
        "amount": amount_cents / 100,
        "ts": datetime.now(_tz.utc).isoformat(),
    }
    _daily_events.append(_entry)
    _weekly_events.append(_entry)

    discord_id = None
    tier_title = None
    for inc in included:
        if inc.get("type") == "user":
            social = inc.get("attributes", {}).get("social_connections", {})
            if social and social.get("discord"):
                discord_id = social["discord"].get("user_id")
        if inc.get("type") == "tier":
            tier_title = inc.get("attributes", {}).get("title")

    # Update tier in tracked event and persist to file
    _entry["tier"] = tier_title
    _append_event(_entry)

    # Correct tier name based on amount paid (Patreon sometimes sends wrong tier name)
    def _correct_tier(title, cents):
        if cents <= 0:
            return title
        if cents <= 700:       # up to $7 → Basic
            return "LocoBasic"
        elif cents <= 1500:    # up to $15 → Standard
            return "LocoStandard"
        else:                  # $16+ → Premium
            return "LocoPremium"

    if amount_cents > 0:
        tier_title = _correct_tier(tier_title, amount_cents)

    # If Discord linked: show "@DiscordMention/Patreon Name", otherwise just Patreon name
    name = f"<@{discord_id}>/**{full_name}**" if discord_id else f"**{full_name}**"
    tier_str = f" (**{tier_title}**)" if tier_title else ""
    dollars = amount_cents / 100

    returning_str = f" *(returning patron — ${lifetime_cents/100:.2f} lifetime)*" if is_returning else ""

    if event == "members:create":
        msg = f"🎉 {name} just joined **LocoDev** on Patreon for free!{returning_str}"
    elif event == "members:delete":
        msg = f"👋 {name} just left **LocoDev** on Patreon."
    elif event == "members:pledge:create":
        msg = f"💎 {name} just subscribed to LocoDev on Patreon{tier_str} for **${dollars:.2f}/month**! Welcome!{returning_str}\n> 👉 Join them at patreon.com/LocoDev"
    elif event == "members:pledge:delete":
        msg = f"❌ {name} just cancelled their Patreon pledge{tier_str}."
    elif event == "members:pledge:update":
        msg = f"🔄 {name} updated their Patreon pledge{tier_str} — now **${dollars:.2f}/month**."
    elif event == "members:update":
        patron_status = attrs.get("patron_status")
        if patron_status == "declined_patron":
            msg = f"⚠️ {name}'s Patreon payment was declined."
        elif patron_status == "active_patron":
            msg = f"✅ {name}'s Patreon payment was successful{tier_str}."
        else:
            msg = None
    elif event == "posts:publish":
        title = attrs.get("title") or "New post"
        url = attrs.get("url", "")
        msg = f"📢 New post published on Patreon: **{title}** {url}"
    elif event == "posts:update":
        title = attrs.get("title") or "A post"
        msg = f"✏️ Patreon post updated: **{title}**"
    elif event == "posts:delete":
        msg = f"🗑️ A Patreon post was deleted."
    else:
        msg = None

    if msg:
        # Send full message to #bot-reports
        channel = client.get_channel(PATREON_ANNOUNCEMENT_CHANNEL_ID)
        if channel:
            await channel.send(msg)
            logger.info("Posted Patreon announcement: %s", msg)
        else:
            logger.warning("Announcement channel %s not found", PATREON_ANNOUNCEMENT_CHANNEL_ID)

        # Send short public message to #patreon-members for new members (free or paid)
        public_channel = client.get_channel(PATREON_PUBLIC_CHANNEL_ID)
        if public_channel:
            public_name = f"<@{discord_id}>/**{full_name}**" if discord_id else f"**{full_name}**"
            if event == "members:pledge:create" and tier_title:
                public_msg = f"💎 {public_name} joined **{tier_title}**\n> 👉 patreon.com/LocoDev"
                await public_channel.send(public_msg)
            elif event == "members:create":
                public_msg = f"👋 {public_name} just joined **LocoDev** on Patreon!"
                await public_channel.send(public_msg)

    return web.Response(status=200, text="OK")


async def start_webhook_server():
    from aiohttp import web
    app = web.Application()
    app.router.add_post("/patreon/webhook", patreon_webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Patreon webhook server listening on port 8080")


client = FeedbackBot()


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN in .env")

    async def main():
        await start_webhook_server()
        await client.start(TOKEN)

    asyncio.run(main())
