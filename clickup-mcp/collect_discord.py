#!/usr/bin/env python3
"""Pull questions from the Discord support channels into the vault.

Discord was the blind channel: a question there became an ephemeral alert
and the history lived only in RAM, so nothing reached the panel and nothing
survived a bot restart. This reads the channels over the REST API with the
bot's own token and files each question in the same block format the
YouTube collector uses, so one inbox holds both.

Answered is decided the same way it is for YouTube: a question counts as
answered when someone on staff replied to it, and that reply is stored
alongside the question so it becomes searchable knowledge like the rest.

Backfill and incremental in one pass: the first run walks each channel's
whole history, later runs only ask for messages after the last id it saw,
which is what makes a fifteen minute schedule cheap.

Usage:
    python collect_discord.py --dry-run
    python collect_discord.py
    python collect_discord.py --full        re-walk the whole history
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

VAULT = Path(r"F:\LocoDev Vault")
STATE_PATH = BASE_DIR / ".discord_state.json"
API = "https://discord.com/api/v10"
INBOX_NAME = "03 - From Discord.md"

# The channels asked for, overridable without touching the code.
DEFAULT_CHANNELS = "1158395982485147692,1460338435163164827,1158461639197216768"

MIN_QUESTION_LEN = 25
QUESTION_WORDS = (
    "how", "what", "why", "where", "when", "which", "who", "can", "does",
    "do", "is", "are", "should", "would", "could", "any", "anyone", "help",
    "problem", "issue", "error", "bug", "possible",
)


def _headers() -> dict:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    return {
        "Authorization": f"Bot {token}",
        "User-Agent": "LocoDevPanel (https://locodev.dev, 1.0)",
        "Content-Type": "application/json",
    }


def api_get(path: str, params: dict | None = None, tries: int = 4):
    """One REST call, honouring Discord's rate limit headers."""
    url = API + path + ("?" + parse.urlencode(params) if params else "")
    for attempt in range(tries):
        req = request.Request(url, headers=_headers())
        try:
            with request.urlopen(req, timeout=20) as resp:
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining == "0":
                    time.sleep(float(resp.headers.get("X-RateLimit-Reset-After", 1)))
                return json.load(resp)
        except error.HTTPError as exc:
            if exc.code == 429:
                body = {}
                try:
                    body = json.load(exc)
                except ValueError:
                    pass
                time.sleep(float(body.get("retry_after", 2)) + 0.5)
                continue
            if exc.code in (403, 404):
                # Missing access or a deleted channel: report it, do not retry.
                raise
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
        except error.URLError:
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass


def looks_like_question(text: str) -> bool:
    t = " ".join(text.split()).lower()
    if len(t) < MIN_QUESTION_LEN:
        return False
    if "?" in t:
        return True
    return any(t.startswith(w + " ") for w in QUESTION_WORDS)


def fetch_messages(channel_id: str, after: str | None, hard_cap: int) -> list[dict]:
    """Newest-first history, or everything after a known id."""
    out: list[dict] = []
    if after:
        cursor = after
        while len(out) < hard_cap:
            batch = api_get(f"/channels/{channel_id}/messages",
                            {"limit": 100, "after": cursor})
            if not batch:
                break
            batch.sort(key=lambda m: int(m["id"]))
            out.extend(batch)
            cursor = batch[-1]["id"]
            if len(batch) < 100:
                break
    else:
        before = None
        while len(out) < hard_cap:
            params = {"limit": 100}
            if before:
                params["before"] = before
            batch = api_get(f"/channels/{channel_id}/messages", params)
            if not batch:
                break
            out.extend(batch)
            before = batch[-1]["id"]
            if len(batch) < 100:
                break
    return out


FORUM_TYPES = (15, 16)   # forum and media channels hold no messages of their own


def channel_info(channel_id: str) -> dict:
    try:
        return api_get(f"/channels/{channel_id}")
    except Exception:  # noqa: BLE001 - a missing name is cosmetic
        return {}


