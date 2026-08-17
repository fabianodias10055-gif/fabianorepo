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


try:
    from secrets_store import get_secret
except ImportError:                      # standalone copy without the module
    def get_secret(name: str, default: str = "") -> str:
        return os.getenv(name, default)

VAULT = Path(r"F:\LocoDev Vault")
STATE_PATH = BASE_DIR / ".discord_state.json"
API = "https://discord.com/api/v10"
INBOX_NAME = "03 - From Discord.md"

# The channels asked for, overridable without touching the code.
# Every channel where a question can land. general-support was missing
# from the first list and is the busiest of them: the channel topic
# literally invites people to post their problem there.
DEFAULT_CHANNELS = ",".join((
    "1158395982485147692",   # general-chat
    "1459914723330883727",   # general-support
    "1460338435163164827",   # support-hub (forum)
    "1160715880787869729",   # patreon-support
    "1158461639197216768",   # blueprint-tips
    "1481100889757581434",   # mover-tips
    "1230971979515826277",   # cpp-tips
    "1158854094597935155",   # als-coding-tips
    "1158414318975582309",   # funny-bugs
    # People ask real questions here between the greetings, and it is the
    # one place the bot cannot be relied on to catch them: a question sent
    # while the bot is restarting is never delivered to it, and this poll is
    # what finds it afterwards.
    "1158395982485147689",   # welcome
    # The one channel the bot answers in and this collector did not read.
    # With the bot's live AI reply off, a question typed here would have
    # reached nobody: not answered, not collected, and the escalation only
    # reaches the alert channel, not the panel's queue.
    "1499029543078465696",   # backup
))

MIN_QUESTION_LEN = 25
QUESTION_WORDS = (
    "how", "what", "why", "where", "when", "which", "who", "can", "does",
    "do", "is", "are", "should", "would", "could", "any", "anyone", "help",
    "problem", "issue", "error", "bug", "possible",
)


def _headers() -> dict:
    token = get_secret("DISCORD_BOT_TOKEN")
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


_MENTION = re.compile(r"<@!?(\d+)>")
_ROLE = re.compile(r"<@&(\d+)>")
_CHAN = re.compile(r"<#(\d+)>")
_EMOJI = re.compile(r"<a?:(\w+):\d+>")
_name_cache: dict[str, str] = {}


def resolve_mentions(text: str, msg: dict | None = None) -> str:
    """Turn <@690691536983425044> into @name.

    A raw id tells the reader nothing and tells a model even less: it cannot
    know whether the person was addressing the creator or another member.
    The message carries the mentioned users, so most resolve for free; the
    rest are looked up once and remembered.
    """
    for u in (msg or {}).get("mentions") or []:
        uid = str(u.get("id", ""))
        if uid:
            _name_cache[uid] = u.get("global_name") or u.get("username") or uid

    def user(m):
        uid = m.group(1)
        if uid not in _name_cache:
            try:
                u = api_get(f"/users/{uid}")
                _name_cache[uid] = u.get("global_name") or u.get("username") or uid
            except Exception:  # noqa: BLE001 - an unknown id stays an id
                _name_cache[uid] = uid
        return "@" + _name_cache[uid]

    text = _MENTION.sub(user, text)
    text = _ROLE.sub("@role", text)
    text = _CHAN.sub(lambda m: "#channel", text)
    return _EMOJI.sub(lambda m: ":" + m.group(1) + ":", text)


def _words(text: str) -> set:
    """Significant words, for the rough overlap checks in this module."""
    return {w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower())}


_SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def split_questions(text: str) -> list[str]:
    """One message, one entry per question asked in it.

    People stack two unrelated questions in a single message, and a single
    staff reply then marks the whole thing answered, which quietly buries
    the half nobody addressed. Each question becomes its own entry so each
    can be tracked, answered and closed on its own.

    Sentences that are not themselves questions ride along with the question
    they precede: "I bought the pack yesterday. How do I migrate it?" is one
    question with its context, not a fragment plus a question.
    """
    sentences = [x.strip() for x in _SENT.split(text) if x.strip()]
    if len(sentences) < 2:
        return [text]

    parts: list[list[str]] = []
    buf: list[str] = []
    for sent in sentences:
        buf.append(sent)
        if looks_like_question(sent) or sent.rstrip().endswith("?"):
            parts.append(buf)
            buf = []
    if buf:
        # Trailing context belongs to the question it follows.
        if parts:
            parts[-1].extend(buf)
        else:
            parts.append(buf)

    joined = [" ".join(p).strip() for p in parts]
    joined = [p for p in joined if len(p) >= MIN_QUESTION_LEN]
    # Splitting is only worth it when the pieces really are separate asks.
    if len(joined) < 2:
        return [text]
    return joined


def which_part_answered(parts: list[str], reply: str) -> int:
    """Which of the questions the staff reply actually addressed.

    A guess, and labelled as one: word overlap between the reply and each
    question. When nothing overlaps, the first is assumed, because a reply
    usually answers the thing asked first. Getting it wrong costs one click
    on Mark as answered or Reopen, which is the point of having those.
    """
    if not reply:
        return -1
    rw = _words(reply)
    best, score = 0, 0
    for i, p in enumerate(parts):
        pw = _words(p)
        overlap = len(rw & pw)
        if overlap > score:
            best, score = i, overlap
    return best


def author_handle(author: dict) -> str:
    """@handle, the way YouTube questions already read.

    Discord has two names: username, which is the unique handle you can
    actually mention or search for, and global_name, the display name that
    two people can share. The handle is what identifies the person; the
    display name goes in parentheses when it says something different.
    """
    handle = (author or {}).get("username") or ""
    shown = (author or {}).get("global_name") or ""
    if not handle:
        return shown or "unknown"
    if shown and shown.lower().replace(" ", "") != handle.lower().replace(".", ""):
        return f"@{handle} ({shown})"
    return f"@{handle}"


MEMBERS_NAME = "discord-members.json"
# Tier roles first: knowing someone is LocoPremium changes how a question
# is prioritised, and it is the one fact the message itself never carries.
ROLE_PRIORITY = ("LocoPremium", "LocoStandard", "LocoBasic", "LocoHelper",
                 "LocoTester", "LocoDev Team", "Patreon", "Content Creator")


def refresh_members(guild_id: str, vault: Path) -> int:
    """Snapshot every member's roles and avatar into Panel/.

    Roles change: someone upgrades a tier, someone lapses. The snapshot is
    rewritten on each collector run, so a fifteen minute schedule keeps the
    panel honest about who is a paying member today rather than who was one
    when the question was asked. Written under Panel/ because it is derived
    data the watcher deliberately ignores.
    """
    if not guild_id:
        return 0
    try:
        roles = {r["id"]: r["name"] for r in api_get(f"/guilds/{guild_id}/roles")}
    except Exception:  # noqa: BLE001
        return 0

    members: dict[str, dict] = {}
    after = None
    while True:
        params = {"limit": 1000}
        if after:
            params["after"] = after
        try:
            page = api_get(f"/guilds/{guild_id}/members", params)
        except Exception:  # noqa: BLE001 - a partial snapshot beats none
            break
        if not page:
            break
        for m in page:
            u = m.get("user") or {}
            uid = str(u.get("id", ""))
            if not uid:
                continue
            names = [roles.get(r) for r in (m.get("roles") or []) if roles.get(r)]
            # @everyone is on everyone and says nothing.
            names = [x for x in names if x and x != "@everyone"]
            names.sort(key=lambda x: (ROLE_PRIORITY.index(x)
                                      if x in ROLE_PRIORITY else 99, x))
            # A per-server avatar wins over the account one, which is what
            # the member actually looks like in this server.
            avatar = ""
            if m.get("avatar"):
                avatar = (f"https://cdn.discordapp.com/guilds/{guild_id}/users/"
                          f"{uid}/avatars/{m['avatar']}.png?size=64")
            elif u.get("avatar"):
                avatar = (f"https://cdn.discordapp.com/avatars/{uid}/"
                          f"{u['avatar']}.png?size=64")
            members[uid] = {
                # Kept in the record, not only as the key it is filed under:
                # Patreon publishes the Discord account a patron linked, and
                # that id is the only exact join between a paying customer
                # and the person asking questions in the server. Matching by
                # name instead would guess, and guessing about who paid is
                # not a thing to do.
                "id": uid,
                "handle": u.get("username", ""),
                "name": m.get("nick") or u.get("global_name") or u.get("username", ""),
                "roles": names,
                "avatar": avatar,
                "joined": (m.get("joined_at") or "")[:10],
            }
        after = page[-1].get("user", {}).get("id")
        if len(page) < 1000:
            break

    by_handle = {v["handle"].lower(): v for v in members.values() if v.get("handle")}
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "roles_known": len(roles), "members": by_handle}
    path = vault / "Panel" / MEMBERS_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        return 0
    return len(by_handle)


