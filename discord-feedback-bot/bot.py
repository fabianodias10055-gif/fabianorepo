import asyncio
import collections
import csv
import json
import logging
import os
import re
import tempfile
import threading
import time
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

# Serializes all local JSON state writes (KB, Patreon events, webhook-seen).
_json_write_lock = threading.Lock()


def _atomic_write_json(path: str, obj) -> None:
    """Write JSON to `path` atomically (temp file + os.replace) under a lock, so a
    crash mid-write or an interleaved writer can't truncate/corrupt the file."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    with _json_write_lock:
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
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
OWNER_DISCORD_ID = int(os.getenv("OWNER_DISCORD_ID", "690691536983425044"))
PATREON_WEBHOOK_SECRET = os.getenv("PATREON_WEBHOOK_SECRET", "")
PATREON_ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("PATREON_ANNOUNCEMENT_CHANNEL_ID", "1490377274749354207"))
PATREON_PUBLIC_CHANNEL_ID = int(os.getenv("PATREON_PUBLIC_CHANNEL_ID", "1158395982485147689"))
YOUTUBE_NOTIFY_CHANNEL_ID = int(os.getenv("YOUTUBE_NOTIFY_CHANNEL_ID", "1481432850212585655"))
LINK_MANAGEMENT_CHANNEL_ID = int(os.getenv("LINK_MANAGEMENT_CHANNEL_ID", "1490377274749354207"))
MIRROR_SOURCE_CHANNEL_ID = int(os.getenv("MIRROR_SOURCE_CHANNEL_ID", "1160715880787869729"))
MIRROR_DEST_CHANNEL_ID = int(os.getenv("MIRROR_DEST_CHANNEL_ID", "1499029543078465696"))
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
# Proactive KB auto-reply thresholds
KB_AUTO_MIN_SCORE = int(os.getenv("KB_AUTO_MIN_SCORE", "3"))   # min non-stopword word overlap
KB_AUTO_COOLDOWN = int(os.getenv("KB_AUTO_COOLDOWN", "120"))   # seconds between KB replies per user per channel
# Per-user cooldown on the expensive @mention/reply AI path (subprocess + fetches)
AI_USER_COOLDOWN = int(os.getenv("AI_USER_COOLDOWN", "8"))     # seconds between AI answers per user
# Whether to attach a KB entry's stored images to FAQ auto-replies. Off by
# default because historical entries also stored the asker's own question
# screenshots, which made the bot post unrelated images. Re-enable once the
# stored KB images are curated.
KB_POST_IMAGES = os.getenv("KB_POST_IMAGES", "").lower() in ("1", "true", "yes")
# Unanswered-question escalation
UNANSWERED_ESCALATION_MINUTES = int(os.getenv("UNANSWERED_ESCALATION_MINUTES", "15"))  # 0 disables
UNANSWERED_ALERT_CHANNEL_ID = int(os.getenv("UNANSWERED_ALERT_CHANNEL_ID", "0")) or None  # falls back to mirror channel
UNANSWERED_PUSHOVER = os.getenv("UNANSWERED_PUSHOVER", "").lower() in ("1", "true", "yes")  # also ping owner's phone
# Spam detection thresholds (image-only flood across channels)
SPAM_IMAGE_COUNT = int(os.getenv("SPAM_IMAGE_COUNT", "3"))      # image-only msgs within window
SPAM_IMAGE_CHANNELS = int(os.getenv("SPAM_IMAGE_CHANNELS", "2")) # across this many channels
SPAM_IMAGE_WINDOW = int(os.getenv("SPAM_IMAGE_WINDOW", "15"))    # seconds
# General cross-channel flood
SPAM_MSG_COUNT = int(os.getenv("SPAM_MSG_COUNT", "6"))           # any msgs within window
SPAM_MSG_CHANNELS = int(os.getenv("SPAM_MSG_CHANNELS", "3"))     # across this many channels
SPAM_MSG_WINDOW = int(os.getenv("SPAM_MSG_WINDOW", "10"))        # seconds
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "")
PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN", "")
KB_CHANNEL_IDS = {1158395982485147692, 1459914723330883727, 1460338435163164827}
MAX_MESSAGES_PER_CHANNEL = int(os.getenv("MAX_MESSAGES_PER_CHANNEL", "250"))
PROJECTS_FORUM_CHANNEL_ID = os.getenv("PROJECTS_FORUM_CHANNEL_ID")
# ── New-merch email watcher ───────────────────────────────────────────────────
# Patreon has no webhook for merch, so we poll a mailbox for the "new merch" email
# and repost it to the merch alert channel. Feature is OFF unless HOST/USER/PASSWORD
# are all set. Use a dedicated inbox + an app-specific password, never a main login.
MERCH_EMAIL_HOST = os.getenv("MERCH_EMAIL_HOST", "")              # e.g. imap.gmail.com
MERCH_EMAIL_PORT = int(os.getenv("MERCH_EMAIL_PORT", "993"))
MERCH_EMAIL_USER = os.getenv("MERCH_EMAIL_USER", "")
MERCH_EMAIL_PASSWORD = os.getenv("MERCH_EMAIL_PASSWORD", "")
MERCH_EMAIL_MAILBOX = os.getenv("MERCH_EMAIL_MAILBOX", "INBOX")
MERCH_EMAIL_POLL_SECS = int(os.getenv("MERCH_EMAIL_POLL_SECS", "300"))
# Comma-separated substrings; an email counts as a merch drop only if its From
# matches one of the FROM filters AND its Subject matches one of the SUBJECT filters.
MERCH_EMAIL_FROM_FILTER = tuple(
    s.strip().lower() for s in os.getenv("MERCH_EMAIL_FROM_FILTER", "patreon.com").split(",") if s.strip()
)
MERCH_EMAIL_SUBJECT_FILTER = tuple(
    s.strip().lower() for s in os.getenv("MERCH_EMAIL_SUBJECT_FILTER", "merch").split(",") if s.strip()
)
# Channel that merch alerts are posted to (defaults to the public patreon-members channel).
MERCH_ALERT_CHANNEL_ID = int(os.getenv("MERCH_ALERT_CHANNEL_ID", "1158395982485147689"))
# "How to earn merch" link appended to each alert. Must be a real short link
# (create it with /shorten) or it will 404. Overridable so you can change it live.
MERCH_INFO_URL = os.getenv("MERCH_INFO_URL", "locodev.dev/docs/patreonmerch")
_MERCH_SEEN_PATH = os.getenv("MERCH_SEEN_PATH", "/app/data/merch_email_seen.json")
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


def _build_click_report_embed() -> discord.Embed:
    from shortener import get_top_links
    try:
        from zoneinfo import ZoneInfo
        _tz = ZoneInfo("America/Sao_Paulo")
    except Exception:
        _tz = timezone(timedelta(hours=-3))
    now = datetime.now(_tz)
    today_str = now.strftime("%b %d, %Y")
    top = get_top_links(days=1, limit=5)
    if not top or all(r["clicks"] == 0 for r in top):
        return discord.Embed(title="locodev.dev Click Report", description="No clicks in the last 24 hours.", color=0xF97316)
    lines = []
    for i, row in enumerate(top, 1):
        label = _fmt_link(row["prefix"], row["slug"])
        clicks = int(row["clicks"])
        lines.append(f"{i}. **{label}** — {clicks} click{'s' if clicks != 1 else ''}")
    total = sum(int(r["clicks"]) for r in top)
    winner = top[0]
    winner_label = _fmt_link(winner["prefix"], winner["slug"])
    winner_pct = int(winner["clicks"] / total * 100) if total else 0
    embed = discord.Embed(
        title="locodev.dev Click Report",
        description=f"Performance overview for **Last 24 Hours**",
        color=0xF97316,
    )
    embed.add_field(name="Report Period", value=f"{today_str}", inline=False)
    embed.add_field(name="Top Link", value=winner_label, inline=True)
    embed.add_field(name="Winner Clicks", value=str(winner["clicks"]), inline=True)
    embed.add_field(name="Winner Share", value=f"{winner_pct}%", inline=True)
    embed.add_field(name="Top 5 Total", value=f"{total} clicks", inline=False)
    embed.add_field(name="Top 5 Leaderboard", value="\n".join(lines), inline=False)
    embed.set_footer(text="Data from locodev.dev shortener")
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


@app_commands.command(name="report", description="Send a click report or UE5 YouTube report instantly.")
@app_commands.describe(type="Which report to send.")
@app_commands.choices(type=[
    app_commands.Choice(name="locodev.dev Click Report (last 24h)", value="clicks"),
    app_commands.Choice(name="UE5 YouTube Top Channels", value="ue5"),
])
async def report_command_slash(
    interaction: discord.Interaction,
    type: app_commands.Choice[str],
) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        loop = asyncio.get_event_loop()
        if type.value == "clicks":
            embed = await loop.run_in_executor(None, _build_click_report_embed)
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


@app_commands.command(name="fix_roles", description="Manually assign the correct Patreon tier role to a user.")
@app_commands.describe(user="The Discord user to fix.", tier="The tier to assign.")
@app_commands.choices(tier=[
    app_commands.Choice(name="LocoBasic", value="LocoBasic"),
    app_commands.Choice(name="LocoStandard", value="LocoStandard"),
    app_commands.Choice(name="LocoPremium", value="LocoPremium"),
])
async def fix_roles_slash(interaction: discord.Interaction, user: discord.Member, tier: app_commands.Choice[str]) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    _tier_roles = ["LocoBasic", "LocoStandard", "LocoPremium"]
    try:
        # Remove existing tier roles
        roles_to_remove = [r for r in user.roles if r.name in _tier_roles]
        if roles_to_remove:
            await user.remove_roles(*roles_to_remove, reason="Manual fix by LocoDev")
        # Assign new role
        role = discord.utils.get(interaction.guild.roles, name=tier.value)
        if not role:
            await interaction.followup.send(f"Role `{tier.value}` not found in server.", ephemeral=True)
            return
        await user.add_roles(role, reason="Manual fix by LocoDev")
        await interaction.followup.send(f"✅ Assigned **{tier.value}** to {user.mention}.", ephemeral=True)
    except Exception as exc:
        await interaction.followup.send(f"Error: {exc}", ephemeral=True)


async def _send_chunked(channel, lines):
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



async def _send_pushover(title: str, message: str, sound: str = "cashregister") -> None:
    """Send a push notification via Pushover to the owner's phone."""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        return
    import aiohttp as _aiohttp
    try:
        async with _aiohttp.ClientSession() as session:
            resp = await session.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": PUSHOVER_API_TOKEN,
                    "user": PUSHOVER_USER_KEY,
                    "title": title,
                    "message": message,
                    "sound": sound,
                    "priority": 0,
                },
                timeout=_aiohttp.ClientTimeout(total=10),
            )
            body = await resp.json()
            if resp.status == 200 and body.get("status") == 1:
                logger.info("Pushover notification sent: %s", title)
            else:
                logger.warning("Pushover rejected notification: status=%s body=%s", resp.status, body)
    except Exception as _pe:
        logger.warning("Pushover notification failed: %s", _pe)


def _search_patreon_posts(query: str) -> list[dict]:
    """Search LocoDev's Patreon posts by title. Returns list of {title, url}."""
    from urllib import request as _req, parse as _parse
    if not PATREON_ACCESS_TOKEN:
        return []
    # Get campaign ID
    req = _req.Request(
        "https://www.patreon.com/api/oauth2/v2/campaigns",
        headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
    )
    with _req.urlopen(req, timeout=30) as resp:
        campaigns = json.load(resp)
    campaign_id = campaigns["data"][0]["id"]

    # Fetch posts with title and URL
    results = []
    cursor = None
    query_lower = query.lower()
    while True:
        params: dict = {
            "fields[post]": "title,url,published_at",
            "page[count]": "200",
        }
        if cursor:
            params["page[cursor]"] = cursor
        url = "https://www.patreon.com/api/oauth2/v2/campaigns/" + campaign_id + "/posts?" + _parse.urlencode(params)
        req = _req.Request(
            url,
            headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
        )
        with _req.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        for post in data.get("data", []):
            title = post.get("attributes", {}).get("title") or ""
            post_url = post.get("attributes", {}).get("url") or ""
            if query_lower in title.lower() and post_url:
                results.append({"title": title, "url": post_url})
        # Paginate
        next_cursor = data.get("meta", {}).get("pagination", {}).get("cursors", {}).get("next")
        if not next_cursor or not data.get("meta", {}).get("pagination", {}).get("has_more"):
            break
        cursor = next_cursor
        if len(results) >= 10:
            break
    return results[:5]


def _fetch_patreon_daily_activity(days: int = 1) -> dict:
    """Fetch members who joined or have declined status in last N days from Patreon API."""
    from urllib import request as _req, parse as _parse
    from datetime import timezone
    req = _req.Request(
        "https://www.patreon.com/api/oauth2/v2/campaigns",
        headers={"Authorization": f"Bearer {PATREON_ACCESS_TOKEN}", "User-Agent": "LocoDev Bot"},
    )
    with _req.urlopen(req, timeout=30) as resp:
        campaigns = json.load(resp)
    campaign_id = campaigns["data"][0]["id"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
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
        }],
        # Sent in the POST body, not the URL query string, so the token doesn't
        # land in proxy/access logs or error messages.
        "access_token": META_ACCESS_TOKEN,
    }).encode()

    url = f"https://graph.facebook.com/v21.0/{META_PIXEL_ID}/events"
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


@app_commands.command(name="test_pushover", description="Send a test Pushover notification to your phone.")
async def test_pushover_slash(interaction: discord.Interaction) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        await interaction.followup.send("PUSHOVER_USER_KEY or PUSHOVER_API_TOKEN not configured.", ephemeral=True)
        return
    await _send_pushover(
        title="💰 Test — New Patron!",
        message="This is a test notification from LocoDev Bot. Cash register works!",
        sound="cashregister",
    )
    await interaction.followup.send("Test notification sent to your phone!", ephemeral=True)


@app_commands.command(name="kb_scan", description="Scan all support channels and save approved (✅) Q&A pairs to the knowledge base.")
@app_commands.describe(limit="How many messages to scan per channel (default 500)")
async def kb_scan_slash(interaction: discord.Interaction, limit: int = 500) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    saved = 0
    for ch_id in KB_CHANNEL_IDS:
        try:
            channel = interaction.client.get_channel(ch_id) or await interaction.client.fetch_channel(ch_id)
            async for msg in channel.history(limit=limit, oldest_first=False):
                if not msg.reference:
                    continue
                approved = any(str(r.emoji) == _KB_APPROVE_EMOJI and r.count > 0 for r in msg.reactions)
                if not approved:
                    continue
                try:
                    question_msg = await channel.fetch_message(msg.reference.message_id)
                    question = question_msg.content.strip()
                    answer = msg.content.strip()
                    images = [
                        a.url for a in msg.attachments
                        if a.content_type and a.content_type.startswith("image/")
                    ]
                    if question and answer:
                        before = len(_kb_load())
                        _kb_add(question, answer, msg.author.display_name, images=images or None)
                        if len(_kb_load()) > before:
                            saved += 1
                except Exception:
                    continue
        except Exception as _se:
            logger.warning("KB scan error on channel %s: %s", ch_id, _se)
    total = len(_kb_load())
    await interaction.followup.send(f"Scan complete — saved **{saved}** new Q&A pairs across all channels. Knowledge base has **{total}** entries total.", ephemeral=True)


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

        # Dedup by (name, member_id) to prevent showing the same person twice
        def _dedup(items):
            _seen = set()
            _out = []
            for _e in items:
                _k = (_e.get("name"), _e.get("member_id"))
                if _k in _seen:
                    continue
                _seen.add(_k)
                _out.append(_e)
            return _out

        joined = _dedup(joined)
        cancels = _dedup(cancels)

        lines = ["📊 **Daily Patreon Summary** (last 24h)\n"]
        if joined:
            lines.append(f"💎 **{len(joined)}** new paid subscriber(s):")
            for e in joined:
                tier = f" ({e['tier']})" if e.get("tier") else ""
                lines.append(f"  • **{e['name']}**{tier} — ${e['amount']:.2f}/mo")
        if cancels:
            lines.append(f"❌ **{len(cancels)}** cancellation(s):")
            for e in cancels:
                tier = f" ({e.get('tier')})" if e.get("tier") else ""
                _ts = e.get("ts", "")[:16].replace("T", " ")
                lines.append(f"  • **{e['name']}**{tier} — {_ts} UTC")
        if len(lines) == 1:
            await channel.send("📊 **Daily Patreon Summary** — No new subscribers or cancellations in the last 24h.")
        else:
            lines.append(f"\n**Net change: {len(joined) - len(cancels):+d}**")
            await _send_chunked(channel, lines)
    except Exception as exc:
        await channel.send(f"📊 **Daily Patreon Summary** — Error: {exc}"[:1900])

    # --- Weekly summary (live from Patreon API for paid, log for free/cancels) ---
    from datetime import timezone as _tz
    cutoff_7d = (datetime.now(_tz.utc) - timedelta(days=7)).isoformat()
    loop = asyncio.get_event_loop()
    w_activity = await loop.run_in_executor(None, lambda: _fetch_patreon_daily_activity(days=7))
    w_paid = w_activity["joined"]
    w_events_log = [e for e in _load_events() if e.get("ts", "") >= cutoff_7d]
    w_free = [e for e in w_events_log if e["event"] == "members:create"]
    w_cancels = [e for e in w_events_log if e["event"] in ("members:pledge:delete", "members:delete")]

    def _dedup_w(items):
        _seen = set()
        _out = []
        for _e in items:
            _k = (_e.get("name"), _e.get("member_id"))
            if _k in _seen:
                continue
            _seen.add(_k)
            _out.append(_e)
        return _out

    w_paid = _dedup_w(w_paid)
    w_free = _dedup_w(w_free)
    w_cancels = _dedup_w(w_cancels)
    w_new = len(w_paid) + len(w_free)
    w_cancel = len(w_cancels)

    if w_new == 0 and w_cancel == 0:
        await channel.send("📅 **Weekly Patreon Summary** — No activity this week.")
    else:
        lines = ["📅 **Weekly Patreon Summary**\n"]
        if w_paid:
            lines.append(f"💎 **{len(w_paid)}** new paid subscriber(s):")
            for e in w_paid:
                tier = f" ({e['tier']})" if e.get("tier") else ""
                lines.append(f"  • **{e['name']}**{tier} — ${e['amount']:.2f}/mo")
        if w_free:
            lines.append(f"👋 **{len(w_free)}** new free member(s):")
            for e in w_free:
                _ts = e.get("ts", "")[:16].replace("T", " ")
                lines.append(f"  • **{e['name']}** — {_ts} UTC")
        if w_cancels:
            lines.append(f"❌ **{len(w_cancels)}** cancellation(s):")
            for e in w_cancels:
                _ts = e.get("ts", "")[:16].replace("T", " ")
                lines.append(f"  • **{e['name']}** — {_ts} UTC")
        lines.append(f"\n**Net change this week: {w_new - w_cancel:+d}**")
        await channel.send("\n".join(lines))

    await interaction.followup.send("✅ Reports sent!", ephemeral=True)