def forum_threads(channel_id: str, guild_id: str) -> list[dict]:
    """Every thread under a forum channel, open and archived.

    A forum channel returns nothing from the messages endpoint: the posts
    are threads hanging off it, and each thread's first message is the
    question. Reading only the channel silently missed the entire support
    forum, which is exactly where the questions worth collecting live.
    """
    threads: dict[str, dict] = {}
    if guild_id:
        try:
            for t in api_get(f"/guilds/{guild_id}/threads/active").get("threads", []):
                if str(t.get("parent_id")) == str(channel_id):
                    threads[t["id"]] = t
        except Exception:  # noqa: BLE001
            pass
    # Archived posts are the bulk of any support forum's history.
    before = None
    while True:
        params = {"limit": 100}
        if before:
            params["before"] = before
        try:
            page = api_get(f"/channels/{channel_id}/threads/archived/public", params)
        except Exception:  # noqa: BLE001
            break
        batch = page.get("threads", [])
        for t in batch:
            threads[t["id"]] = t
        if not page.get("has_more") or not batch:
            break
        before = batch[-1].get("thread_metadata", {}).get("archive_timestamp")
        if not before:
            break
    return list(threads.values())


def channel_name(channel_id: str) -> str:
    try:
        return api_get(f"/channels/{channel_id}").get("name", channel_id)
    except Exception:  # noqa: BLE001 - a name is cosmetic, never fatal
        return channel_id


def staff_ids(guild_id: str) -> set[str]:
    """Whoever counts as an official answer: the configured staff, plus the
    guild owner, so a fresh install still recognises your own replies."""
    ids = {i.strip() for i in os.getenv("DISCORD_STAFF_IDS", "").split(",") if i.strip()}
    if guild_id:
        try:
            ids.add(str(api_get(f"/guilds/{guild_id}").get("owner_id", "")))
        except Exception:  # noqa: BLE001
            pass
    return {i for i in ids if i}


def build_index(messages: list[dict]) -> dict:
    return {m["id"]: m for m in messages}


def find_answer(msg: dict, messages: list[dict], staff: set[str]) -> dict | None:
    """A staff reply pointing at this message, if there is one."""
    for other in messages:
        ref = other.get("message_reference") or {}
        if ref.get("message_id") != msg["id"]:
            continue
        author = str((other.get("author") or {}).get("id", ""))
        if author in staff:
            return other
    return None