# Somebody reporting a broken thing wants an answer as much as somebody
# asking outright, and they rarely use a question mark: "it crashes when I
# jump", "I cant get it to work in 5.6". Requiring a "?" filed all of those
# as ordinary chatter and they never reached the panel.
PROBLEM_MARKERS = (
    "doesn't work", "does not work", "dont work", "not working", "won't work",
    "wont work", "isn't working", "isnt working", "stopped working",
    "crash", "error", "bug", "broken", "stuck", "freeze", "glitch",
    "can't", "cant ", "cannot", "unable to", "fails", "failing", "failed",
    "issue", "problem", "not able", "no idea how", "dont know how",
    "don't know how", "i need help", "need help", "help me", "any help",
    "i need the", "i want to", "im trying", "i'm trying", "trying to",
    "does not have", "doesn't have", "i dont see", "i don't see",
    "not showing", "not appearing", "missing", "wrong",
    # "the montage is not playing", "the trace is not detecting": the shape
    # is "<thing> is not <verb>ing", which no single phrase above catches.
)
NEGATED_VERB = re.compile(r"\b(is|are|was|were|does|do|did|will|wont|won.t)\s+not\s+\w+")
# A message that is only praise or thanks is not a request, even when it
# happens to contain a marker word.
CLOSERS = ("thank", "thanks", "tks", "obrigad", "worked", "solved", "fixed it",
           "amazing", "awesome", "great work", "great stuff", "congrat",
           "nice work", "love it", "keep it up", "well done")


_URL_ONLY = re.compile(r"https?://\S+")
# "Nice, if you need help, we're here" is someone offering, and it carries
# the same words as someone asking. Reading the offer as a request files a
# helper's kindness in the queue as work to do.
OFFERS = ("if you need help", "if u need help", "we're here", "were here",
          "happy to help", "here to help", "let me know if you need",
          "feel free to ask", "you can ask")