@app_commands.command(name="trial_stats", description="Show free trial starts and conversions to paid.")
@app_commands.describe(days="How many days back to look (default 30)")
async def trial_stats_slash(interaction: discord.Interaction, days: int = 30) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)

    from datetime import timezone as _tz
    now = datetime.now(_tz.utc)
    cutoff = (now - timedelta(days=days)).isoformat()
    now_iso = now.isoformat()
    events = [e for e in _load_events() if e.get("ts", "") >= cutoff]
    trials = [e for e in events if e.get("is_trial") is True]
    conversions = [e for e in events if e.get("is_trial_conversion") is True]
    trial_ids = {e.get("member_id") for e in trials}
    converted_ids = {e.get("member_id") for e in conversions}
    pending = [e for e in trials if e.get("member_id") not in converted_ids]

    # Split pending into still-active vs expired (trial_ends_at in the past)
    still_active = [e for e in pending if e.get("trial_ends_at", "9999") >= now_iso]
    expired = [e for e in pending if e.get("trial_ends_at", "9999") < now_iso]

    rate = f"{len(converted_ids)/len(trial_ids)*100:.0f}%" if trial_ids else "N/A"

    lines = [
        f"**📊 Free Trial Stats** (last {days} day{'s' if days != 1 else ''})",
        f"🆓 Trials started: **{len(trials)}**",
        f"💎 Converted to paid: **{len(converted_ids)}**",
        f"⏳ Still on trial: **{len(still_active)}**",
        f"❌ Trial ended, not converted: **{len(expired)}**",
        f"📈 Conversion rate: **{rate}**",
    ]
    if conversions:
        lines.append("\n**Conversions:**")
        for e in conversions:
            lines.append(f"  • **{e['name']}** → {e.get('tier') or 'unknown tier'}")
    if still_active:
        lines.append("\n**Still on trial:**")
        for e in still_active:
            ends = e.get("trial_ends_at", "")[:10] if e.get("trial_ends_at") else "unknown"
            lines.append(f"  • {e['name']} (ends {ends})")
    if expired:
        lines.append("\n**Trial expired, never converted:**")
        for e in expired:
            lines.append(f"  • {e['name']}")

    await interaction.followup.send("\n".join(lines), ephemeral=True)


# ── URL Shortener slash commands ──────────────────────────────────────────────

def _fmt_link(prefix: str, slug: str) -> str:
    """Display helper — turns root/_root into locodev.dev and root/slug into /slug."""
    if prefix == "root" and slug == "_root":
        return "locodev.dev"
    if prefix == "root":
        return f"/{slug}"
    return f"/{prefix}/{slug}"


# ── Link security ───────────────────────────────────────────────────────────

# Prefixes that are sensitive — only the server owner can modify them
_PROTECTED_PREFIXES = {"download", "docs", "freebuild", "free"}

# Domains allowed for download/docs links — reject anything else
_ALLOWED_DOWNLOAD_DOMAINS = {
    "drive.google.com",
    "docs.google.com",
    "github.com",
    "raw.githubusercontent.com",
    "dropbox.com",
    "dl.dropboxusercontent.com",
    "patreon.com",
    "locodev.dev",
    "blueprint.locodev.dev",
    "blueprintmastery.hotmart.host",
    "hotmart.com",
    "creator-spring.com",
    "mega.nz",
    "mega.co.nz",
}


# Max bytes to read from any server-side fetch (web page / image) before giving
# up — prevents a malicious endpoint from OOM-killing the process with a huge body.
MAX_FETCH_BYTES = 512 * 1024
# Per-image byte cap and per-message image count cap for the AI vision path.
MAX_IMAGE_BYTES = 5 * 1024 * 1024   # Claude vision per-image limit is ~5 MB
MAX_IMAGES_PER_MSG = 4


def _url_host_is_public(host: str) -> bool:
    """True only if EVERY address `host` resolves to is a global/public IP.
    Blocks SSRF to loopback/link-local/private/reserved ranges (incl. the cloud
    metadata endpoint and the bot's own localhost admin panel)."""
    import socket
    import ipaddress
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified
                or not ip.is_global):
            return False
    return True


def _is_safe_fetch_url(url: str) -> bool:
    """Gate for server-side URL fetches: http(s) only, resolving to a public IP."""
    from urllib.parse import urlparse as _up
    try:
        p = _up(url)
    except Exception:
        return False
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        return False
    return _url_host_is_public(p.hostname)


async def _fetch_capped(session, url, **kwargs):
    """GET `url` with redirects disabled and the body capped at MAX_FETCH_BYTES.
    Returns (status, body_bytes) or (None, b'') on error/oversize."""
    kwargs.setdefault("allow_redirects", False)
    try:
        async with session.get(url, **kwargs) as resp:
            body = await resp.content.read(MAX_FETCH_BYTES + 1)
            if len(body) > MAX_FETCH_BYTES:
                logger.warning("Fetch aborted — body exceeds %d bytes: %s", MAX_FETCH_BYTES, url)
                return None, b""
            return resp.status, body
    except Exception as _fe:
        logger.warning("Capped fetch failed for %s: %s", url, _fe)
        return None, b""


def _random_slug_suffix(length: int = 8) -> str:
    """Random base62 suffix appended to download/ slugs so they're unguessable."""
    import secrets, string
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# Prefixes that get an auto-appended random suffix for obscurity
_OBSCURED_PREFIXES = {"download"}

_LINK_AUDIT_PATH = "/app/data/link_audit.json"

def _audit_link_change(action: str, user_id: int, user_name: str,
                        prefix: str, slug: str, new_url: str, old_url: str = "") -> None:
    """Append a link change record to the audit log."""
    try:
        from datetime import timezone as _tz
        record = {
            "ts": datetime.now(_tz.utc).isoformat(),
            "action": action,
            "user_id": user_id,
            "user_name": user_name,
            "prefix": prefix,
            "slug": slug,
            "old_url": old_url,
            "new_url": new_url,
        }
        try:
            with open(_LINK_AUDIT_PATH) as _f:
                log = json.load(_f)
        except Exception:
            log = []
        log.append(record)
        # Keep last 500 entries
        if len(log) > 500:
            log = log[-500:]
        os.makedirs(os.path.dirname(_LINK_AUDIT_PATH), exist_ok=True)
        with open(_LINK_AUDIT_PATH, "w") as _f:
            json.dump(log, _f)
    except Exception as _ae:
        logger.warning("Audit log error: %s", _ae)

def _check_link_permission(interaction: discord.Interaction, prefix: str, url: str = "") -> str | None:
    """
    Returns an error message string if the action is not allowed, or None if OK.
    Checks:
    1. User must have 'LocoDev' role for any link operation
    2. For protected prefixes, user must be the server owner (OWNER_DISCORD_ID)
    3. For protected prefixes, destination URL must be on the allowed domain list
    """
    from urllib.parse import urlparse as _urlparse
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        return "❌ You don't have permission to manage links."

    # Scheme check for EVERY prefix (not just protected ones): a javascript:/data:
    # destination becomes clickable XSS in the admin dashboard.
    if url and _urlparse(url).scheme.lower() not in ("http", "https"):
        return "🚫 Destination URL must start with http:// or https://."

    if prefix in _PROTECTED_PREFIXES:
        # Must be the owner
        if OWNER_DISCORD_ID and interaction.user.id != OWNER_DISCORD_ID:
            return f"🔒 Only the server owner can modify `{prefix}/` links."
        # URL must be on allowlist
        if url:
            try:
                domain = _urlparse(url).netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                # Strip port if present
                domain = domain.split(":")[0]
                if not any(domain == d or domain.endswith("." + d) for d in _ALLOWED_DOWNLOAD_DOMAINS):
                    return (
                        f"🚫 URL domain `{domain}` is not on the trusted list for `{prefix}/` links.\n"
                        f"Allowed domains: {', '.join(sorted(_ALLOWED_DOWNLOAD_DOMAINS))}"
                    )
            except Exception:
                return "🚫 Could not parse the destination URL."
    return None  # all good


@app_commands.command(name="shorten", description="Create a new short link.")
@app_commands.describe(
    url="The destination URL",
    slug="The short slug (e.g. obstacleavoidance)",
    prefix="Prefix folder (default: p)",
)
async def shorten_slash(interaction: discord.Interaction, url: str, slug: str, prefix: str = "p") -> None:
    slug = slug.lower().strip()
    prefix = prefix.lower().strip()
    err = _check_link_permission(interaction, prefix, url)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    # Auto-append random suffix for obscured prefixes (e.g. download/)
    if prefix in _OBSCURED_PREFIXES and "/" not in slug:
        slug = f"{slug}/{_random_slug_suffix()}"
    from shortener import create_link
    ok = create_link(slug, url, prefix)
    if ok:
        _audit_link_change("create", interaction.user.id, str(interaction.user), prefix, slug, url)
        await interaction.response.send_message(
            f"✅ Created: `/{prefix}/{slug}` → <{url}>", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ Slug `/{prefix}/{slug}` already exists. Use `/edit_link` to update it.", ephemeral=True
        )