def existing_sources(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return set(re.findall(r"^source:\s*(\S+)", path.read_text(encoding="utf-8",
                                                              errors="replace"), re.M))


def write_inbox(rows: list[dict], dry: bool) -> int:
    path = VAULT / "Inbox" / INBOX_NAME
    seen = existing_sources(path)
    fresh = [r for r in rows if r["source"] not in seen]
    if not fresh:
        return 0

    blocks = []
    for r in fresh:
        reply_line = f"reply: {r['reply']}\n" if r.get("reply") else ""
        blocks.append(
            f"\n### {r['date']} {r['author']}\n"
            f"channel: discord\n"
            f"system: -\n"
            f"status: {r['status']}\n"
            f"subscriber: unknown\n"
            f"source: {r['source']}\n"
            f"thread: {r['thread'] or ('#' + r['channel_name'])}\n"
            f"url: {r['url']}\n"
            f"{reply_line}\n"
            f"{r['text'][:1200]}\n"
        )

    if not path.is_file():
        header = (
            "---\ntags: [locodev, inbox, discord, generated]\n---\n\n"
            "# Questions from Discord\n\n"
            "Collected by `collect_discord.py` from the support channels. A "
            "question counts as answered when a staff member replied to it in "
            "Discord; that reply is kept here so it becomes searchable "
            "knowledge like every other answer.\n\n"
            "Appended only, never rewritten, so edits made from the panel "
            "survive the next run.\n\n---\n"
        )
        text = header + "".join(blocks)
    else:
        text = path.read_text(encoding="utf-8", errors="replace") + "".join(blocks)

    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return len(fresh)


def main() -> int:
    global VAULT

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--channels", default=os.getenv("DISCORD_CHANNEL_IDS", DEFAULT_CHANNELS))
    ap.add_argument("--full", action="store_true",
                    help="ignore the saved position and re-walk the history")
    ap.add_argument("--max-per-channel", type=int,
                    default=int(os.getenv("DISCORD_MAX_PER_CHANNEL", "3000")))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    VAULT = Path(args.vault)
    if not os.getenv("DISCORD_BOT_TOKEN", "").strip():
        print("ERROR: DISCORD_BOT_TOKEN is not set in clickup-mcp/.env")
        print("Use the same token the bot runs with (Railway > the bot service >")
        print("Variables > DISCORD_BOT_TOKEN). Reading needs no new bot.")
        return 1
    if not VAULT.is_dir():
        print(f"ERROR: vault not found at {VAULT}")
        return 1

    guild = os.getenv("DISCORD_GUILD_ID", "").strip()
    staff = staff_ids(guild)
    print(f"staff accounts recognised as an official answer: {len(staff)}")
    if not staff:
        print("  none: every question will be filed as unanswered until you set")
        print("  DISCORD_STAFF_IDS or DISCORD_GUILD_ID in .env")

    state = load_state() if not args.full else {}
    channels = [c.strip() for c in args.channels.split(",") if c.strip()]
    # The same id twice in the list is a typo, not two channels.
    channels = list(dict.fromkeys(channels))

    rows: list[dict] = []
    read = answered_n = 0
    t0 = time.time()

    for cid in channels:
        info = channel_info(cid)
        name = info.get("name", cid)
        is_forum = info.get("type") in FORUM_TYPES
        after = state.get(cid, {}).get("last_id") if not args.full else None

        # A forum is a list of posts, each its own thread; a text channel is
        # one stream. Both end up as (source id, thread label, messages).
        sources: list[tuple[str, str]] = []
        if is_forum:
            posts = forum_threads(cid, guild)
            sources = [(t["id"], t.get("name", "")) for t in posts]
            print(f"#{name}: forum with {len(sources)} posts")
        else:
            sources = [(cid, "")]

        messages: list[dict] = []
        thread_of: dict[str, str] = {}
        failed = False
        for sid, label in sources:
            try:
                # Only a text channel can resume from a saved position: a
                # forum post is short and cheap to re-read in full.
                got = fetch_messages(sid, after if not is_forum else None,
                                     args.max_per_channel)
            except error.HTTPError as exc:
                if not is_forum:
                    reason = ("the bot cannot see this channel (needs View "
                              "Channel and Read Message History)" if exc.code == 403
                              else "channel not found")
                    print(f"#{name} ({cid}): SKIPPED, {reason}")
                    failed = True
                continue
            except Exception as exc:  # noqa: BLE001 - one source must not end the run
                if not is_forum:
                    print(f"#{name} ({cid}): FAILED, {type(exc).__name__}")
                    failed = True
                continue
            for m in got:
                thread_of[m["id"]] = label
            messages.extend(got)
        if failed:
            continue

        read += len(messages)
        newest = max((int(m["id"]) for m in messages), default=None) if not is_forum else None
        found = 0
        for m in messages:
            author = m.get("author") or {}
            if author.get("bot"):
                continue
            if str(author.get("id", "")) in staff:
                continue          # a staff message is an answer, not a question
            text = " ".join((m.get("content") or "").split())
            if not looks_like_question(text):
                continue
            answer = find_answer(m, messages, staff)
            reply = " ".join((answer.get("content") or "").split())[:900] if answer else ""
            rows.append({
                "date": (m.get("timestamp") or "")[:10],
                "author": author.get("global_name") or author.get("username") or "unknown",
                "text": text,
                "status": "answered" if reply else "no-source",
                "reply": reply,
                "source": f"dc:{m['id']}",
                "channel_name": name,
                # A forum question belongs to its post, not to the forum, and
                # the link has to point at the post to be worth clicking.
                "thread": thread_of.get(m["id"], ""),
                "url": (f"https://discord.com/channels/{guild or '@me'}/"
                        f"{m.get('channel_id', cid)}/{m['id']}"),
            })
            found += 1
            if reply:
                answered_n += 1

        if newest and not args.dry_run:
            state[cid] = {"last_id": str(newest), "name": name,
                          "checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        print(f"#{name}: {len(messages)} messages read, {found} questions")

    added = write_inbox(rows, args.dry_run)
    if not args.dry_run:
        save_state(state)

    verb = "would be " if args.dry_run else ""
    print(f"\nmessages read: {read} \u00b7 questions found: {len(rows)} "
          f"({answered_n} already answered by staff)")
    print(f"{verb}added to the inbox: {added} (new ones only) \u00b7 "
          f"{time.time() - t0:.0f}s")
    if not read:
        print("\nNothing came back. If the channels are right, the usual cause is")
        print("the Message Content intent being off: Discord Developer Portal >")
        print("your app > Bot > Privileged Gateway Intents > Message Content.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