def looks_like_question(text: str) -> bool:
    t = " ".join(text.split()).lower()
    # A pasted link with nothing around it says nothing to search on and
    # nothing to answer; the length test passes it because a URL is long.
    if len(_URL_ONLY.sub("", t).strip()) < MIN_QUESTION_LEN:
        return False
    if len(t) < MIN_QUESTION_LEN:
        return False
    if "?" not in t and any(o in t for o in OFFERS):
        return False
    # Someone closing a thread often uses a marker word in passing
    # ("this is not the first time I buy from you"). Gratitude with no
    # question mark is a thank-you, not a request.
    if len(t) < 160 and "?" not in t and any(c in t for c in CLOSERS):
        return False
    # Someone closing a thread often uses a marker word in passing ("this
    # is not the first time I buy from you"). Gratitude with no question
    # mark is a thank-you, not a request.
    if len(t) < 160 and "?" not in t and any(c in t for c in CLOSERS):
        return False
    has_marker = (any(m in t for m in PROBLEM_MARKERS)
                  or bool(NEGATED_VERB.search(t)))
    if has_marker:
        return True
    if "?" in t:
        return True
    if any(t.startswith(w + " ") for w in QUESTION_WORDS):
        return True
    # Short and grateful: someone closing a thread, not opening one.
    if len(t) < 120 and any(c in t for c in CLOSERS):
        return False
    return False


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
    # dc:123 already in the inbox covers dc:123#1 and #2: splitting only
    # applies to messages that were not filed before, or the old entry and
    # its pieces would sit side by side saying the same thing.
    fresh = [r for r in rows
             if r["source"] not in seen
             and r["source"].split("#")[0] not in seen]
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
    ap.add_argument("--no-split", dest="split", action="store_false",
                    help="keep a message with two questions as one entry")
    ap.add_argument("--full", action="store_true",
                    help="ignore the saved position and re-walk the history")
    ap.add_argument("--max-per-channel", type=int,
                    default=int(os.getenv("DISCORD_MAX_PER_CHANNEL", "3000")))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    VAULT = Path(args.vault)
    if not get_secret("DISCORD_BOT_TOKEN"):
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
    read = answered_n = split_n = 0
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
            text = resolve_mentions(" ".join((m.get("content") or "").split()), m)
            if not looks_like_question(text):
                continue
            answer = find_answer(m, messages, staff)
            reply = (resolve_mentions(" ".join((answer.get("content") or "").split()),
                                      answer)[:900] if answer else "")
            parts = split_questions(text) if args.split else [text]
            answered_idx = which_part_answered(parts, reply) if len(parts) > 1 else 0

            for pi, part in enumerate(parts):
                # The first part keeps the message id unsuffixed, so a
                # question already filed and referenced keeps its code
                # when a second ask is split out of it.
                suffix = f"#{pi + 1}" if pi else ""
                if len(parts) > 1:
                    part_status = "answered" if pi == answered_idx and reply else "no-source"
                else:
                    part_status = "answered" if reply else "no-source"
                rows.append({
                    "date": (m.get("timestamp") or "")[:10],
                    "author": author_handle(author),
                    "text": part,
                    "status": part_status,
                    "reply": reply,
                    "source": f"dc:{m['id']}{suffix}",
                    "channel_name": name,
                    # A forum question belongs to its post, not to the forum,
                    # and the link has to point at the post to be clickable.
                    "thread": thread_of.get(m["id"], ""),
                    "url": (f"https://discord.com/channels/{guild or '@me'}/"
                            f"{m.get('channel_id', cid)}/{m['id']}"),
                })
                found += 1
                if part_status == "answered":
                    answered_n += 1
            if len(parts) > 1:
                split_n += 1

        if newest and not args.dry_run:
            state[cid] = {"last_id": str(newest), "name": name,
                          "checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        print(f"#{name}: {len(messages)} messages read, {found} questions")

    members = 0 if args.dry_run else refresh_members(guild, VAULT)

    added = write_inbox(rows, args.dry_run)
    if not args.dry_run:
        save_state(state)

    verb = "would be " if args.dry_run else ""
    print(f"\nmessages read: {read} \u00b7 questions found: {len(rows)} "
          f"({answered_n} already answered by staff)")
    if split_n:
        print(f"messages carrying more than one question, split apart: {split_n}")
    print(f"{verb}added to the inbox: {added} (new ones only) \u00b7 "
          f"member roles refreshed: {members} \u00b7 {time.time() - t0:.0f}s")
    if not read:
        print("\nNothing came back. If the channels are right, the usual cause is")
        print("the Message Content intent being off: Discord Developer Portal >")
        print("your app > Bot > Privileged Gateway Intents > Message Content.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