@app_commands.command(name="edit_link", description="Update the destination URL of an existing short link.")
@app_commands.describe(slug="The slug to update", url="New destination URL", prefix="Prefix (default: p)")
async def edit_link_slash(interaction: discord.Interaction, slug: str, url: str, prefix: str = "p") -> None:
    slug = slug.lower().strip()
    prefix = prefix.lower().strip()
    err = _check_link_permission(interaction, prefix, url)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    from shortener import update_link, get_link
    old = get_link(slug, prefix)
    old_url = old["url"] if old else ""
    ok = update_link(slug, url, prefix)
    if ok:
        _audit_link_change("update", interaction.user.id, str(interaction.user), prefix, slug, url, old_url)
        await interaction.response.send_message(f"✅ Updated `/{prefix}/{slug}` → <{url}>", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Link `/{prefix}/{slug}` not found.", ephemeral=True)


@app_commands.command(name="delete_link", description="Delete a short link.")
@app_commands.describe(slug="The slug to delete", prefix="Prefix (default: p)")
async def delete_link_slash(interaction: discord.Interaction, slug: str, prefix: str = "p") -> None:
    slug = slug.lower().strip()
    prefix = prefix.lower().strip()
    err = _check_link_permission(interaction, prefix)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    from shortener import delete_link, get_link
    old = get_link(slug, prefix)
    old_url = old["url"] if old else ""
    ok = delete_link(slug, prefix)
    if ok:
        _audit_link_change("delete", interaction.user.id, str(interaction.user), prefix, slug, "", old_url)
        await interaction.response.send_message(f"🗑️ Deleted `/{prefix}/{slug}`.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Link `/{prefix}/{slug}` not found.", ephemeral=True)


@app_commands.command(name="list_links", description="List all short links.")
async def list_links_slash(interaction: discord.Interaction) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    from shortener import list_links
    links = list_links()
    if not links:
        await interaction.response.send_message("No links yet.", ephemeral=True)
        return
    lines = ["**🔗 All Short Links:**"]
    for lnk in links:
        lines.append(f"  `{_fmt_link(lnk['prefix'], lnk['slug'])}` → {lnk['url']}")
    text = "\n".join(lines)
    # Discord message limit
    if len(text) > 1900:
        text = text[:1900] + "\n…(truncated)"
    await interaction.response.send_message(text, ephemeral=True)


@app_commands.command(name="link_stats", description="Show click analytics for a short link.")
@app_commands.describe(slug="The slug to check", prefix="Prefix (default: p)", days="Days to look back (default 30)")
async def link_stats_slash(interaction: discord.Interaction, slug: str, prefix: str = "p", days: int = 30) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    from shortener import get_stats
    stats = get_stats(slug.lower(), prefix.lower(), days)
    if not stats:
        await interaction.followup.send(f"❌ Link `/{prefix}/{slug}` not found.", ephemeral=True)
        return
    lines = [
        f"**📊 `{_fmt_link(prefix, slug)}`** — last {days} days",
        f"🔗 → {stats['link']['url']}",
        f"👆 Total clicks: **{stats['total']}**",
    ]
    if stats["by_country"]:
        lines.append("\n**🌍 By Country:**")
        for c in stats["by_country"]:
            lines.append(f"  {c['country_code']} {c['country']} — {c['cnt']}")
    if stats["by_referrer"]:
        lines.append("\n**🔀 By Referrer:**")
        for r in stats["by_referrer"]:
            lines.append(f"  {r['referrer']} — {r['cnt']}")
    if stats["daily"]:
        lines.append("\n**📅 Last 7 days:**")
        for d in stats["daily"]:
            lines.append(f"  {d['day']} — {d['cnt']} clicks")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@app_commands.command(name="top_links", description="Show the most clicked short links.")
@app_commands.describe(days="Days to look back (default 7)", limit="Number of links to show (default 5)")
async def top_links_slash(interaction: discord.Interaction, days: int = 7, limit: int = 5) -> None:
    roles = [r.name for r in getattr(interaction.user, "roles", [])]
    if "LocoDev" not in roles:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    from shortener import get_top_links
    links = get_top_links(days, limit)
    if not links:
        await interaction.followup.send("No clicks recorded yet.", ephemeral=True)
        return
    lines = [f"**🏆 Top {limit} Links — last {days} days**"]
    for i, lnk in enumerate(links, 1):
        lines.append(f"{i}. `{_fmt_link(lnk['prefix'], lnk['slug'])}` — **{lnk['clicks']} clicks**")
        lines.append(f"   → {lnk['url']}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


# ── New-merch email watcher helpers ───────────────────────────────────────────

def _load_merch_seen() -> set[str]:
    try:
        with open(_MERCH_SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_merch_seen(seen: set[str]) -> None:
    try:
        _atomic_write_json(_MERCH_SEEN_PATH, list(seen))
    except Exception as exc:
        logger.warning("Could not save merch-seen file: %s", exc)


def _email_matches_merch(frm: str, subj: str) -> bool:
    """True only if the email is from an expected sender AND its subject looks
    like a merch drop — keeps the watcher from reposting unrelated mail."""
    frm_l, subj_l = (frm or "").lower(), (subj or "").lower()
    from_ok = (not MERCH_EMAIL_FROM_FILTER) or any(f in frm_l for f in MERCH_EMAIL_FROM_FILTER)
    subj_ok = (not MERCH_EMAIL_SUBJECT_FILTER) or any(k in subj_l for k in MERCH_EMAIL_SUBJECT_FILTER)
    return from_ok and subj_ok


def _extract_email_text(msg) -> str:
    """Return a cleaned plain-text body from an email.message.Message."""
    body = ""
    try:
        if msg.is_multipart():
            # Prefer text/plain; fall back to stripping the HTML part.
            plain = html = ""
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition", ""))
                if "attachment" in disp:
                    continue
                try:
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                except Exception:
                    continue
                if ctype == "text/plain" and not plain:
                    plain = text
                elif ctype == "text/html" and not html:
                    html = text
            body = plain or html
        else:
            payload = msg.get_payload(decode=True)
            if payload is not None:
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
    except Exception:
        body = ""
    # If it's HTML, strip tags to text.
    if body and ("<html" in body.lower() or "<body" in body.lower() or "<div" in body.lower()):
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            body = soup.get_text(separator="\n", strip=True)
        except Exception:
            body = re.sub(r"<[^>]+>", " ", body)
    lines = [l.strip() for l in (body or "").splitlines() if l.strip()]
    return "\n".join(lines)


def _fetch_merch_emails() -> list[dict]:
    """Blocking IMAP fetch (run in an executor). Returns recent emails that match
    the merch filters as dicts: {id, from, subject, date, body}."""
    import imaplib
    import email as _email
    from email.header import decode_header, make_header

    results: list[dict] = []
    M = None
    try:
        M = imaplib.IMAP4_SSL(MERCH_EMAIL_HOST, MERCH_EMAIL_PORT)
        M.login(MERCH_EMAIL_USER, MERCH_EMAIL_PASSWORD)
        M.select(MERCH_EMAIL_MAILBOX, readonly=True)
        # Bound the scan to the last few days and the most recent messages.
        since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%d-%b-%Y")
        typ, data = M.search(None, f'(SINCE {since})')
        if typ != "OK" or not data or not data[0]:
            return results
        ids = data[0].split()
        for num in ids[-50:]:
            typ, msg_data = M.fetch(num, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = _email.message_from_bytes(msg_data[0][1])
            try:
                frm = str(make_header(decode_header(msg.get("From", ""))))
                subj = str(make_header(decode_header(msg.get("Subject", ""))))
            except Exception:
                frm, subj = msg.get("From", ""), msg.get("Subject", "")
            if not _email_matches_merch(frm, subj):
                continue
            mid = msg.get("Message-ID", "").strip() or f"{frm}|{subj}|{msg.get('Date', '')}"
            results.append({
                "id": mid,
                "from": frm,
                "subject": subj,
                "date": msg.get("Date", ""),
                "body": _extract_email_text(msg),
            })
    finally:
        if M is not None:
            try:
                M.logout()
            except Exception:
                pass
    return results


# Words that mark a line as a merch ITEM (vs a patron name) in the recipient list.
_MERCH_ITEM_HINTS = (
    "mug", "shirt", "tee", "t-shirt", "hoodie", "sweatshirt", "sweater", "crewneck",
    "long sleeve", "sticker", "poster", "hat", "cap", "beanie", "tote", "bag",
    "pin", "socks", "exclusive", "premium", "merch",
)
# Lines that mark the START of the recipient list (list begins after them).
_MERCH_LIST_START = ("subscribed long enough", "will receive your merch", "on its way to", "on their way")
# Lines that mark the END of the recipient list (footer / boilerplate).
_MERCH_LIST_END = (
    "see the charges", "charges for this merch", "contact us", "get the patreon app",
    "download on the", "get it on google", "manage your email", "this email was sent",
    "patreon wordmark", "townsend street",
)


def _looks_like_merch_item(s: str) -> bool:
    sl = (s or "").lower()
    return any(h in sl for h in _MERCH_ITEM_HINTS)


def _plausible_patron_name(s: str) -> bool:
    """Heuristic: a short, name-like line (not a URL, email, or sentence)."""
    if not s or len(s) > 48:
        return False
    sl = s.lower()
    if "http" in sl or "@" in s or "://" in s:
        return False
    if len(s.split()) > 5:
        return False
    if s.rstrip().endswith((".", "!", ":", "?", ",")):
        return False
    return any(c.isalpha() for c in s)


def _parse_merch_recipients(body: str) -> list[dict]:
    """From a 'N members will receive your merch' email, extract the list of
    {name, item} pairs. Tolerant of extra lines and HTML-stripped layout."""
    lines = [l.strip() for l in (body or "").splitlines() if l.strip()]
    start = 0
    for i, l in enumerate(lines):
        ll = l.lower()
        if any(k in ll for k in _MERCH_LIST_START):
            start = i + 1
    end = len(lines)
    for i in range(start, len(lines)):
        ll = lines[i].lower()
        if any(k in ll for k in _MERCH_LIST_END):
            end = i
            break
    region = lines[start:end]
    pairs: list[dict] = []
    i = 0
    while i < len(region):
        name = region[i]
        item = region[i + 1] if i + 1 < len(region) else ""
        if _plausible_patron_name(name) and _looks_like_merch_item(item):
            pairs.append({"name": name, "item": item})
            i += 2
        else:
            i += 1
    return pairs


def _parse_merch_count(body: str, subject: str) -> int | None:
    mo = re.search(r"(\d+)\s+members?", f"{subject or ''} {body or ''}")
    return int(mo.group(1)) if mo else None


@app_commands.command(name="test_merch", description="(Owner) Post the most recent Patreon merch email now — tests the watcher.")
async def test_merch_slash(interaction: discord.Interaction) -> None:
    if not (OWNER_DISCORD_ID and interaction.user.id == OWNER_DISCORD_ID):
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    if not (MERCH_EMAIL_HOST and MERCH_EMAIL_USER and MERCH_EMAIL_PASSWORD):
        await interaction.response.send_message(
            "Merch watcher isn't configured — set MERCH_EMAIL_HOST / MERCH_EMAIL_USER / MERCH_EMAIL_PASSWORD in Railway.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        loop = asyncio.get_event_loop()
        msgs = await loop.run_in_executor(None, _fetch_merch_emails)
    except Exception as exc:
        await interaction.followup.send(f"❌ IMAP connection/login failed: `{exc}`", ephemeral=True)
        return
    if not msgs:
        await interaction.followup.send(
            "✅ Connected to the mailbox, but found **no merch-matching emails** in the last 3 days.\n"
            "If you expected one, check `MERCH_EMAIL_FROM_FILTER` / `MERCH_EMAIL_SUBJECT_FILTER`.",
            ephemeral=True,
        )
        return
    latest = msgs[-1]  # most recent matching email
    try:
        await interaction.client._post_merch_alert(latest)
    except Exception as exc:
        await interaction.followup.send(f"Fetched the email but posting failed: `{exc}`", ephemeral=True)
        return
    await interaction.followup.send(
        f"✅ Posted the most recent merch email to <#{MERCH_ALERT_CHANNEL_ID}>:\n**{latest.get('subject','')}**",
        ephemeral=True,
    )


class FeedbackBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        intents.members = True
        # Default to suppressing ALL mentions the bot emits. The bot echoes
        # user-controlled content (message mirrors, nickname/username changes,
        # AI replies, RSS titles); without this, a member could launder an
        # @everyone / role ping through the bot, which Discord would resolve
        # with the bot's permissions. Opt back in explicitly where a real ping
        # is intended.
        super().__init__(
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.tree = app_commands.CommandTree(self)
        self.synced = False
        self._status_task: asyncio.Task | None = None
        self._daily_task: asyncio.Task | None = None
        self._weekly_task: asyncio.Task | None = None
        self._youtube_task: asyncio.Task | None = None
        self._merch_task: asyncio.Task | None = None
        self._ue_seen_video_ids: set[str] = set()
        self._conversation_history: dict[int, list[dict]] = {}
        self._processed_messages: set[int] = set()
        # Per-user last-AI-call time (monotonic) for the AI-path cooldown
        self._ai_last_call: dict[int, float] = {}
        # Spam detection: user_id → deque of (datetime, channel_id, Message, is_image_only)
        self._spam_tracker: dict[int, collections.deque] = {}
        # Users already actioned this session (avoid double-kick)
        self._spam_actioned: set[int] = set()
        # Proactive KB auto-reply state
        self._kb_auto_replied: set[int] = set()                                # message IDs already answered
        self._kb_auto_cooldown: dict[tuple[int, int], float] = {}             # (user_id, channel_id) → timestamp
        # Unanswered-question escalation: question message IDs with a pending check
        self._unanswered_scheduled: set[int] = set()

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

                # 2. Live server member count
                if GUILD_ID:
                    guild = self.get_guild(int(GUILD_ID))
                    if guild:
                        statuses.append(discord.Activity(type=discord.ActivityType.watching, name=f"{guild.member_count} devs 🎮"))

                # 3. Fixed statuses
                statuses.append(discord.Activity(type=discord.ActivityType.listening, name="LocoDev"))
                statuses.append(discord.Activity(type=discord.ActivityType.watching, name="UE5 Devs build"))
                statuses.append(discord.Game(name="Unreal Engine 5"))

                # 4. Fixed "Ask me anything! :)"
                ask_phrase = "Ask me anything! :)"
                statuses.append(discord.Activity(type=discord.ActivityType.listening, name=ask_phrase))

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

                def _dedup_d(items):
                    _seen = set()
                    _out = []
                    for _e in items:
                        _k = (_e.get("name"), _e.get("member_id"))
                        if _k in _seen:
                            continue
                        _seen.add(_k)
                        _out.append(_e)
                    return _out

                joined = _dedup_d(joined)
                cancels = _dedup_d(cancels)

                lines = ["📊 **Daily Patreon Summary** (last 24h)\n"]
                if joined:
                    lines.append(f"💎 **{len(joined)}** new paid subscriber(s):")
                    for e in joined:
                        tier = f" ({e['tier']})" if e.get("tier") else ""
                        lines.append(f"  • **{e['name']}**{tier} — ${e['amount']:.2f}/mo")
                if cancels:
                    lines.append(f"❌ **{len(cancels)}** cancellation(s):")
                    for e in cancels:
                        tier = f" ({e.get('tier')})" if e.get("tier") else ""
                        _ts = e.get("ts", "")[:16].replace("T", " ")
                        lines.append(f"  • **{e['name']}**{tier} — {_ts} UTC")

                if len(lines) == 1:
                    await channel.send("📊 **Daily Patreon Summary** — No new subscribers or cancellations in the last 24h.")
                else:
                    net = len(joined) - len(cancels)
                    lines.append(f"\n**Net change: {net:+d}**")
                    await _send_chunked(channel, lines)

                # Click report
                try:
                    loop = asyncio.get_event_loop()
                    click_embed = await loop.run_in_executor(None, _build_click_report_embed)
                    await channel.send(embed=click_embed)
                except Exception as ce:
                    logger.warning("Scheduled click report error: %s", ce)

            except Exception as exc:
                logger.warning("Daily summary error: %s", exc)
                await asyncio.sleep(60)

    async def _watch_unreal_engine_youtube(self) -> None:
        """Poll Unreal Engine YouTube RSS feed every 30 minutes and post new videos."""
        import json as _json
        import xml.etree.ElementTree as ET
        from urllib import request as _req
        _UE_SEEN_PATH = "/app/data/ue_seen_videos.json"

        def _load_seen() -> set:
            try:
                with open(_UE_SEEN_PATH) as f:
                    return set(_json.load(f))
            except Exception:
                return set()

        def _save_seen(ids: set):
            try:
                os.makedirs(os.path.dirname(_UE_SEEN_PATH), exist_ok=True)
                with open(_UE_SEEN_PATH, "w") as f:
                    _json.dump(list(ids), f)
            except Exception as exc:
                logger.warning("ue_seen save error: %s", exc)

        await self.wait_until_ready()
        RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id=UCBobmJyzsJ6Ll7UbfhI4iwQ"

        # Load persisted seen IDs so restarts don't re-seed all videos
        self._ue_seen_video_ids = _load_seen()
        logger.info("YouTube watcher started, %d seen video IDs loaded", len(self._ue_seen_video_ids))

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

                if not self._ue_seen_video_ids:
                    # First ever run with no persisted data — seed without announcing
                    for entry in entries:
                        vid = entry.findtext("yt:videoId", namespaces=ns)
                        if vid:
                            self._ue_seen_video_ids.add(vid)
                    _save_seen(self._ue_seen_video_ids)
                    logger.info("YouTube watcher: seeded %d videos on first run", len(self._ue_seen_video_ids))
                else:
                    new_found = False
                    for entry in entries:
                        vid = entry.findtext("yt:videoId", namespaces=ns)
                        if not vid or vid in self._ue_seen_video_ids:
                            continue
                        t = entry.findtext("atom:title", namespaces=ns, default="New video")
                        l_el = entry.find("atom:link", ns)
                        u = l_el.get("href", "") if l_el is not None else f"https://www.youtube.com/watch?v={vid}"
                        channel = self.get_channel(YOUTUBE_NOTIFY_CHANNEL_ID) or await self.fetch_channel(YOUTUBE_NOTIFY_CHANNEL_ID)
                        await channel.send(
                            f"🎮 **Unreal Engine** just posted a new video!\n**{t}**\n{u}"
                        )
                        self._ue_seen_video_ids.add(vid)
                        new_found = True
                        logger.info("YouTube watcher: posted new video %s (%s)", vid, t)
                    if new_found:
                        _save_seen(self._ue_seen_video_ids)
            except Exception as exc:
                logger.warning("YouTube watcher error: %s", exc)
            await asyncio.sleep(1800)  # check every 30 minutes

    async def _watch_merch_email(self) -> None:
        """Poll a mailbox for Patreon 'new merch' emails and repost them to the
        merch alert channel. Disabled unless MERCH_EMAIL_HOST/USER/PASSWORD are set.

        Mirrors the YouTube watcher: on the very first run (no persisted state) it
        seeds the existing inbox silently so a fresh deploy doesn't dump old mail,
        then announces only genuinely new matching emails.
        """
        if not (MERCH_EMAIL_HOST and MERCH_EMAIL_USER and MERCH_EMAIL_PASSWORD):
            logger.info("Merch email watcher disabled (MERCH_EMAIL_* not configured)")
            return
        await self.wait_until_ready()
        seen = _load_merch_seen()
        first_run = not seen
        logger.info("Merch email watcher started (%d seen ids, first_run=%s)", len(seen), first_run)

        while not self.is_closed():
            try:
                loop = asyncio.get_event_loop()
                msgs = await loop.run_in_executor(None, _fetch_merch_emails)
                new_msgs = [m for m in msgs if m.get("id") and m["id"] not in seen]
                for m in new_msgs:
                    seen.add(m["id"])
                # Bound the persisted set.
                if len(seen) > 2000:
                    seen = set(list(seen)[-2000:])

                if first_run:
                    # Seed silently — don't announce mail that predates the watcher.
                    _save_merch_seen(seen)
                    first_run = False
                    logger.info("Merch watcher: seeded %d existing emails on first run", len(new_msgs))
                elif new_msgs:
                    for m in new_msgs:
                        try:
                            await self._post_merch_alert(m)
                        except Exception as _pe:
                            logger.warning("Failed to post merch alert: %s", _pe)
                    _save_merch_seen(seen)
            except Exception as exc:
                logger.warning("Merch email watcher error: %s", exc)
            await asyncio.sleep(MERCH_EMAIL_POLL_SECS)

    def _find_member_by_name(self, name: str):
        """Best-effort match of a Patreon display name to a guild member so we can
        @mention them. Returns the member or None. Conservative to avoid mis-pings:
        requires a full-name substring match, or all name tokens present."""
        try:
            guild = self.get_guild(int(GUILD_ID)) if GUILD_ID else None
        except Exception:
            guild = None
        if not guild or not name:
            return None
        n = name.strip().lower()
        tokens = [t for t in n.split() if len(t) >= 2]
        for member in guild.members:
            hay = " ".join(filter(None, [
                member.name,
                getattr(member, "display_name", "") or "",
                getattr(member, "global_name", "") or "",
            ])).lower()
            if n and n in hay:
                return member
            if len(tokens) >= 2 and all(t in hay for t in tokens):
                return member
        return None

    async def _post_merch_alert(self, m: dict) -> None:
        """Format and post a single 'members will receive your merch' email to the
        merch alert channel, @mentioning each patron we can resolve to a member."""
        try:
            channel = self.get_channel(MERCH_ALERT_CHANNEL_ID) or await self.fetch_channel(MERCH_ALERT_CHANNEL_ID)
        except Exception as _ce:
            logger.warning("Merch alert channel %s unavailable: %s", MERCH_ALERT_CHANNEL_ID, _ce)
            return

        subject = (m.get("subject") or "New merch").strip()
        recipients = _parse_merch_recipients(m.get("body", ""))
        resolved: list = []

        if recipients:
            count = _parse_merch_count(m.get("body", ""), subject) or len(recipients)
            lines = [f"🛍️ **{count} member{'s' if count != 1 else ''} earned LocoDev merch!** 🎉"]
            for r in recipients:
                member = self._find_member_by_name(r["name"])
                if member:
                    resolved.append(member)
                who = member.mention if member else f"**{r['name']}**"
                lines.append(f"🎁 {who} — {r['item']}")
            lines.append("_Orders are printing now — shipping in the next 1–2 weeks._")
            if MERCH_INFO_URL:
                lines.append(f"\nWanna know how to earn your merch? 👉 {MERCH_INFO_URL}")
            text = "\n".join(lines)[:1900]
        else:
            # Unknown/changed format — don't silently drop it; post the gist.
            snippet = re.sub(r"\n{3,}", "\n\n", (m.get("body") or "").strip())[:600]
            text = "\n".join([f"🛍️ **{subject}**", snippet]).strip()[:1900]

        # The email body is untrusted: only the patrons we actually resolved may be
        # pinged — @everyone/@here/roles are always suppressed.
        allowed = discord.AllowedMentions(everyone=False, roles=False,
                                          users=resolved if resolved else False)
        await channel.send(text, allowed_mentions=allowed)
        logger.info("Posted merch alert: %s (%d recipients, %d mentioned)",
                    subject[:60], len(recipients), len(resolved))

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

                # Pull live data from Patreon API for the past 7 days
                loop = asyncio.get_event_loop()
                activity = await loop.run_in_executor(None, lambda: _fetch_patreon_daily_activity(days=7))
                paid_subs = activity["joined"]

                # Cancellations from local event log (API doesn't expose these easily)
                events_log = [e for e in _load_events() if e.get("ts", "") >= cutoff_7d]
                free_joins = [e for e in events_log if e["event"] == "members:create"]
                cancels = [e for e in events_log if e["event"] in ("members:pledge:delete", "members:delete")]
                _weekly_events.clear()

                def _dedup_wb(items):
                    _seen = set()
                    _out = []
                    for _e in items:
                        _k = (_e.get("name"), _e.get("member_id"))
                        if _k in _seen:
                            continue
                        _seen.add(_k)
                        _out.append(_e)
                    return _out

                paid_subs = _dedup_wb(paid_subs)
                free_joins = _dedup_wb(free_joins)
                cancels = _dedup_wb(cancels)

                channel = self.get_channel(PATREON_ANNOUNCEMENT_CHANNEL_ID) or await self.fetch_channel(PATREON_ANNOUNCEMENT_CHANNEL_ID)

                total_new = len(paid_subs) + len(free_joins)
                total_cancel = len(cancels)

                if total_new == 0 and total_cancel == 0:
                    await channel.send("📅 **Weekly Patreon Summary** — No activity this week.")
                    continue

                lines = ["📅 **Weekly Patreon Summary**\n"]

                if paid_subs:
                    lines.append(f"💎 **{len(paid_subs)}** new paid subscriber(s):")
                    for e in paid_subs:
                        tier = f" ({e['tier']})" if e.get("tier") else ""
                        lines.append(f"  • **{e['name']}**{tier} — ${e['amount']:.2f}/mo")

                if free_joins:
                    lines.append(f"👋 **{len(free_joins)}** new free member(s):")
                    for e in free_joins:
                        _ts = e.get("ts", "")[:16].replace("T", " ")
                        lines.append(f"  • **{e['name']}** — {_ts} UTC")

                if cancels:
                    lines.append(f"❌ **{len(cancels)}** cancellation(s):")
                    for e in cancels:
                        _ts = e.get("ts", "")[:16].replace("T", " ")
                        lines.append(f"  • **{e['name']}** — {_ts} UTC")

                lines.append(f"\n**Net change this week: {total_new - total_cancel:+d}**")
                await channel.send("\n".join(lines))

            except Exception as exc:
                logger.warning("Weekly summary error: %s", exc)
                await asyncio.sleep(60)

    async def setup_hook(self) -> None:
        self.tree.add_command(report_command_slash)
        self.tree.add_command(check_patron_slash)
        self.tree.add_command(fix_roles_slash)
        self.tree.add_command(top_patrons_slash)
        self.tree.add_command(recent_posts_slash)
        self.tree.add_command(meta_conversion_slash)
        self.tree.add_command(test_reports_slash)
        self.tree.add_command(test_pushover_slash)
        self.tree.add_command(test_merch_slash)
        self.tree.add_command(kb_scan_slash)
        self.tree.add_command(trial_stats_slash)
        self.tree.add_command(shorten_slash)
        self.tree.add_command(edit_link_slash)
        self.tree.add_command(delete_link_slash)
        self.tree.add_command(list_links_slash)
        self.tree.add_command(link_stats_slash)
        self.tree.add_command(top_links_slash)

    async def on_ready(self) -> None:
        if not self.synced:
            # Clear global commands to remove duplicates
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            # Re-add commands and sync to guild
            self.tree.add_command(report_command_slash)
            self.tree.add_command(check_patron_slash)
            self.tree.add_command(fix_roles_slash)
            self.tree.add_command(top_patrons_slash)
            self.tree.add_command(recent_posts_slash)
            self.tree.add_command(meta_conversion_slash)
            self.tree.add_command(test_reports_slash)
            self.tree.add_command(test_pushover_slash)
            self.tree.add_command(test_merch_slash)
            self.tree.add_command(kb_scan_slash)
            self.tree.add_command(trial_stats_slash)
            self.tree.add_command(shorten_slash)
            self.tree.add_command(edit_link_slash)
            self.tree.add_command(delete_link_slash)
            self.tree.add_command(list_links_slash)
            self.tree.add_command(link_stats_slash)
            self.tree.add_command(top_links_slash)
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
        if self._merch_task is None or self._merch_task.done():
            self._merch_task = asyncio.create_task(self._watch_merch_email())
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

    def _reactor_is_staff(self, payload: discord.RawReactionActionEvent) -> bool:
        """True if the reacting user is the server owner or has the LocoDev role."""
        if OWNER_DISCORD_ID and payload.user_id == OWNER_DISCORD_ID:
            return True
        member = payload.member  # populated for guild reaction-add events
        if member is None:
            return False
        try:
            return any(r.name == "LocoDev" for r in getattr(member, "roles", []))
        except Exception:
            return False

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Save a Q&A to the knowledge base when ✅ is added to an answer.

        Works in the dedicated support channels and in project forum threads.
        The approved message can be a human reply OR one of the bot's own
        answers — approving a bot answer lets the KB grow automatically from
        good AI/FAQ replies. To prevent KB poisoning, only a staff member
        (server owner or LocoDev role) may approve the bot's own answers.
        """
        if str(payload.emoji) != _KB_APPROVE_EMOJI:
            return
        in_kb_channel = payload.channel_id in KB_CHANNEL_IDS
        channel = self.get_channel(payload.channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(payload.channel_id)
            except Exception:
                return
        in_project_thread = bool(
            PROJECTS_FORUM_CHANNEL_ID
            and isinstance(channel, discord.Thread)
            and str(getattr(channel, "parent_id", None)) == PROJECTS_FORUM_CHANNEL_ID
        )
        if not (in_kb_channel or in_project_thread):
            return
        try:
            answer_msg = await channel.fetch_message(payload.message_id)
            # The answer must be a reply to a question
            if not answer_msg.reference:
                return

            is_bot_answer = bool(self.user) and answer_msg.author.id == self.user.id
            # Only staff (server owner or LocoDev) may curate ANY answer into the
            # KB. Human replies must be staff-approved too — otherwise any member
            # could ✅ their own message and inject arbitrary text that is later
            # served to users and fed into the AI system prompt (stored prompt
            # injection / KB poisoning).
            if not self._reactor_is_staff(payload):
                return

            question_msg = await channel.fetch_message(answer_msg.reference.message_id)
            question = question_msg.content.strip()
            answer = answer_msg.content.strip()
            # Strip the bot's own FAQ prefix so the stored answer is clean
            if is_bot_answer:
                _faq_prefix = "📚 **From our FAQ:**"
                if answer.startswith(_faq_prefix):
                    answer = answer[len(_faq_prefix):].lstrip("\n").strip()
            # Store only the ANSWER message's images. The asker's own question
            # screenshots are usually irrelevant to resurface on a later question.
            images = [
                a.url for a in answer_msg.attachments
                if a.content_type and a.content_type.startswith("image/")
            ]
            if question and answer:
                author_label = "LocoBOT (approved)" if is_bot_answer else answer_msg.author.display_name
                _kb_add(question, answer, author_label, images=images or None)
                await answer_msg.add_reaction("📚")  # confirm saved
        except Exception as _ke:
            logger.warning("KB reaction handler error: %s", _ke)

    async def _mirror_dest(self):
        """Return the mirror destination channel, or None."""
        return self.get_channel(MIRROR_DEST_CHANNEL_ID) if MIRROR_DEST_CHANNEL_ID else None

    async def on_message_delete(self, message: discord.Message) -> None:
        if message.channel.id != MIRROR_SOURCE_CHANNEL_ID:
            return
        dest = await self._mirror_dest()
        if not dest:
            return
        try:
            ts = discord.utils.format_dt(message.created_at, style="f")
            author_tag = f"{message.author.mention} ({message.author} — ID: {message.author.id})"
            content = message.content or "*(no text)*"
            lines = [
                f"🗑️ **MESSAGE DELETED**",
                f"**Author:** {author_tag}",
                f"**Originally sent:** {ts}",
                f"**Content:**\n{content}",
            ]
            if message.attachments:
                att_list = "\n".join(f"  • {a.filename}" for a in message.attachments)
                lines.append(f"**Attachments (files lost):**\n{att_list}")
            await dest.send("\n".join(lines))
        except Exception as _de:
            logger.warning("Mirror delete error: %s", _de)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """Fallback for deletions where the message wasn't cached."""
        if payload.channel_id != MIRROR_SOURCE_CHANNEL_ID:
            return
        if payload.cached_message is not None:
            return  # already handled by on_message_delete
        dest = await self._mirror_dest()
        if not dest:
            return
        try:
            await dest.send(
                f"🗑️ **MESSAGE DELETED** (content unknown — message was not in cache)\n"
                f"**Message ID:** {payload.message_id}"
            )
        except Exception as _rde:
            logger.warning("Mirror raw-delete error: %s", _rde)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.channel.id != MIRROR_SOURCE_CHANNEL_ID:
            return
        if before.content == after.content:
            return  # embed/pin update, not a text edit
        dest = await self._mirror_dest()
        if not dest:
            return
        try:
            ts = discord.utils.format_dt(after.edited_at or after.created_at, style="f")
            author_tag = f"{before.author.mention} ({before.author} — ID: {before.author.id})"
            before_text = before.content or "*(no text)*"
            after_text = after.content or "*(no text)*"
            await dest.send(
                f"✏️ **MESSAGE EDITED**\n"
                f"**Author:** {author_tag}\n"
                f"**Edited at:** {ts}\n"
                f"**Jump:** {after.jump_url}\n"
                f"**Before:**\n{before_text}\n"
                f"**After:**\n{after_text}"
            )
        except Exception as _ee:
            logger.warning("Mirror edit error: %s", _ee)

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Flag server nickname changes."""
        if before.nick == after.nick:
            return
        dest = await self._mirror_dest()
        if not dest:
            return
        try:
            old_nick = before.nick or "*(none)*"
            new_nick = after.nick or "*(removed)*"
            await dest.send(
                f"📝 **NICKNAME CHANGED**\n"
                f"**User:** {after.mention} ({after} — ID: {after.id})\n"
                f"**Before:** {old_nick}\n"
                f"**After:** {new_nick}"
            )
        except Exception as _nce:
            logger.warning("Mirror nickname error: %s", _nce)

    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        """Flag global Discord username changes."""
        if before.name == after.name and before.display_name == after.display_name:
            return
        dest = await self._mirror_dest()
        if not dest:
            return
        try:
            lines = [f"👤 **USERNAME CHANGED**", f"**User:** {after.mention} (ID: {after.id})"]
            if before.name != after.name:
                lines.append(f"**Username before:** {before.name}")
                lines.append(f"**Username after:** {after.name}")
            if before.display_name != after.display_name:
                lines.append(f"**Display name before:** {before.display_name}")
                lines.append(f"**Display name after:** {after.display_name}")
            await dest.send("\n".join(lines))
        except Exception as _uce:
            logger.warning("Mirror username error: %s", _uce)

    # ── Spam detection ────────────────────────────────────────────────────────

    async def _check_invite_link(self, message: discord.Message) -> bool:
        """Delete unsolicited Discord invite links and timeout the sender.

        Returns True if the message was actioned so the caller can skip
        further processing.  Staff (admins, server owner, LocoDev role) are
        always exempt.
        """
        import re as _re
        if not message.guild:
            return False
        member = message.author
        if not isinstance(member, discord.Member):
            return False
        if member.guild_permissions.administrator or member.id == message.guild.owner_id:
            return False
        if any(r.name == "LocoDev" for r in getattr(member, "roles", [])):
            return False

        # Normalize so simple obfuscation (spaces, zero-width chars, "dot"/"[.]"
        # tricks) can't slip an invite past the regex.
        import unicodedata as _ud
        text = _ud.normalize("NFKC", message.content or "")
        # Strip whitespace + zero-width / bidi control chars used to break the URL up.
        _norm = re.sub("[\\s\u200b-\u200f\u202a-\u202e\u2060\ufeff]+", "", text.lower())
        _norm = _norm.replace("[.]", ".").replace("(.)", ".").replace("(dot)", ".").replace("[dot]", ".").replace(" dot ", ".")
        # Catch discord.gg/xxx, discord.com/invite/xxx and common alt invite hosts.
        _invite_re = re.compile(
            r"(?:https?://)?(?:www\.)?("
            r"discord(?:\.gg|(?:app)?\.com/invite)"
            r"|discord\.me|dsc\.gg|invite\.gg|disboard\.org/server/join"
            r")/[\w-]+",
            re.IGNORECASE,
        )
        if not (_invite_re.search(text) or _invite_re.search(_norm)):
            return False

        # Delete the message immediately
        try:
            await message.delete()
        except Exception as _de:
            logger.warning("Invite-link delete failed: %s", _de)

        # Timeout for 10 minutes so the user can't immediately re-post
        timed_out = False
        try:
            from datetime import timedelta as _td, timezone as _tz
            until = datetime.now(_tz.utc) + _td(minutes=10)
            await member.timeout(until, reason="Auto-mod: posted an unsolicited server invite link")
            timed_out = True
        except Exception as _te:
            logger.warning("Invite-link timeout failed for %s: %s", member, _te)

        # Log to mirror/backup channel
        log_ch = await self._mirror_dest()
        if log_ch:
            try:
                invite_url = _invite_re.search(text).group(0)
                lines = [
                    "🔗 **INVITE LINK REMOVED**",
                    f"**User:** {member.mention} (**{member}** — ID: `{member.id}`)",
                    f"**Channel:** {message.channel.mention}",
                    f"**Link:** `{invite_url}`",
                    f"**Timed out 10 min:** {'✅ Yes' if timed_out else '❌ Failed — check bot permissions'}",
                    f"**Original message:** {text[:400]}",
                ]
                await log_ch.send("\n".join(lines))
            except Exception as _le:
                logger.warning("Invite-link log error: %s", _le)

        logger.info("Invite link removed from %s in #%s — timed_out=%s", member, message.channel, timed_out)
        return True

    async def _check_spam(self, message: discord.Message) -> bool:
        """Track message; return True and take action if spam is detected."""
        if not message.guild:
            return False
        member = message.author
        if not isinstance(member, discord.Member):
            return False
        # Never action admins or the server owner
        if member.guild_permissions.administrator or member.id == message.guild.owner_id:
            return False

        uid = member.id
        now = datetime.now(timezone.utc)
        is_image_only = bool(message.attachments) and not message.content.strip()

        deque = self._spam_tracker.setdefault(uid, collections.deque())
        deque.append((now, message.channel.id, message, is_image_only))

        # Drop entries older than the longest window we care about
        max_window = max(SPAM_IMAGE_WINDOW, SPAM_MSG_WINDOW)
        while deque and (now - deque[0][0]).total_seconds() > max_window:
            deque.popleft()

        # Periodically sweep the whole tracker so deques (and the Message objects
        # they retain) for one-time posters don't accumulate over long uptime.
        if len(self._spam_tracker) > 200:
            for _uid in [u for u, dq in self._spam_tracker.items()
                         if not dq or (now - dq[-1][0]).total_seconds() > max_window]:
                if _uid != uid:
                    self._spam_tracker.pop(_uid, None)
        # Bound the actioned set so it can't grow without limit.
        if len(self._spam_actioned) > 1000:
            self._spam_actioned.clear()

        if uid in self._spam_actioned:
            # Already kicked — just silently delete any new messages they sneak in
            try:
                await message.delete()
            except Exception:
                pass
            return True

        recent = list(deque)

        # Image-only flood check
        img_recent = [e for e in recent if e[3] and (now - e[0]).total_seconds() <= SPAM_IMAGE_WINDOW]
        img_channels = len({e[1] for e in img_recent})

        # General cross-channel flood check
        msg_recent = [e for e in recent if (now - e[0]).total_seconds() <= SPAM_MSG_WINDOW]
        msg_channels = len({e[1] for e in msg_recent})

        is_spam = (
            (len(img_recent) >= SPAM_IMAGE_COUNT and img_channels >= SPAM_IMAGE_CHANNELS) or
            (len(msg_recent) >= SPAM_MSG_COUNT and msg_channels >= SPAM_MSG_CHANNELS)
        )
        if not is_spam:
            return False

        self._spam_actioned.add(uid)
        await self._punish_spammer(member, recent)
        return True

    async def _punish_spammer(self, member: discord.Member, entries: list) -> None:
        """Delete all tracked messages, kick the member, and log the action."""
        # 1. Delete every tracked message
        deleted = 0
        by_channel: dict[int, list] = {}
        for _ts, cid, msg, _ in entries:
            by_channel.setdefault(cid, []).append(msg)

        for cid, msgs in by_channel.items():
            ch = self.get_channel(cid)
            if not ch:
                continue
            for msg in msgs:
                try:
                    await msg.delete()
                    deleted += 1
                except Exception:
                    pass

        # 2. Kick
        kicked = False
        try:
            await member.kick(reason="Auto-spam: cross-channel image/message flood")
            kicked = True
        except Exception as ke:
            logger.warning("Spam kick failed for %s: %s", member, ke)

        channels_hit = {e[1] for e in entries}
        img_count = sum(1 for e in entries if e[3])

        # 3. Private log in mirror/backup channel
        log_ch = await self._mirror_dest()
        if log_ch:
            lines = [
                "🚨 **SPAM AUTO-ACTION**",
                f"**User:** {member.mention} (**{member}** — ID: `{member.id}`)",
                f"**Messages detected:** {len(entries)} across {len(channels_hit)} channel(s)",
                f"**Image-only messages:** {img_count}",
                f"**Messages deleted:** {deleted}",
                f"**Kicked:** {'✅ Yes' if kicked else '❌ Failed — check bot permissions'}",
            ]
            try:
                await log_ch.send("\n".join(lines))
            except Exception:
                pass

        # 4. Public notice in the community channel
        public_ch = self.get_channel(1158395982485147689)
        if public_ch and kicked:
            try:
                await public_ch.send(
                    f"⚠️ **{member}** was automatically kicked for spamming images across multiple channels. "
                    f"Their messages have been removed."
                )
            except Exception:
                pass

        logger.info("Spam punished: user=%s kicked=%s deleted=%d", member, kicked, deleted)

    async def _try_kb_auto_reply(self, message: discord.Message) -> bool:
        """Proactively reply with a KB match when a support-channel message looks like a question.

        Returns True if a reply was sent so the caller can short-circuit.
        """
        import time as _t
        text = message.content.strip()
        # Skip very short messages and ones that are obviously not questions
        if len(text) < 10:
            return False
        if not _looks_like_question(text):
            return False
        if message.id in self._kb_auto_replied:
            return False

        # Per-(user, channel) cooldown so the bot doesn't repeat itself
        key = (message.author.id, message.channel.id)
        now = _t.time()
        if now - self._kb_auto_cooldown.get(key, 0.0) < KB_AUTO_COOLDOWN:
            return False

        matches = _kb_search_scored(text, top_n=1, min_score=KB_AUTO_MIN_SCORE)
        if not matches:
            return False

        score, entry = matches[0]
        answer = entry["answer"]
        kb_question = entry["question"]
        images = entry.get("images") or []

        reply_text = f"📚 **From our FAQ:**\n{answer}"
        if len(reply_text) > 1900:
            reply_text = reply_text[:1897] + "…"

        try:
            await message.reply(reply_text, mention_author=False)
            if KB_POST_IMAGES and images:
                await message.channel.send("\n".join(images[:4]))
            self._kb_auto_replied.add(message.id)
            if len(self._kb_auto_replied) > 500:
                self._kb_auto_replied.clear()
            self._kb_auto_cooldown[key] = now
            if len(self._kb_auto_cooldown) > 500:
                cutoff = now - KB_AUTO_COOLDOWN
                self._kb_auto_cooldown = {k: v for k, v in self._kb_auto_cooldown.items() if v > cutoff}
            logger.info("KB auto-reply to %s (score=%d): %s", message.author, score, kb_question[:60])
            return True
        except Exception as _e:
            logger.warning("KB auto-reply error: %s", _e)
            return False

    async def _unanswered_alert_dest(self):
        """Resolve the channel where unanswered-question alerts are posted."""
        cid = UNANSWERED_ALERT_CHANNEL_ID or MIRROR_DEST_CHANNEL_ID
        if not cid:
            return None
        return self.get_channel(cid) or await self.fetch_channel(cid)

    def _schedule_unanswered_check(self, message: discord.Message) -> None:
        """Start a background timer that escalates the question if it stays ignored."""
        if UNANSWERED_ESCALATION_MINUTES <= 0:
            return
        if message.id in self._unanswered_scheduled:
            return
        # Bound the tracking set so long uptimes can't leak it
        if len(self._unanswered_scheduled) > 1000:
            self._unanswered_scheduled.clear()
        self._unanswered_scheduled.add(message.id)
        asyncio.create_task(self._check_unanswered(message))

    async def _check_unanswered(self, message: discord.Message) -> None:
        """After a delay, alert staff if nobody (bot or human) answered the question."""
        try:
            await asyncio.sleep(UNANSWERED_ESCALATION_MINUTES * 60)
            channel = message.channel
            # If the question was deleted in the meantime, drop it silently
            try:
                await channel.fetch_message(message.id)
            except discord.NotFound:
                return
            except Exception:
                pass
            # Answered if the bot or any user other than the asker posted afterward
            answered = False
            try:
                async for m in channel.history(limit=50, after=discord.Object(id=message.id)):
                    if m.id == message.id:
                        continue
                    if m.author.bot or m.author.id != message.author.id:
                        answered = True
                        break
            except Exception as _he:
                logger.warning("Unanswered-check history error: %s", _he)
                return
            if answered:
                return

            text = (message.content or "").strip()
            ch_label = getattr(channel, "mention", None) or f"#{getattr(channel, 'name', channel.id)}"
            alert = (
                f"🆘 **Unanswered question** — no reply in {UNANSWERED_ESCALATION_MINUTES} min\n"
                f"**From:** {message.author.mention} in {ch_label}\n"
                f"**Q:** {text[:500]}\n"
                f"**Jump:** {message.jump_url}"
            )
            dest = await self._unanswered_alert_dest()
            if dest:
                try:
                    await dest.send(alert)
                except Exception as _se:
                    logger.warning("Unanswered alert send failed: %s", _se)
            if UNANSWERED_PUSHOVER:
                await _send_pushover(
                    title="🆘 Unanswered question",
                    message=f"{message.author.display_name}: {text[:200]}",
                    sound="none",
                )
            logger.info("Escalated unanswered question from %s: %s", message.author, text[:60])
        except Exception as _e:
            logger.warning("Unanswered-question check error: %s", _e)
        finally:
            self._unanswered_scheduled.discard(message.id)

    async def on_message(self, message: discord.Message) -> None:
        # Mirror all messages from the source channel to the backup channel.
        if message.channel.id == MIRROR_SOURCE_CHANNEL_ID and MIRROR_DEST_CHANNEL_ID:
            try:
                dest = self.get_channel(MIRROR_DEST_CHANNEL_ID)
                if dest:
                    # Build header: author, timestamp, jump link
                    ts = discord.utils.format_dt(message.created_at, style="f")
                    jump = message.jump_url
                    author_tag = f"{message.author.mention} ({message.author} — ID: {message.author.id})"
                    header = f"**{author_tag}** — {ts}\n{jump}"
                    body = message.content or ""
                    mirror_text = f"{header}\n{body}".strip()
                    # Collect files to re-upload (max 8 MB per file; skip oversized)
                    files = []
                    for att in message.attachments:
                        if att.size <= 8_000_000:
                            try:
                                files.append(await att.to_file())
                            except Exception:
                                mirror_text += f"\n📎 {att.filename} ({att.url})"
                        else:
                            mirror_text += f"\n📎 {att.filename} (too large to copy — {att.url})"
                    await dest.send(mirror_text, files=files if files else discord.utils.MISSING)
            except Exception as _me:
                logger.warning("Mirror error: %s", _me)

        if message.author.bot:
            return

        # Invite-link filter — runs before flood check so a single drop is caught
        if await self._check_invite_link(message):
            return

        # Spam detection runs on every non-bot message
        if await self._check_spam(message):
            return
        # Trigger if bot is @mentioned OR if someone replies to one of the bot's messages
        is_mention = self.user in message.mentions
        is_reply_to_bot = False
        if message.reference and message.reference.message_id:
            try:
                ref = message.reference.resolved or await message.channel.fetch_message(message.reference.message_id)
                if ref and ref.author and ref.author.id == self.user.id:
                    is_reply_to_bot = True
            except Exception:
                pass
        if not is_mention and not is_reply_to_bot:
            # Proactively answer questions in support channels OR project forum threads
            in_kb_channel = message.channel.id in KB_CHANNEL_IDS
            in_project_thread = (
                PROJECTS_FORUM_CHANNEL_ID
                and isinstance(message.channel, discord.Thread)
                and str(getattr(message.channel, "parent_id", None)) == PROJECTS_FORUM_CHANNEL_ID
            )
            if in_kb_channel or in_project_thread:
                replied = await self._try_kb_auto_reply(message)
                # If neither the bot nor (yet) a human has answered, watch the
                # question and escalate to staff if it stays ignored.
                _qtext = message.content.strip()
                if not replied and len(_qtext) >= 10 and _looks_like_question(_qtext):
                    self._schedule_unanswered_check(message)
            return
        if not ANTHROPIC_API_KEY:
            return
        if message.id in self._processed_messages:
            return
        self._processed_messages.add(message.id)
        # Keep set size bounded
        if len(self._processed_messages) > 1000:
            self._processed_messages.clear()

        # Per-user rate limit: the AI path spawns yt-dlp subprocesses and outbound
        # fetches, so a rapid message stream from one account could saturate CPU /
        # sockets / memory. Drop calls that arrive within the cooldown.
        _now_mono = time.monotonic()
        if _now_mono - self._ai_last_call.get(message.author.id, 0.0) < AI_USER_COOLDOWN:
            return
        self._ai_last_call[message.author.id] = _now_mono
        if len(self._ai_last_call) > 5000:
            self._ai_last_call = {
                k: v for k, v in self._ai_last_call.items() if _now_mono - v < 3600
            }

        question = message.content.replace(f"<@{self.user.id}>", "").strip()
        _image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        def _is_image_attachment(a):
            if a.content_type and a.content_type.startswith("image/"):
                return True
            import os as _os
            ext = _os.path.splitext(a.filename)[1].lower()
            return ext in _image_exts

        # Collect attachments and text from this message AND the replied-to message
        all_attachments = list(message.attachments)
        replied_text = ""
        ref_msg = None
        if message.reference:
            ref_msg = message.reference.resolved
            # Fetch the referenced message if Discord didn't cache it
            if ref_msg is None and message.reference.message_id:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                except Exception:
                    pass
        if ref_msg is not None:
            if hasattr(ref_msg, "attachments"):
                all_attachments.extend(ref_msg.attachments)
            if hasattr(ref_msg, "content") and ref_msg.content:
                replied_text = ref_msg.content.strip()

        _text_exts = {".txt", ".md", ".csv", ".log", ".srt", ".vtt"}
        def _is_text_attachment(a):
            if a.content_type and (
                a.content_type.startswith("text/") or
                a.content_type in ("application/octet-stream",)
            ):
                import os as _os
                ext = _os.path.splitext(a.filename)[1].lower()
                return ext in _text_exts
            import os as _os
            ext = _os.path.splitext(a.filename)[1].lower()
            return ext in _text_exts

        has_images = any(_is_image_attachment(a) for a in all_attachments)
        has_text_files = any(_is_text_attachment(a) for a in all_attachments)
        if not question and not has_images and not has_text_files and not replied_text:
            # Look at the last message from the same user in this channel (within 2 min).
            # Handles the case where they send text then @mention as a separate message.
            try:
                async for _prev in message.channel.history(limit=5, before=message):
                    if _prev.author.id == message.author.id and _prev.content.strip():
                        _age = (message.created_at - _prev.created_at).total_seconds()
                        if _age < 120:
                            question = _prev.content.strip()
                        break
            except Exception:
                pass
        if not question and not has_images and not has_text_files and not replied_text:
            await message.reply("Hey! How can I help? 😊")
            return

        import aiohttp as _aiohttp
        # Build user message content (text + images)
        user_content: list = []
        image_count = 0
        attached_texts: list[str] = []
        for attachment in all_attachments:
            if _is_text_attachment(attachment):
                try:
                    async with _aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            if resp.status == 200:
                                raw = await resp.read()
                                # Cap at 150 KB to avoid massive prompts
                                if len(raw) > 150_000:
                                    raw = raw[:150_000]
                                    truncated = True
                                else:
                                    truncated = False
                                text_content = raw.decode("utf-8", errors="replace")
                                suffix = "\n[...truncated at 150 KB]" if truncated else ""
                                attached_texts.append(
                                    f"[Attachment: {attachment.filename}]\n{text_content}{suffix}"
                                )
                except Exception as _te:
                    logger.warning("Could not read text attachment %s: %s", attachment.filename, _te)
            elif _is_image_attachment(attachment):
                if image_count >= MAX_IMAGES_PER_MSG:
                    logger.info("Per-message image cap (%d) reached; skipping %s",
                                MAX_IMAGES_PER_MSG, attachment.filename)
                    continue
                async with _aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                        if resp.status == 200:
                            img_bytes = await resp.content.read(MAX_IMAGE_BYTES + 1)
                            if len(img_bytes) > MAX_IMAGE_BYTES:
                                logger.warning("Skipping oversize image %s (> %d bytes)",
                                               attachment.filename, MAX_IMAGE_BYTES)
                                continue
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
        # Fetch last 12 messages in the channel for context, including attachments
        channel_context = ""
        _hist_images: list = []
        _hist_img_count = 0
        _MAX_HIST_IMAGES = 3
        _MAX_HIST_FILE_BYTES = 30_000
        try:
            history_msgs = []
            async with _aiohttp.ClientSession() as _hist_session:
                async for m in message.channel.history(limit=12, before=message):
                    if m.id == message.id:
                        continue
                    author = m.author.display_name
                    parts_for_msg = []
                    content = m.content.strip()
                    if content:
                        parts_for_msg.append(content)
                    for _hatt in m.attachments:
                        if _is_text_attachment(_hatt):
                            try:
                                async with _hist_session.get(_hatt.url) as _hr:
                                    if _hr.status == 200:
                                        _hraw = await _hr.read()
                                        _htrunc = ""
                                        if len(_hraw) > _MAX_HIST_FILE_BYTES:
                                            _hraw = _hraw[:_MAX_HIST_FILE_BYTES]
                                            _htrunc = "\n[...truncated]"
                                        _htxt = _hraw.decode("utf-8", errors="replace")
                                        parts_for_msg.append(
                                            f"[Attachment: {_hatt.filename}]\n{_htxt}{_htrunc}"
                                        )
                            except Exception:
                                parts_for_msg.append(f"[Attachment: {_hatt.filename} — could not read]")
                        elif _is_image_attachment(_hatt):
                            if _hist_img_count < _MAX_HIST_IMAGES:
                                try:
                                    async with _hist_session.get(_hatt.url) as _hr:
                                        if _hr.status == 200:
                                            _hibytes = await _hr.read()
                                            import base64 as _b64h
                                            _hib64 = _b64h.b64encode(_hibytes).decode()
                                            if _hibytes[:8] == b'\x89PNG\r\n\x1a\n':    _himt = "image/png"
                                            elif _hibytes[:3] == b'\xff\xd8\xff':        _himt = "image/jpeg"
                                            elif _hibytes[:4] == b'GIF8':               _himt = "image/gif"
                                            elif _hibytes[:4] == b'RIFF' and _hibytes[8:12] == b'WEBP': _himt = "image/webp"
                                            else: _himt = (_hatt.content_type or "image/png").split(";")[0].strip()
                                            _hist_images.append({
                                                "type": "image",
                                                "source": {"type": "base64", "media_type": _himt, "data": _hib64},
                                            })
                                            _hist_img_count += 1
                                            parts_for_msg.append(f"[Image: {_hatt.filename}]")
                                except Exception:
                                    parts_for_msg.append(f"[Image: {_hatt.filename} — could not load]")
                            else:
                                parts_for_msg.append(f"[Image: {_hatt.filename}]")
                        else:
                            parts_for_msg.append(f"[File: {_hatt.filename}]")
                    if parts_for_msg:
                        history_msgs.append(f"{author}: " + "\n".join(parts_for_msg))
            if history_msgs:
                history_msgs.reverse()  # oldest first
                channel_context = "\n\n".join(history_msgs)
        except Exception as _he:
            logger.warning("Failed to fetch channel history: %s", _he)

        # Detect YouTube URLs in current message, replied-to message, or embeds
        import re as _re
        _yt_pattern = r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})'
        # Also check embeds on the replied-to and current message (Discord stores link embeds there)
        _embed_urls = ""
        _embed_info = ""  # title + description extracted from Discord embed
        _check_embeds_on = []
        if ref_msg is not None:
            _check_embeds_on.append(ref_msg)
        # Wait briefly for Discord to populate embeds on the current message
        if not message.embeds:
            await asyncio.sleep(1.5)
            try:
                message = await message.channel.fetch_message(message.id)
            except Exception:
                pass
        _check_embeds_on.append(message)
        for _emsg in _check_embeds_on:
            for embed in getattr(_emsg, "embeds", []):
                if embed.url:
                    _embed_urls += " " + embed.url
                if embed.video and embed.video.url:
                    _embed_urls += " " + embed.video.url
                # Capture title and description from the embed
                if embed.title:
                    _embed_info += f"Title: {embed.title}\n"
                if embed.description:
                    _embed_info += f"Description: {embed.description}\n"
                if embed.author and embed.author.name:
                    _embed_info += f"Channel: {embed.author.name}\n"
        _all_text = (question or "") + " " + (replied_text or "") + " " + _embed_urls
        _yt_match = _re.search(_yt_pattern, _all_text)
        transcript_context = ""
        yt_url = ""
        if _yt_match:
            video_id = _yt_match.group(1)
            yt_url = f"https://youtu.be/{video_id}"
            yt_title = ""
            yt_description = ""

            # Use yt-dlp to get metadata + subtitles in one call
            loop = asyncio.get_event_loop()
            def _get_yt_info():
                import subprocess, json as _json, shutil, tempfile
                # Run in a throwaway dir so the subtitle files yt-dlp writes land
                # there (not the process CWD) and are deleted afterwards — otherwise
                # they accumulate forever and can fill the disk.
                _tmpd = tempfile.mkdtemp(prefix="ytsub_")
                try:
                    result = subprocess.run(
                        [
                            "yt-dlp",
                            "--skip-download",
                            "--dump-json",
                            "--write-auto-sub",
                            "--write-sub",
                            "--sub-lang", "en,pt",
                            "--sub-format", "json3",
                            "-o", "%(id)s.%(ext)s",
                            f"https://www.youtube.com/watch?v={video_id}",
                        ],
                        capture_output=True, text=True, timeout=30, cwd=_tmpd,
                    )
                    if result.returncode != 0:
                        return {}, ""
                    info = _json.loads(result.stdout)
                    # Extract subtitles from the json3 format if downloaded
                    subs_text = ""
                    # Check requested_subtitles for the actual subtitle data
                    req_subs = info.get("requested_subtitles") or {}
                    for lang in ["en", "pt"]:
                        sub_info = req_subs.get(lang)
                        if sub_info and sub_info.get("filepath"):
                            try:
                                _fp = sub_info["filepath"]
                                if not os.path.isabs(_fp):
                                    _fp = os.path.join(_tmpd, _fp)
                                with open(_fp, "r", encoding="utf-8") as f:
                                    sub_data = _json.load(f)
                                events = sub_data.get("events", [])
                                segments = []
                                for evt in events:
                                    segs = evt.get("segs", [])
                                    text = "".join(s.get("utf8", "") for s in segs).strip()
                                    if text and text != "\n":
                                        segments.append(text)
                                subs_text = " ".join(segments)
                            except Exception:
                                pass
                            if subs_text:
                                break
                    return info, subs_text[:6000]
                except Exception as e:
                    logger.warning("yt-dlp failed for %s: %s", video_id, e)
                    return {}, ""
                finally:
                    shutil.rmtree(_tmpd, ignore_errors=True)

            try:
                yt_info, subs = await loop.run_in_executor(None, _get_yt_info)
                yt_title = yt_info.get("title", "")
                yt_description = (yt_info.get("description") or "")[:1000]
                if subs:
                    transcript_context = subs
                    logger.info("yt-dlp extracted transcript for %s (%d chars)", video_id, len(subs))
            except Exception as _te:
                logger.warning("yt-dlp error for %s: %s", video_id, _te)

            # If yt-dlp failed, try youtube-transcript-api as fallback
            if not transcript_context:
                try:
                    from youtube_transcript_api import YouTubeTranscriptApi as _YTApi
                    def _get_transcript():
                        try:
                            transcript = _YTApi.get_transcript(video_id)
                        except Exception:
                            transcript = _YTApi.get_transcript(video_id, languages=["en", "pt", "auto"])
                        return " ".join(t["text"] for t in transcript)[:6000]
                    transcript_context = await loop.run_in_executor(None, _get_transcript)
                except Exception as _te:
                    logger.warning("youtube-transcript-api also failed for %s: %s", video_id, _te)

        # YouTube search — if no URL shared and question looks like a search request
        yt_search_results = ""
        _search_keywords = ["find", "search", "link", "where", "video", "tutorial", "show me", "can you find", "look for"]
        _looks_like_search = (
            not _yt_match
            and any(kw in (question or "").lower() for kw in _search_keywords)
        )
        if _looks_like_search:
            # Build search query — strip filler words and focus on content terms
            search_query = (question or "").lower()
            # Automatically scope to LocoDev if not already mentioned
            if "locodev" not in search_query:
                search_query = f"LocoDev {question}"
            else:
                search_query = question
            try:
                import subprocess, json as _json
                loop = asyncio.get_event_loop()
                def _yt_search():
                    result = subprocess.run(
                        ["yt-dlp", f"ytsearch5:{search_query}", "--dump-json",
                         "--flat-playlist", "--skip-download", "--no-warnings"],
                        capture_output=True, text=True, timeout=20
                    )
                    videos = []
                    for line in result.stdout.strip().splitlines():
                        try:
                            v = _json.loads(line)
                            title = v.get("title", "")
                            url = v.get("webpage_url") or f"https://youtu.be/{v.get('id','')}"
                            if title and url:
                                videos.append(f"- {title}: {url}")
                        except Exception:
                            pass
                    return "\n".join(videos)
                yt_search_results = await loop.run_in_executor(None, _yt_search)
                if yt_search_results:
                    logger.info("YouTube search returned results for: %s", search_query)
            except Exception as _se:
                logger.warning("YouTube search failed: %s", _se)

        # Patreon post search — when user asks to find a Patreon post/system
        patreon_search_results = ""
        web_context = ""  # initialized here; populated later in URL fetch block
        _patreon_keywords = ["patreon", "post", "system", "project files", "download", "premium", "find", "link", "where"]
        _looks_like_patreon_search = (
            not _yt_match
            and not web_context
            and any(kw in (question or "").lower() for kw in _patreon_keywords)
        )
        if _looks_like_patreon_search and PATREON_ACCESS_TOKEN:
            # Extract meaningful search terms (remove common stop words and punctuation)
            _filler = {
                "can", "you", "find", "the", "link", "for", "to", "a", "an", "of", "from",
                "locodev", "patreon", "post", "posts", "video", "please", "where", "is",
                "get", "on", "in", "at", "be", "do", "have", "about", "with", "it",
                "this", "that", "me", "my", "i", "we", "us", "are", "was", "has",
                "there", "some", "any", "what", "which", "how", "up", "out", "by",
                "show", "give", "send", "share", "look", "search", "hey", "hi", "please"
            }
            import re as _re2
            search_terms = " ".join(
                _re2.sub(r'[^\w\s]', '', w) for w in (question or "").split()
                if w.lower().rstrip("?!.,") not in _filler and len(w) > 2
            ).strip()
            if search_terms:
                try:
                    loop = asyncio.get_event_loop()
                    posts = await loop.run_in_executor(None, _search_patreon_posts, search_terms)
                    if posts:
                        lines = [f"- {p['title']}: {p['url']}" for p in posts]
                        patreon_search_results = "\n".join(lines)
                        logger.info("Patreon search for '%s' returned %d results", search_terms, len(posts))
                except Exception as _pe:
                    logger.warning("Patreon post search failed: %s", _pe)

        # Detect non-YouTube URLs and fetch their content
        _url_pattern = r'https?://[^\s<>\"\']+'
        _all_urls = _re.findall(_url_pattern, _all_text)
        # Filter out YouTube URLs (already handled above)
        _other_urls = [u for u in _all_urls if not _re.search(_yt_pattern, u)]
        if _other_urls and not _yt_match:
            url_to_fetch = _other_urls[0]  # fetch the first non-YT URL
            # SSRF guard: only fetch public http(s) hosts. Blocks localhost / cloud
            # metadata / internal ranges that a member could otherwise reach and
            # exfiltrate through the bot's reply.
            if not _is_safe_fetch_url(url_to_fetch):
                logger.warning("Refusing to fetch non-public/unsafe URL: %s", url_to_fetch)
            else:
                logger.info("Attempting to fetch web content from: %s", url_to_fetch)
                try:
                    import aiohttp as _aiohttp
                    async with _aiohttp.ClientSession() as session:
                        status, body = await _fetch_capped(
                            session,
                            url_to_fetch,
                            timeout=_aiohttp.ClientTimeout(total=15),
                            allow_redirects=False,  # no redirect-based allowlist bypass
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            },
                        )
                        logger.info("URL %s returned status %s", url_to_fetch, status)
                        if status == 200 and body:
                            html = body.decode("utf-8", errors="replace")
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(html, "html.parser")
                            for tag in soup(["script", "style", "nav", "footer", "header"]):
                                tag.decompose()
                            page_title = soup.title.string.strip() if soup.title and soup.title.string else ""
                            text = soup.get_text(separator="\n", strip=True)
                            lines = [l.strip() for l in text.splitlines() if l.strip()]
                            web_context = "\n".join(lines)[:4000]
                            if page_title:
                                web_context = f"Page title: {page_title}\n\n{web_context}"
                            logger.info("Fetched web content from %s (%d chars)", url_to_fetch, len(web_context))
                        elif status not in (200, None):
                            logger.warning("URL %s returned non-200 status: %s", url_to_fetch, status)
                except Exception as _we:
                    logger.warning("Failed to fetch URL %s: %s", url_to_fetch, _we)
            # If fetch failed, use Discord embed info as fallback
            if not web_context and _embed_info:
                web_context = f"Page: {url_to_fetch}\n{_embed_info.strip()}"
                logger.info("Using Discord embed info as fallback for %s", url_to_fetch)

        # Search knowledge base for relevant past Q&A
        kb_context = ""
        if question:
            kb_matches = _kb_search(question, top_n=3)
            if kb_matches:
                kb_lines = [
                    f"Q: {e['question']}\nA: {e['answer']}" +
                    (f"\nImages: {', '.join(e['images'])}" if e.get('images') else "")
                    for e in kb_matches
                ]
                kb_context = "\n\n".join(kb_lines)

        # Build the final text prompt, including context from replied-to message
        parts = []
        if kb_context:
            parts.append(f"[Relevant past Q&A from community knowledge base:\n{kb_context}\n]")
        if channel_context:
            parts.append(f"[Recent channel messages for context:\n{channel_context}\n]")

        # Link analytics context — inject if question is about links/clicks (owner only)
        # Owner can create/delete short links by talking to the bot — but only in the
        # link management channel, and the destination must be on the trusted domain list.
        _is_owner = bool(OWNER_DISCORD_ID) and message.author.id == OWNER_DISCORD_ID
        if _is_owner and message.channel.id == LINK_MANAGEMENT_CHANNEL_ID:
            import re as _re
            from urllib.parse import urlparse as _ulp_chat
            # Use raw message content for link detection (more reliable than parsed question)
            _raw_msg = message.content
            _q_lower = _raw_msg.lower()
            _delete_kw = ["delete link", "remove link", "delete the link", "remove the link"]

            if any(kw in _q_lower for kw in _delete_kw):
                _slug_match = _re.search(r'(?:delete|remove)\s+(?:the\s+)?link\s+/?([^\s]+)', _q_lower)
                if _slug_match:
                    _raw = _slug_match.group(1).strip("/")
                    if "/" in _raw:
                        _dpfx, _dslug = _raw.split("/", 1)
                    else:
                        _dpfx, _dslug = "root", _raw
                    from shortener import delete_link as _del_link
                    _deleted = _del_link(_dslug, _dpfx)
                    if _deleted:
                        _audit_link_change("delete", message.author.id, str(message.author), _dpfx, _dslug, "")
                        await message.channel.send(f"✅ Deleted `/{_dpfx}/{_dslug}`.")
                    else:
                        await message.channel.send(f"❌ Link `/{_dpfx}/{_dslug}` not found.")
                    return

            else:
                # Detect create intent: message has a locodev.dev/path AND a https:// URL
                _path_match = _re.search(r'locodev\.dev/([^\s→>\n]+)', _raw_msg, _re.IGNORECASE)
                _url_match = _re.search(r'https?://[^\s→>\n]+', _raw_msg)
                if _path_match and _url_match:
                    _dest_url = _url_match.group(0).rstrip(".,)")
                    _raw_path = _path_match.group(1).strip("/")
                    if "/" in _raw_path:
                        _pfx, _slg = _raw_path.split("/", 1)
                    else:
                        _pfx, _slg = "root", _raw_path
                    # Domain allowlist — same set used by the [CREATE_LINK] marker
                    _dom = _ulp_chat(_dest_url).netloc.lower()
                    if _dom.startswith("www."):
                        _dom = _dom[4:]
                    _dom = _dom.split(":")[0]
                    _all_doms = _ALLOWED_DOWNLOAD_DOMAINS | {"patreon.com", "youtube.com", "youtu.be"}
                    if not any(_dom == _d or _dom.endswith("." + _d) for _d in _all_doms):
                        await message.channel.send(f"🚫 Domain `{_dom}` is not on the trusted list. Link not created.")
                        return
                    # Auto-append random suffix for obscured prefixes (e.g. download/)
                    if _pfx in _OBSCURED_PREFIXES and "/" not in _slg:
                        _slg = f"{_slg}/{_random_slug_suffix()}"
                    try:
                        from shortener import create_link as _crt_link, update_link as _upd_link, get_link as _get_link
                        _ok = _crt_link(_slg, _dest_url, _pfx)
                        _short = f"locodev.dev/{_pfx}/{_slg}" if _pfx != "root" else f"locodev.dev/{_slg}"
                        if not _ok:
                            _upd_link(_slg, _dest_url, _pfx)
                        # Verify it's actually in the DB
                        _verify = _get_link(_slg, _pfx)
                        if _verify:
                            action = "Created" if _ok else "Updated"
                            _audit_link_change(action.lower(), message.author.id, str(message.author), _pfx, _slg, _dest_url)
                            await message.channel.send(f"✅ {action}: `{_short}` → {_verify['url']}")
                        else:
                            await message.channel.send(f"❌ Failed to save link — DB write error.")
                            logger.error("Link creation failed: slug=%s prefix=%s url=%s", _slg, _pfx, _dest_url)
                    except Exception as _le:
                        await message.channel.send(f"❌ Error creating link: {_le}")
                        logger.error("Link creation exception: %s", _le)
                    return


        _link_keywords = ["link", "click", "locodev.dev", "short", "redirect", "country", "visit", "traffic", "popular", "most clicked", "how many", "create", "make a", "short link"]
        if _is_owner and any(kw in (question or "").lower() for kw in _link_keywords):
            try:
                from shortener import get_top_links, list_links, get_stats, _conn as _sh_conn
                from datetime import timedelta as _td, timezone as _shtz
                _all_links = list_links()
                _top_1 = get_top_links(days=1, limit=10)
                _top_7 = get_top_links(days=7, limit=10)
                _top_30 = get_top_links(days=30, limit=10)
                # Country breakdown for last 7 days (overall)
                _cutoff_7 = (datetime.now(_shtz.utc) - _td(days=7)).isoformat()
                with _sh_conn() as _shdb:
                    _countries = _shdb.execute(
                        """SELECT country, country_code, COUNT(*) cnt
                           FROM clicks WHERE clicked_at >= ?
                           GROUP BY country ORDER BY cnt DESC LIMIT 10""",
                        (_cutoff_7,)
                    ).fetchall()
                _link_lines = ["YOUR SHORT LINKS (locodev.dev):"]
                for lnk in _all_links:
                    _link_lines.append(f"  {_fmt_link(lnk['prefix'], lnk['slug'])} → {lnk['url']}")
                _link_lines.append("\nTOP CLICKS LAST 24 HOURS:")
                for lnk in _top_1:
                    _link_lines.append(f"  {_fmt_link(lnk['prefix'], lnk['slug'])} — {lnk['clicks']} clicks")
                if not _top_1:
                    _link_lines.append("  No clicks in the last 24 hours.")
                _link_lines.append("\nTOP CLICKS LAST 7 DAYS (with per-link country breakdown):")
                for lnk in _top_7:
                    _lbl = _fmt_link(lnk['prefix'], lnk['slug'])
                    _link_lines.append(f"  {_lbl} — {lnk['clicks']} clicks")
                    _lstats = get_stats(lnk['slug'], lnk['prefix'], days=7)
                    if _lstats and _lstats.get('by_country'):
                        for _bc in _lstats['by_country'][:5]:
                            _link_lines.append(f"    • {_bc['country'] or 'Unknown'} ({_bc['country_code'] or '??'}) — {_bc['cnt']} clicks")
                _link_lines.append("\nTOP CLICKS LAST 30 DAYS:")
                for lnk in _top_30:
                    _link_lines.append(f"  {_fmt_link(lnk['prefix'], lnk['slug'])} — {lnk['clicks']} clicks")
                _link_lines.append("\nOVERALL COUNTRY BREAKDOWN (last 7 days, all links combined):")
                for _c in _countries:
                    _link_lines.append(f"  {_c['country'] or 'Unknown'} ({_c['country_code'] or '??'}) — {_c['cnt']} clicks")
                if not _countries:
                    _link_lines.append("  No country data available.")
                # If a specific link path is mentioned in the question, inject its detailed stats
                import re as _sre
                _mentioned = _sre.findall(r'(?:locodev\.dev/|/)?([a-z0-9_-]+/[a-zA-Z0-9/_.-]+)', (question or "").lower())
                for _mpath in _mentioned:
                    _mpath = _mpath.strip("/")
                    if "/" in _mpath:
                        _mpfx, _mslg = _mpath.split("/", 1)
                        _mstats = get_stats(_mslg, _mpfx, days=30)
                        if _mstats and _mstats['total'] > 0:
                            _link_lines.append(f"\nDETAILED STATS FOR /{_mpfx}/{_mslg} (last 30 days):")
                            _link_lines.append(f"  Total: {_mstats['total']} clicks")
                            _link_lines.append(f"  By country:")
                            for _bc in _mstats['by_country']:
                                _link_lines.append(f"    • {_bc['country'] or 'Unknown'} ({_bc['country_code'] or '??'}) — {_bc['cnt']} clicks")
                            if not _mstats['by_country']:
                                _link_lines.append(f"    • No country data resolved yet (geo lookup pending)")
                parts.append(f"[URL Shortener Analytics:\n" + "\n".join(_link_lines) + "\n]")
            except Exception as _le:
                logger.warning("Link analytics context error: %s", _le)

        # Google Drive project folders — inject when in link channel so Claude
        # can auto-fill the destination URL when creating download/ links.
        if message.channel.id == LINK_MANAGEMENT_CHANNEL_ID and _is_owner:
            try:
                from drive_helper import list_project_folders as _gdrive_list
                _drive_folders = _gdrive_list()
                if _drive_folders:
                    _folder_lines = "\n".join(
                        f"  • {f['name']} → {f['url']}" for f in _drive_folders
                    )
                    parts.append(f"[Google Drive project folders (use these URLs for download/ links):\n{_folder_lines}\n]")
            except Exception as _dre:
                logger.warning("Drive context error: %s", _dre)

        # Patreon event context — inject if question is about subscribers/members (owner only)
        _patreon_keywords = ["patreon", "patron", "subscriber", "subscri", "join", "cancel", "trial", "member", "who paid", "who signed", "pledge", "tier", "revenue", "income", "earning", "monthly", "mrr", "money", "increasing", "growing"]
        if _is_owner and any(kw in (question or "").lower() for kw in _patreon_keywords):
            try:
                _events = _load_events()
                from datetime import timezone as _tz
                _now = datetime.now(_tz.utc)
                _7d_cutoff = (_now - timedelta(days=7)).isoformat()
                _30d_cutoff = (_now - timedelta(days=30)).isoformat()
                _recent = [e for e in _events if e.get("ts", "") >= _7d_cutoff]
                _month = [e for e in _events if e.get("ts", "") >= _30d_cutoff]

                # Revenue summary from active paid subscribers (members:pledge:create + members:pledge:update)
                # Use latest pledge event per member to get current amount
                _member_amounts: dict = {}
                for e in sorted(_events, key=lambda x: x.get("ts", "")):
                    if e.get("event") in ("members:pledge:create", "members:pledge:update") and not e.get("is_trial") and e.get("amount", 0) > 0:
                        _member_amounts[e.get("member_id", e.get("name"))] = e.get("amount", 0)
                    elif e.get("event") in ("members:pledge:delete", "members:delete"):
                        _member_amounts.pop(e.get("member_id", e.get("name")), None)
                _mrr = sum(_member_amounts.values())
                _active_count = len(_member_amounts)

                # Revenue from last 30 days (new payments received)
                _payments_30d = [e for e in _month if e.get("event") == "members:update" and e.get("amount", 0) > 0]
                _new_subs_30d = [e for e in _month if e.get("event") == "members:pledge:create" and not e.get("is_trial") and e.get("amount", 0) > 0]
                _cancels_30d = [e for e in _month if e.get("event") in ("members:pledge:delete", "members:delete")]

                _ev_lines = ["PATREON REVENUE & MEMBER DATA:"]
                _ev_lines.append(f"\nESTIMATED MRR (based on active pledges in log): ${_mrr:.2f}/month")
                _ev_lines.append(f"Active paid members tracked: {_active_count}")
                _ev_lines.append(f"\nLAST 30 DAYS:")
                _ev_lines.append(f"  New paid subscribers: {len(_new_subs_30d)}")
                _ev_lines.append(f"  Cancellations: {len(_cancels_30d)}")
                _ev_lines.append(f"  Net change: {len(_new_subs_30d) - len(_cancels_30d):+d}")
                _ev_lines.append(f"\nRECENT EVENTS (last 7 days):")
                for e in sorted(_recent, key=lambda x: x.get("ts",""), reverse=True):
                    _trial_tag = " [FREE TRIAL]" if e.get("is_trial") else ""
                    _conv_tag = " [CONVERTED]" if e.get("is_trial_conversion") else ""
                    _ev_lines.append(f"  {e.get('ts','')[:10]} {e.get('event','')} — {e.get('name','?')} tier={e.get('tier','?')} amount=${e.get('amount',0):.2f}{_trial_tag}{_conv_tag}")
                if not _recent:
                    _ev_lines.append("  No events in last 7 days.")
                _ev_lines.append(f"\nALL EVENTS LAST 30 DAYS:")
                for e in sorted(_month, key=lambda x: x.get("ts",""), reverse=True):
                    _trial_tag = " [FREE TRIAL]" if e.get("is_trial") else ""
                    _conv_tag = " [CONVERTED]" if e.get("is_trial_conversion") else ""
                    _ev_lines.append(f"  {e.get('ts','')[:10]} {e.get('event','')} — {e.get('name','?')} tier={e.get('tier','?')} amount=${e.get('amount',0):.2f}{_trial_tag}{_conv_tag}")
                if not _month:
                    _ev_lines.append("  No events in last 30 days.")

                # Correlate Patreon link clicks with conversions (time-based)
                try:
                    from shortener import _conn as _sh_conn
                    from datetime import timedelta as _td
                    _cutoff_30 = (_now - timedelta(days=30)).isoformat()
                    with _sh_conn() as _shdb:
                        # Clicks on Patreon links (p/ prefix) per slug last 30 days
                        _p_clicks = _shdb.execute(
                            """SELECT l.slug, l.url, COUNT(c.id) cnt,
                                      MIN(c.clicked_at) first_click, MAX(c.clicked_at) last_click
                               FROM links l JOIN clicks c ON c.link_id=l.id
                               WHERE l.prefix='p' AND c.clicked_at>=?
                               GROUP BY l.id ORDER BY cnt DESC""",
                            (_cutoff_30,)
                        ).fetchall()
                        # Free join clicks (free/ prefix)
                        _free_clicks = _shdb.execute(
                            """SELECT l.slug, l.url, COUNT(c.id) cnt,
                                      MIN(c.clicked_at) first_click, MAX(c.clicked_at) last_click
                               FROM links l JOIN clicks c ON c.link_id=l.id
                               WHERE l.prefix='free' AND c.clicked_at>=?
                               GROUP BY l.id ORDER BY cnt DESC""",
                            (_cutoff_30,)
                        ).fetchall()
                    _ev_lines.append(f"\nPATREON LINK CLICKS vs CONVERSIONS (last 30 days):")
                    _ev_lines.append("Patreon page links (locodev.dev/p/...):")
                    for _r in _p_clicks:
                        _ev_lines.append(f"  /p/{_r['slug']} — {_r['cnt']} clicks (last: {(_r['last_click'] or '')[:10]})")
                    if not _p_clicks:
                        _ev_lines.append("  No clicks on Patreon links.")
                    _ev_lines.append("Free tier links (locodev.dev/free/...):")
                    for _r in _free_clicks:
                        _ev_lines.append(f"  /free/{_r['slug']} — {_r['cnt']} clicks (last: {(_r['last_click'] or '')[:10]})")
                    if not _free_clicks:
                        _ev_lines.append("  No clicks on free links.")
                    _ev_lines.append("NOTE: Direct correlation not possible (no user ID tracking), but you can infer by comparing click dates with conversion dates above.")
                except Exception as _ce:
                    logger.warning("Conversion correlation error: %s", _ce)

                parts.append(f"[Patreon Member Events:\n" + "\n".join(_ev_lines) + "\n]")
            except Exception as _pe:
                logger.warning("Patreon event context error: %s", _pe)

        if web_context:
            parts.append(f"[Web page content from {url_to_fetch}:\n{web_context}\n]")
        if yt_search_results:
            parts.append(f"[YouTube search results for '{search_query}':\n{yt_search_results}\n\nShare the most relevant link(s) from above to answer the user's request.]")
        if patreon_search_results:
            parts.append(f"[Patreon post search results for '{search_terms}':\n{patreon_search_results}\n\nShare the most relevant Patreon link(s) from above.]")
        if transcript_context:
            header = f"[YouTube video: {yt_url}"
            if yt_title:
                header += f"\nTitle: {yt_title}"
            header += f"\n\nTranscript:\n{transcript_context}\n]"
            parts.append(header)
        elif yt_url:
            # No transcript — use yt-dlp metadata or Discord embed info
            video_info = f"[YouTube video: {yt_url}"
            if yt_title:
                video_info += f"\nTitle: {yt_title}"
            if yt_description:
                video_info += f"\nDescription: {yt_description}"
            if not yt_title and _embed_info:
                video_info += f"\n{_embed_info.strip()}"
            video_info += "\n(Answer based on the title/description above)]"
            parts.append(video_info)
        if replied_text and not _yt_match:
            parts.append(f"[Replying to this message:\n{replied_text}\n]")
        for _at in attached_texts:
            parts.append(_at)
        if question:
            parts.append(question)
        elif image_count > 0 and not replied_text and not transcript_context:
            parts.append("Please describe and analyze what you see in this image.")
        elif attached_texts and not question:
            parts.append("Please read the attached file(s) and summarize or answer any question about them.")
        full_prompt = "\n\n".join(parts) if parts else ""
        # Inject historical images after current-message images, before the text prompt
        for _hi in _hist_images:
            user_content.append(_hi)
        if full_prompt:
            user_content.append({"type": "text", "text": full_prompt})
        if not user_content:
            await message.reply("Hey! How can I help? 😊")
            return

        # Build conversation history for this user (last 10 exchanges)
        user_id = message.author.id
        if user_id not in self._conversation_history:
            # Bound the number of tracked users so history can't grow unbounded
            # (every distinct sender, including DMs, would otherwise persist forever).
            if len(self._conversation_history) >= 2000:
                self._conversation_history.pop(next(iter(self._conversation_history)), None)
            self._conversation_history[user_id] = []
        history = self._conversation_history[user_id]
        # Store only the raw question in history — NOT the full injected context.
        # Context (analytics, Drive folders, Patreon events) is fetched fresh each turn
        # and should not compound across turns. Storing full_prompt would make history
        # grow by ~50 KB per analytics exchange and eventually crash the API call.
        history_text = (f"[User shared {image_count} image(s)] " if image_count > 0 else "") + (question or "")
        history.append({"role": "user", "content": user_content if image_count > 0 else history_text.strip()})
        # Keep only last 10 messages to avoid token limits
        if len(history) > 10:
            history = history[-10:]
            self._conversation_history[user_id] = history

        # Build user identity context
        member_roles = [r.name for r in getattr(message.author, "roles", []) if r.name != "@everyone"]
        is_locodev = "LocoDev" in member_roles
        display_name = message.author.display_name

        _in_link_channel = message.channel.id == LINK_MANAGEMENT_CHANNEL_ID

        if is_locodev:
            user_context = (
                f"USER CONTEXT:\n"
                f"You are talking to LocoDev himself — the creator and owner of this server. "
                f"Treat him as your boss. Be direct, casual, and skip any generic intro. "
                f"He knows everything about the server, so don't explain basics to him.\n\n"
                f"GOOGLE DRIVE ACCESS:\n"
                f"When in the link management channel, you HAVE access to LocoDev's Google Drive project folders "
                f"via an injected context block titled '[Google Drive project folders ...]'. That list contains every "
                f"subfolder under his 'Locomotion Systems' Drive root, with names and shareable URLs. "
                f"If LocoDev asks you to 'check the drive', 'list the drive folders', or anything similar, just read "
                f"that list and answer with what's in it. NEVER say 'I don't have access to Drive' — you DO have access "
                f"through that injected list whenever it's present.\n\n"
                f"IMPORTANT — URL SHORTENER ACTIONS:\n"
                f"You have the ability to actually create and delete short links on locodev.dev, "
                f"BUT ONLY when the conversation is in channel <#{LINK_MANAGEMENT_CHANNEL_ID}>. "
                f"{'You are currently IN that channel, so you may create links.' if _in_link_channel else f'You are NOT in that channel. If asked to create or edit links, tell the user to go to <#{LINK_MANAGEMENT_CHANNEL_ID}> to manage links.'}\n"
                f"When in the link management channel and LocoDev wants to create a short link, respond with EXACTLY this format on its own line:\n"
                f"[CREATE_LINK: prefix/slug → destination_url]\n"
                f"Example: [CREATE_LINK: download/ragdollbasic → https://drive.google.com/...]\n"
                f"For root links (no prefix): [CREATE_LINK: root/slug → url]\n"
                f"IMPORTANT SLUG RULES:\n"
                f"1. Before picking a slug, check the existing links list provided in context.\n"
                f"2. Never reuse an existing slug — if /p/obstacleavoidance exists, use /p/obstacleavoidance-yt or similar.\n"
                f"3. Keep slugs short, lowercase, no spaces (use hyphens).\n"
                f"4. If the slug you want is taken, tell LocoDev and suggest alternatives.\n"
                f"5. CRITICAL — `download/` links: ONLY provide the base slug (e.g. `download/weaponstandard`). "
                f"Do NOT append a Mega ID, hash, or random string yourself. The system automatically appends a random "
                f"unguessable suffix for `download/` links so the final URL becomes `download/weaponstandard/<random>`. "
                f"Emitting `[CREATE_LINK: download/weaponstandard → ...]` is correct; emitting "
                f"`[CREATE_LINK: download/weaponstandard/2EZwiLCL → ...]` is WRONG.\n"
                f"6. DRIVE AUTO-FILL — When creating a `download/` link and no URL is provided, check the "
                f"'Google Drive project folders' list in context. Find the folder whose name best matches what "
                f"LocoDev asked for (fuzzy: ignore case, spaces, and words like System/Standard/Premium/Basic). "
                f"Use that folder's URL directly in the [CREATE_LINK] marker. "
                f"If no match exists in the list, ask LocoDev for the URL.\n"
                f"DO NOT say 'I can't create links' or 'you need to do this manually' or 'use the slash command'. "
                f"All prefixes including `download/`, `docs/`, `free/`, `freebuild/` are fine for LocoDev to create via chat — just emit the marker. "
                f"Just output the CREATE_LINK marker and it will be executed automatically.\n"
                f"CRITICAL: NEVER announce the short URL in your response text. Do NOT say 'Done!', 'link is ready', or write out the locodev.dev/... URL. "
                f"Only output the [CREATE_LINK] marker — the system will post the confirmation automatically."
            )
        else:
            roles_str = ", ".join(member_roles) if member_roles else "no special roles"
            user_context = (
                f"USER CONTEXT:\n"
                f"You are talking to **{display_name}**, a community member.\n"
                f"Their Discord roles: {roles_str}.\n"
                f"Use this to tailor your response — e.g. LocoPremium members have full access, "
                f"LocoBasic/LocoStandard have limited access, members with no tier are free users."
            )

        async with message.channel.typing():
            try:
                import anthropic as _anthropic
                loop = asyncio.get_event_loop()
                # Prior exchanges use compact history (raw questions); the current
                # turn uses the full context-injected prompt so Claude has all data.
                current_content = user_content if image_count > 0 else (full_prompt or question or "")
                msgs = list(history[:-1]) + [{"role": "user", "content": current_content}]
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
                            "If you don't know the answer, say so honestly and suggest contacting LocoDev.\n\n"
                            f"{user_context}"
                        ),
                        messages=msgs
                    )
                    return resp.content[0].text
                answer = await loop.run_in_executor(None, _ask)

                # Execute any [CREATE_LINK: prefix/slug → url] markers in Claude's response
                import re as _cre
                from urllib.parse import urlparse as _ulp
                _cl_matches = _cre.findall(r'\[CREATE_LINK:\s*([^\s→]+)\s*[→>]+\s*(https?://[^\]]+)\]', answer)
                _link_results = []
                # Author check: only the server owner can drive link mutations via chat.
                # Without this, anyone in the link channel could prompt-inject Claude into
                # emitting a [CREATE_LINK] marker that the bot would execute.
                if _cl_matches and not (bool(OWNER_DISCORD_ID) and message.author.id == OWNER_DISCORD_ID):
                    _link_results.append(
                        "🔒 Only the server owner can create links via chat. Use `/shorten` instead."
                    )
                    logger.warning("Blocked CREATE_LINK from non-owner %s", message.author.id)
                    _cl_matches = []
                if _cl_matches and not _in_link_channel:
                    _link_results.append(
                        f"🔒 Link management is only allowed in <#{LINK_MANAGEMENT_CHANNEL_ID}>."
                    )
                    _cl_matches = []
                for _cl_path, _cl_url in _cl_matches:
                    _cl_url = _cl_url.strip()
                    _cl_path = _cl_path.strip().strip("/")
                    if "/" in _cl_path:
                        _cl_pfx, _cl_slg = _cl_path.split("/", 1)
                    else:
                        _cl_pfx, _cl_slg = "root", _cl_path
                    # Protected prefixes (download/docs/freebuild/free) are owner-only;
                    # the author check above already guarantees that, so no extra block needed.
                    # Auto-append random suffix for obscured prefixes (e.g. download/)
                    if _cl_pfx in _OBSCURED_PREFIXES and "/" not in _cl_slg:
                        _cl_slg = f"{_cl_slg}/{_random_slug_suffix()}"
                    # Security: domain allowlist for all chat-created links
                    try:
                        _cl_domain = _ulp(_cl_url).netloc.lower()
                        if _cl_domain.startswith("www."):
                            _cl_domain = _cl_domain[4:]
                        _cl_domain = _cl_domain.split(":")[0]
                        _all_domains = _ALLOWED_DOWNLOAD_DOMAINS | {"patreon.com", "youtube.com", "youtu.be"}
                        if not any(_cl_domain == _d or _cl_domain.endswith("." + _d) for _d in _all_domains):
                            _link_results.append(f"🚫 Domain `{_cl_domain}` not on trusted list. Link not created.")
                            logger.warning("Blocked CREATE_LINK — untrusted domain: %s", _cl_domain)
                            continue
                    except Exception:
                        pass
                    try:
                        from shortener import create_link as _cl_create, update_link as _cl_update, get_link as _cl_get
                        _cl_ok = _cl_create(_cl_slg, _cl_url, _cl_pfx)
                        if not _cl_ok:
                            _cl_update(_cl_slg, _cl_url, _cl_pfx)
                        _cl_verify = _cl_get(_cl_slg, _cl_pfx)
                        _cl_short = f"locodev.dev/{_cl_pfx}/{_cl_slg}" if _cl_pfx != "root" else f"locodev.dev/{_cl_slg}"
                        if _cl_verify:
                            _audit_link_change(
                                "create" if _cl_ok else "update",
                                message.author.id, str(message.author),
                                _cl_pfx, _cl_slg, _cl_url,
                            )
                            _link_results.append(f"✅ {'Created' if _cl_ok else 'Updated'}: `{_cl_short}` → {_cl_verify['url']}")
                            logger.info("Auto-created link: %s → %s", _cl_short, _cl_url)
                        else:
                            _link_results.append(f"❌ Failed to save `{_cl_short}`")
                    except Exception as _cle:
                        _link_results.append(f"❌ Error: {_cle}")
                        logger.error("CREATE_LINK execution error: %s", _cle)
                # Strip the markers from the displayed answer
                answer = _cre.sub(r'\[CREATE_LINK:[^\]]+\]\n?', '', answer).strip()

                # If Claude emitted only the marker (no surrounding text), the link
                # results become the user-visible reply — otherwise message.reply("")
                # would 400 and the link confirmation would never get sent.
                if not answer:
                    if _link_results:
                        answer = "\n".join(_link_results)
                        _link_results = []
                    else:
                        answer = "✅ Done."

                # Store bot reply in history
                self._conversation_history[user_id].append({"role": "assistant", "content": answer})
                if len(answer) <= 1900:
                    await message.reply(answer)
                else:
                    await message.reply(answer[:1900])
                    remainder = answer[1900:]
                    if remainder.strip():
                        await message.channel.send(remainder)
                # Send link creation results as follow-up (only if not already consumed above)
                if _link_results:
                    await message.channel.send("\n".join(_link_results))
                # NOTE: KB-entry images are intentionally NOT auto-posted here.
                # The fuzzy KB match often pulled in loosely-related entries — and
                # their stored images included the original asker's screenshots — so
                # the bot tacked a random, unrelated image onto nearly every answer.
                # Claude still receives the image URLs inside kb_context and can link
                # one itself when it's genuinely relevant.
            except Exception as exc:
                logger.warning("AI responder error: %s", exc, exc_info=True)
                if _is_owner:
                    await message.reply(f"⚠️ Error: `{type(exc).__name__}: {exc}`")
                else:
                    await message.reply("Sorry, I couldn't process your question right now. Try again! 🙏")


# Dedup cache: (member_id, event) -> timestamp, to avoid duplicate announcements
_patreon_event_cache: dict[tuple, float] = {}
_PATREON_DEDUP_SECONDS = 30

# Persistent webhook idempotency — hash of body → ingestion timestamp
_WEBHOOK_SEEN_PATH = "/app/data/patreon_webhook_seen.json"
_webhook_seen_hashes: dict | None = None  # lazily loaded
_WEBHOOK_STARTUP_TIME = datetime.now(timezone.utc)  # module-level datetime/timezone already imported
_WEBHOOK_STARTUP_GRACE_SECS = 90  # first 90s after boot: log but don't announce / pushover
_HISTORICAL_CANCEL_DAYS = 60  # pledge:delete with last_charge_date older than this is skipped

def _load_webhook_seen() -> dict:
    """Load persistent webhook hash dedup file, pruning entries older than 30 days."""
    try:
        from datetime import timezone as _tz
        with open(_WEBHOOK_SEEN_PATH) as _f:
            _data = json.load(_f)
        _cutoff = (datetime.now(_tz.utc) - timedelta(days=30)).isoformat()
        return {k: v for k, v in _data.items() if v >= _cutoff}
    except Exception:
        return {}

def _save_webhook_seen(seen: dict) -> None:
    try:
        _atomic_write_json(_WEBHOOK_SEEN_PATH, seen)
    except Exception as _exc:
        logger.warning("Could not save webhook seen file: %s", _exc)

# ── Knowledge Base ──────────────────────────────────────────────────────────
_KB_PATH = "/app/data/knowledge_base.json"
_KB_APPROVE_EMOJI = "✅"

def _kb_load() -> list[dict]:
    try:
        with open(_KB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _kb_save(entries: list[dict]) -> None:
    _atomic_write_json(_KB_PATH, entries)

def _kb_add(question: str, answer: str, author: str, images: list[str] | None = None) -> None:
    entries = _kb_load()
    # Avoid duplicates
    for e in entries:
        if e["question"].strip().lower() == question.strip().lower():
            return
    entry: dict = {
        "question": question.strip(),
        "answer": answer.strip(),
        "author": author,
        "ts": datetime.utcnow().isoformat(),
    }
    if images:
        entry["images"] = images
    entries.append(entry)
    _kb_save(entries)
    logger.info("KB: saved Q&A — %s (%d images)", question[:60], len(images or []))

def _kb_search(query: str, top_n: int = 3) -> list[dict]:
    """Simple keyword search over the knowledge base."""
    entries = _kb_load()
    query_words = set(query.lower().split())
    scored = []
    for e in entries:
        q_words = set(e["question"].lower().split())
        score = len(query_words & q_words)
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_n]]

_KB_STOPWORDS = {
    "i", "a", "an", "the", "is", "it", "in", "of", "to", "my", "me",
    "do", "can", "be", "for", "how", "what", "where", "when", "why",
    "who", "will", "are", "have", "has", "was", "not", "that", "this",
    "on", "at", "by", "or", "and", "but", "if", "as", "with", "from",
    "any", "you", "your", "we", "they", "their", "there", "just", "im",
    "i'm", "its", "it's", "get", "got", "so", "up", "out", "about",
    "also", "some", "all", "no", "need", "want", "like", "more",
}
_KB_QUESTION_STARTERS = {
    "how", "what", "why", "where", "when", "can", "could", "does", "do",
    "is", "are", "will", "would", "should", "which", "who", "any",
    "help", "having", "having", "getting", "trying", "unable",
}

def _looks_like_question(text: str) -> bool:
    """Return True if text is plausibly a question or support request."""
    if "?" in text:
        return True
    words = text.lower().split()
    return bool(words) and words[0] in _KB_QUESTION_STARTERS and len(words) >= 4

def _kb_search_scored(query: str, top_n: int = 3, min_score: int = 1) -> list[tuple[int, dict]]:
    """Like _kb_search but filters stopwords, returns (score, entry) pairs, min_score enforced."""
    entries = _kb_load()
    query_words = {w.strip("?.,!") for w in query.lower().split()
                   if w not in _KB_STOPWORDS and len(w) > 2}
    if not query_words:
        return []
    scored = []
    for e in entries:
        q_words = {w for w in e["question"].lower().split()
                   if w not in _KB_STOPWORDS and len(w) > 2}
        score = len(query_words & q_words)
        if score >= min_score:
            scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]

# ── Event trackers for scheduled summaries ──────────────────────────────────
_EVENTS_LOG_PATH = "/app/data/patreon_events.json"

def _load_events() -> list[dict]:
    """Load persisted events, dropping entries older than 90 days."""
    from datetime import timezone
    try:
        with open(_EVENTS_LOG_PATH, "r") as f:
            events = json.load(f)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        return [e for e in events if e.get("ts", "") >= cutoff]
    except Exception:
        return []

def _save_events(events: list[dict]) -> None:
    try:
        _atomic_write_json(_EVENTS_LOG_PATH, events)
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
    logger.info("Patreon webhook received: event=%s has_sig=%s body_len=%d",
                request.headers.get("X-Patreon-Event", ""), bool(sig), len(body))
    # Fail CLOSED: if no secret is configured the endpoint is unauthenticated,
    # and this handler grants/strips paid Discord roles from the request body.
    # Refuse to process anything unless we can verify the HMAC signature.
    if not PATREON_WEBHOOK_SECRET:
        logger.error("Patreon webhook rejected: PATREON_WEBHOOK_SECRET is not set")
        return web.Response(status=503, text="Webhook not configured")
    if not sig:
        return web.Response(status=403, text="Missing signature")
    expected = hmac.new(PATREON_WEBHOOK_SECRET.encode(), body, hashlib.md5).hexdigest()
    if not hmac.compare_digest(sig, expected):
        logger.warning("Patreon webhook signature mismatch")
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
    # Use currently_entitled_amount_cents for free trial detection (can be 0 for trials)
    # will_pay_amount_cents is the future amount — don't use it to override 0
    _entitled = attrs.get("currently_entitled_amount_cents")
    _will_pay = attrs.get("will_pay_amount_cents")
    amount_cents = _entitled if _entitled is not None else (_will_pay or 0)
    lifetime_cents = attrs.get("lifetime_support_cents") or 0
    is_returning = lifetime_cents > amount_cents
    trial_ends_at = attrs.get("trial_ends_at")
    is_free_trial = bool(trial_ends_at) and amount_cents == 0

    # --- Persistent idempotency by body hash (survives restarts) ---
    global _webhook_seen_hashes
    if _webhook_seen_hashes is None:
        _webhook_seen_hashes = _load_webhook_seen()
    body_hash = hashlib.sha256(body).hexdigest()
    if body_hash in _webhook_seen_hashes:
        logger.info(
            "Skipping already-processed webhook hash=%s event=%s name=%s",
            body_hash[:12], event, full_name,
        )
        return web.Response(status=200, text="OK (duplicate body)")
    from datetime import timezone as _tz
    _webhook_seen_hashes[body_hash] = datetime.now(_tz.utc).isoformat()
    # Prune entries older than 30 days occasionally (load also prunes on read)
    if len(_webhook_seen_hashes) % 10 == 0:
        _cutoff_30d = (datetime.now(_tz.utc) - timedelta(days=30)).isoformat()
        _webhook_seen_hashes = {k: v for k, v in _webhook_seen_hashes.items() if v >= _cutoff_30d}
    _save_webhook_seen(_webhook_seen_hashes)

    # --- Historical cancellation filter ---
    # For pledge:delete, if last_charge_date is very old, the cancellation is
    # historical cleanup (Patreon retrying or replaying an old event), not a
    # fresh cancel. Skip entirely — don't log, don't announce.
    if event == "members:pledge:delete":
        _lcd = attrs.get("last_charge_date")
        if _lcd:
            try:
                _lc = datetime.fromisoformat(_lcd.replace("Z", "+00:00"))
                _age_days = (datetime.now(timezone.utc) - _lc).days
                if _age_days > _HISTORICAL_CANCEL_DAYS:
                    logger.info(
                        "Skipping historical cancellation for %s (last_charge_date=%s, %d days ago)",
                        full_name, _lcd, _age_days,
                    )
                    return web.Response(status=200, text="OK (historical)")
            except Exception as _te:
                logger.warning("Could not parse last_charge_date '%s': %s", _lcd, _te)

    # --- Startup grace period ---
    # If a flood of webhooks arrives in the first 90s after boot, it's almost
    # certainly Patreon's retry queue flushing. Log them (and record the hash
    # so later retries are deduped) but do NOT announce or pushover.
    _boot_age = (datetime.now(timezone.utc) - _WEBHOOK_STARTUP_TIME).total_seconds()
    _in_startup_grace = _boot_age < _WEBHOOK_STARTUP_GRACE_SECS
    if _in_startup_grace:
        logger.info(
            "Webhook in startup grace (%.0fs of %ds), logging but not announcing: event=%s name=%s",
            _boot_age, _WEBHOOK_STARTUP_GRACE_SECS, event, full_name,
        )

    # In-memory dedup (belt-and-suspenders short-window guard)
    cache_key = (member_id, event)
    now = time.monotonic()
    dedup_seconds = 21600 if event in ("members:update", "members:pledge:create", "members:pledge:delete") else 30
    if now - _patreon_event_cache.get(cache_key, 0) < dedup_seconds:
        logger.info("Skipping duplicate Patreon event %s for %s", event, member_id)
        return web.Response(status=200, text="OK")
    _patreon_event_cache[cache_key] = now
    # Evict entries older than the longest dedup window so the cache can't grow
    # without bound (member_id/event come from the request).
    if len(_patreon_event_cache) > 512:
        _evict_before = now - 21600
        for _k in [k for k, t in _patreon_event_cache.items() if t < _evict_before]:
            _patreon_event_cache.pop(_k, None)

    # Track event for daily and weekly summaries
    from datetime import timezone as _tz
    _entry = {
        "event": event,
        "name": full_name,
        "member_id": member_id,
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
    _entry["is_trial"] = is_free_trial
    if is_free_trial and trial_ends_at:
        _entry["trial_ends_at"] = trial_ends_at

    # Detect trial conversion: paid pledge from someone who had a prior trial in the log
    if event == "members:pledge:create" and not is_free_trial and amount_cents > 0 and member_id:
        prior = _load_events()
        had_trial = any(
            e.get("member_id") == member_id and e.get("is_trial") is True
            for e in prior
        )
        if had_trial:
            _entry["is_trial_conversion"] = True

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

    if event == "members:pledge:create" and is_free_trial:
        trial_tier = tier_title or "LocoBasic"
        msg = f"🆓 {name} started a **free trial** of **{trial_tier}**!{returning_str}"
    elif event == "members:create":
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

    # --- Assign/remove Discord tier roles based on event ---
    _tier_roles = ["LocoBasic", "LocoStandard", "LocoPremium"]
    if discord_id:
        guild = client.get_guild(int(GUILD_ID))
        if guild:
            try:
                member = guild.get_member(int(discord_id)) or await guild.fetch_member(int(discord_id))
                if member:
                    if event in ("members:pledge:create", "members:pledge:update") and tier_title in _tier_roles:
                        # New sub or tier change — assign correct role
                        roles_to_remove = [r for r in member.roles if r.name in _tier_roles and r.name != tier_title]
                        if roles_to_remove:
                            await member.remove_roles(*roles_to_remove, reason="Patreon tier update")
                        role = discord.utils.get(guild.roles, name=tier_title)
                        if role and role not in member.roles:
                            await member.add_roles(role, reason=f"Patreon {event}")
                            logger.info("Assigned role '%s' to patreon member %s", tier_title, member_id)
                    elif event == "members:update" and attrs.get("patron_status") == "active_patron" and tier_title in _tier_roles:
                        # Payment received — ensure they still have the correct role
                        role = discord.utils.get(guild.roles, name=tier_title)
                        if role and role not in member.roles:
                            roles_to_remove = [r for r in member.roles if r.name in _tier_roles and r.name != tier_title]
                            if roles_to_remove:
                                await member.remove_roles(*roles_to_remove, reason="Patreon payment confirmed")
                            await member.add_roles(role, reason="Patreon payment confirmed")
                            logger.info("Re-assigned role '%s' to patreon member %s after payment", tier_title, member_id)
                    elif event == "members:pledge:delete":
                        # Cancelled — remove all tier roles
                        roles_to_remove = [r for r in member.roles if r.name in _tier_roles]
                        if roles_to_remove:
                            await member.remove_roles(*roles_to_remove, reason="Patreon cancelled")
                            logger.info("Removed tier roles from patreon member %s — cancelled", member_id)
            except discord.NotFound:
                logger.warning("Discord member %s not found in guild for role assignment", discord_id)
            except Exception as _re:
                logger.warning("Failed to assign role for %s: %s", discord_id, _re)

    if msg and not _in_startup_grace:
        # Send full message to #bot-reports
        try:
            channel = client.get_channel(PATREON_ANNOUNCEMENT_CHANNEL_ID) or await client.fetch_channel(PATREON_ANNOUNCEMENT_CHANNEL_ID)
            await channel.send(msg)
            logger.info("Posted Patreon announcement: %s", msg)
        except Exception as _ce:
            logger.warning("Could not send to announcement channel %s: %s", PATREON_ANNOUNCEMENT_CHANNEL_ID, _ce)

    # Pushover notification for payment events (skip free trials and startup grace)
    logger.info("Patreon webhook processed: event=%s name=%s amount=%s is_free_trial=%s", event, full_name, amount_cents, is_free_trial)
    if _in_startup_grace:
        return web.Response(status=200, text="OK (startup grace)")
    if event == "members:pledge:create" and not is_free_trial and _entry.get("is_trial_conversion"):
        await _send_pushover(
            title=f"🔄 Trial Converted — ${dollars:.2f}/month",
            message=f"{full_name} converted from free trial to {tier_title or 'paid'} on Patreon!",
            sound="cashregister",
        )
    elif event == "members:pledge:create" and not is_free_trial:
        await _send_pushover(
            title=f"💰 New Patron — ${dollars:.2f}/month",
            message=f"{full_name} joined {tier_title or 'LocoDev'} on Patreon!",
            sound="cashregister",
        )
    elif event == "members:pledge:create" and is_free_trial:
        await _send_pushover(
            title=f"🆓 Free Trial — {tier_title or 'LocoBasic'}",
            message=f"{full_name} started a free trial on Patreon.",
            sound="none",
        )
    elif event == "members:pledge:update" and amount_cents > 0:
        await _send_pushover(
            title=f"⬆️ Tier Upgrade — ${dollars:.2f}/month",
            message=f"{full_name} upgraded to {tier_title or 'a new tier'} on Patreon.",
            sound="cashregister",
        )
    elif event == "members:update" and attrs.get("patron_status") == "active_patron":
        await _send_pushover(
            title=f"✅ Payment received — ${dollars:.2f}",
            message=f"{full_name} ({tier_title or 'patron'}) payment successful.",
            sound="cashregister",
        )

    return web.Response(status=200, text="OK")


async def start_webhook_server():
    from aiohttp import web
    from shortener import setup_routes as setup_shortener_routes
    from admin_panel import setup_admin_routes
    app = web.Application()
    app.router.add_post("/patreon/webhook", patreon_webhook_handler)
    # Admin routes must be registered before shortener catch-all routes
    setup_admin_routes(app, ADMIN_SECRET)
    setup_shortener_routes(app)
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
        # Ensure all links from CSV are imported (safe to re-run, skips existing)
        try:
            from migrate_dub import migrate
            import os
            csv_path = os.path.join(os.path.dirname(__file__), "dub_links.csv")
            if os.path.exists(csv_path):
                logger.info("Running link migration from CSV...")
                migrate(csv_path)
                logger.info("Link migration complete.")
        except Exception as e:
            logger.warning("Dub migration skipped: %s", e)

        # ── One-time link URL patches (safe to run on every boot — idempotent) ──
        try:
            from shortener import update_link as _patch_link
            _link_patches = [
                # (slug, prefix, new_url)
                ("uecourse", "p", "https://blueprint.locodev.dev/?utm_source=youtube&utm_medium=organic_video&utm_campaign=leads_abril"),
            ]
            for _slug, _prefix, _new_url in _link_patches:
                if _patch_link(_slug, _new_url, _prefix):
                    logger.info("Link patch applied: %s/%s → %s", _prefix, _slug, _new_url)
                else:
                    logger.warning("Link patch failed (slug not found?): %s/%s", _prefix, _slug)
        except Exception as _pe:
            logger.warning("Link patches error: %s", _pe)

        # ── Startup link deletions (disabled/retired links) ──────────────────
        try:
            from shortener import delete_link as _del_link
            _link_deletes = [
                # (slug, prefix) — links that should no longer be active
                ("walkonbeamstandard/i7IpRzN1",     "download"),
                ("slidingstandard/YKZu5AFj",         "download"),
                ("slidingpremium/R6jcCKTp",          "download"),
                ("slidingbasic/QIkpihi5",            "download"),
                ("ziplinebasic/zxsjJboA",            "download"),
                ("pushpullstandard/N77kqqbI",        "download"),
                ("rollpickupbasic/ZuxuEkmT",         "download"),
                ("falldamagestandard/ZqOiMdHG",      "download"),
                ("dynamicfootstepsbasic/FY2JsdbM",   "download"),
                ("telekinesisbasic/in9ReCom",        "download"),
                ("hostagesystembasic/6oBef2f5",      "download"),
                ("hangswingbasic/iVxKADv8",          "download"),
                ("vaultsystemstandard/grg5nv2J",     "download"),
                ("hangsswingstandard/OZV1moOY",      "download"),
                ("motionmatchingbasic/g6rDdbyO",     "download"),
            ]
            for _slug, _prefix in _link_deletes:
                if _del_link(_slug, _prefix):
                    logger.info("Link disabled: %s/%s", _prefix, _slug)
        except Exception as _de:
            logger.warning("Link deletes error: %s", _de)
        await client.start(TOKEN)

    asyncio.run(main())
