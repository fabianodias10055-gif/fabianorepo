#!/usr/bin/env python3
"""LocoDev Operations Panel: reads the vault from disk and renders the dashboard.

Two outputs from the same scan:
  - "00 - Operations Center.md"  a generated note you can read inside Obsidian
  - "panel.html"                 a live dashboard you open in the browser

Usage:
    python panel.py                 build both files once
    python panel.py --watch         watch the vault, rebuild on every change,
                                    serve on localhost and open the browser

In watch mode the page shows whether it is live, when it last rebuilt, and has
a button to rebuild on demand. Edit any note in Obsidian, save, and the page
refreshes itself within a couple of seconds.
"""

import argparse
import hashlib
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

VAULT = Path(r"F:\LocoDev Vault")
LEGACY_VAULT = Path(r"C:\Users\LocoDevPC\Documents\Vaults")
PORT = 8765
POLL_SECONDS = 2.0
YT_API = "https://www.googleapis.com/youtube/v3"
YT_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Facet key -> (display label, file name patterns, weight in the urgency score).
# Overview and Setup weigh most: they are the ones that answer on their own.
FACETS = [
    ("overview", "Overview", ("overview", "00 -"), 3),
    ("logic", "How it works", ("how it works", "logic", "01 -"), 1),
    ("setup", "Setup", ("setup", "02 -"), 3),
    ("issues", "Common issues", ("common issues", "issue", "faq", "03 -"), 2),
    ("blueprints", "Blueprints", ("blueprint", "04 -"), 1),
]
WEIGHT_TOTAL = sum(f[3] for f in FACETS)

# Minimum bytes of real author content for a facet to count as written.
# Frontmatter, headings and template comments are stripped before measuring, so
# an untouched template scores zero.
MIN_CONTENT = 80

CATALOG = [
    ("climb", "Climb", "locomotion"),
    ("crawl-locomotion", "Crawl Locomotion", "locomotion"),
    ("directional-ledge", "Directional Ledge", "locomotion"),
    ("flight", "Flight", "locomotion"),
    ("grapple-hook", "Grapple Hook", "locomotion"),
    ("hang-and-swing", "Hang and Swing", "locomotion"),
    ("ladder", "Ladder", "locomotion"),
    ("ledge-system", "Ledge System", "locomotion"),
    ("motion-matching", "Motion Matching", "locomotion"),
    ("narrow-passage", "Narrow Passage", "locomotion"),
    ("obstacle-avoidance", "Obstacle Avoidance", "locomotion"),
    ("roll-dash", "Roll Dash + Pickup Pistols", "locomotion"),
    ("root-motion", "Root Motion", "locomotion"),
    ("rope", "Rope", "locomotion"),
    ("simple-gliding", "Simple Gliding", "locomotion"),
    ("skateboard", "Skateboard", "locomotion"),
    ("spider-man", "Spider-Man", "locomotion"),
    ("swim", "Swim", "locomotion"),
    ("vault-move", "Vault", "locomotion"),
    ("wall-run", "Wall Run", "locomotion"),
    ("ziplining", "Ziplining", "locomotion"),
    ("advanced-combat-punch", "Advanced Combat Punch", "combat"),
    ("bow-and-arrow", "Bow and Arrow", "combat"),
    ("pistol", "Pistol", "combat"),
    ("sword-combo", "Sword Combo", "combat"),
    ("weapon-system", "Weapon System", "combat"),
    ("hostage", "Hostage", "interaction"),
    ("sneak-cover", "Sneak Cover", "interaction"),
    ("stealth", "Stealth", "interaction"),
    ("telekinesis", "Telekinesis", "interaction"),
]

# Fallback demand for a system nobody has asked about in the logged questions
# yet. Real demand (open, no-source questions in Inbox/) always wins once a
# system has at least one logged question, even a count of zero; this table
# only guesses for a system that has never come up.
DEMAND = {
    "ledge-system": 14,
    "obstacle-avoidance": 11,
    "rope": 8,
    "ziplining": 6,
    "grapple-hook": 5,
    "weapon-system": 5,
    "crawl-locomotion": 3,
    "wall-run": 3,
}

# Data sources and their real state, verified in Supabase and in the bot code
# on 2026-08-13.
INSTRUMENTATION = [
    ("Wingman: events", "377,394 rows", "ok",
     "loco_events, including every user prompt, cost and compile result"),
    ("Wingman: diagnostics", "971,739 rows", "ok",
     "loco_diagnostics, ETL to PostHog every 3 minutes"),
    ("Wingman: conversations", "2,925 rows", "ok",
     "loco_transcripts, prompt and response per turn"),
    ("Discord", "nothing stored", "blind",
     "an unanswered question becomes an ephemeral alert; chat history lives in RAM only"),
    ("YouTube (LocoDev)", "0 comments", "blind",
     "the collector already runs for 12 competitor videos, never for your own channel"),
    ("Patreon", "2 manual snapshots", "partial",
     "from April; the event log drops anything older than 90 days"),
    ("Short links (locodev.dev)", "SQLite on Railway", "ok",
     "click telemetry behind adminlocoILco; the panel reads its JSON API live"),
    ("Knowledge base", "hand curated", "partial",
     "entries only via staff reaction; lives on a Railway volume with no local copy"),
]


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------

def strip_scaffold(text: str) -> str:
    """Remove frontmatter and guide comments only. Headings, bold labels and
    list content survive: this is the version the answer-suggestion search
    reads, where '## Symptom: the character grabs the rope but does not
    swing' is exactly the text a question should match against."""
    body = re.sub(r"^---.*?---", "", text, count=1, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    return body.strip()


# A line that is pure template scaffolding: a bare bold label ('**Cause:**'
# with nothing after it), or only list/checkbox/number punctuation. Content
# written after a label ('**Cause:** the constraint is locked') never matches.
_BARE_SCAFFOLD = re.compile(r"(?:\*\*[^*]+:\*\*)|(?:[-*\d.\s\[\]():]+)")


def strip_template(text: str) -> str:
    """What the AUTHOR wrote, for coverage measuring: scaffold removed, plus
    headings, tables, quotes and bare template labels dropped. An untouched
    template must come out (near) empty; the old single-regex version also
    swallowed real prose in bold or bullets, undercounting written notes.
    """
    lines = []
    for line in strip_scaffold(text).splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|", ">", "![](")):
            continue
        if _BARE_SCAFFOLD.fullmatch(s):
            continue
        lines.append(s)
    return "\n".join(lines)


def measure_system(slug: str, name: str) -> dict:
    folder = VAULT / "Systems" / slug
    written: dict[str, bool] = {}
    chars = 0
    found_at = str(folder) if folder.is_dir() else ""

    if folder.is_dir():
        for note in folder.rglob("*.md"):
            useful = len(strip_template(note.read_text(encoding="utf-8", errors="replace")))
            chars += useful
            low = note.stem.lower()
            for key, _label, patterns, _w in FACETS:
                if any(p in low for p in patterns):
                    written[key] = written.get(key, False) or useful >= MIN_CONTENT
                    break

    facets = [written.get(key, False) for key, _l, _p, _w in FACETS]
    return {
        "slug": slug, "name": name,
        "facets": facets, "done": sum(facets),
        "chars": chars, "path": found_at,
        "demand": DEMAND.get(slug, 0),
    }


def urgency(m: dict, demand_max: int) -> tuple[int, str]:
    """Need percentage and label.

    Combines how much is missing (weighted per facet) with how many people have
    already asked. Demand counts 60%, the gap 40%: documenting what nobody asks
    about is less urgent than documenting what everyone asks about.
    """
    missing = sum(w for (_k, _l, _p, w), ok in zip(FACETS, m["facets"]) if not ok)
    gap = missing / WEIGHT_TOTAL
    asked = (m["demand"] / demand_max) if demand_max else 0
    pct = round((gap * 0.4 + asked * 0.6) * 100)

    if pct >= 70:
        label = "critical"
    elif pct >= 40:
        label = "urgent"
    elif pct >= 15:
        label = "normal"
    elif pct > 0:
        label = "low"
    else:
        label = "done"
    return pct, label


QUESTION_HEAD = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\s+(.+?)\s*$", re.M)

CHANNELS = {
    "discord": "#5865F2",
    "youtube": "#E5332A",
    "patreon": "#E6EDEA",
    "email": "#3FD39C",
}

STATUS_CLASS = {
    "answered": "ok",
    "escalated": "info",
    "no-source": "crit",
    "out-of-scope": "mute",
}

NAME_BY_SLUG = {slug: name for slug, name, _c in CATALOG}


ANSWERED_LOG_NAME = "02 - Answered.md"

QUESTION_FIELDS = ("channel", "system", "status", "subscriber", "source",
                   "video_id", "video_url", "video")
_FIELD_LINE = re.compile(r"^(" + "|".join(QUESTION_FIELDS) + r"):\s*(.*)$")


def _derive_id(date: str, who: str, source: str, text: str) -> str:
    if source:
        return source
    return "local:" + hashlib.sha1(f"{date}|{who}|{text}".encode()).hexdigest()[:12]


def _mask(raw: str, pattern: str, flags=re.S) -> str:
    """Blank out a region length-for-length (spaces, newlines kept), so byte
    offsets found in the masked copy still point at the right place in the
    real file. Used to hide frontmatter, fenced examples and instructions
    from the block scanner without disturbing where real blocks start.
    """
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    return re.sub(pattern, blank, raw, count=0, flags=flags)


def _iter_inbox_blocks():
    """Yield (note_path, raw_text, start, end, date, who, fields, text, qid)
    for every question block in every Inbox/*.md file.

    parse_questions() and update_question_status() both call this, so the id
    a question is displayed with and the id used to find it again for a
    status update can never drift apart - they are the same computation.
    """
    inbox = VAULT / "Inbox"
    if not inbox.is_dir():
        return
    for note in sorted(inbox.glob("*.md")):
        if note.name == ANSWERED_LOG_NAME:
            continue  # a log of replies, not a source of questions
        raw = note.read_text(encoding="utf-8", errors="replace")
        masked = _mask(raw, r"^---.*?\n---\n")
        masked = _mask(masked, r"```.*?```")
        # Blank the instructions header too (everything up to and including
        # the first remaining '\n---\n'), same rule parse_questions used to
        # apply with str.split: only real content after that line counts.
        sep = re.search(r"\n---\n", masked)
        if sep:
            head = masked[:sep.end()]
            masked = re.sub(r"[^\n]", " ", head) + masked[sep.end():]

        matches = list(QUESTION_HEAD.finditer(masked))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(masked)
            block = raw[start:end]  # real content: nothing here was masked

            fields = {}
            for line in block.splitlines():
                fm = _FIELD_LINE.match(line.strip())
                if fm:
                    v = fm.group(2).strip()
                    # channel/system/status/subscriber are normalized labels;
                    # the rest must keep their case: YouTube video and comment
                    # ids are case sensitive, and a lowercased source would
                    # both break the deep link and make the Reply button post
                    # against a comment id that does not exist.
                    if fm.group(1) in ("video", "source", "video_id", "video_url"):
                        fields[fm.group(1)] = v
                    else:
                        fields[fm.group(1)] = v.lower()
            prose = "\n".join(
                l for l in block.splitlines()
                if l.strip() and not _FIELD_LINE.match(l.strip())
            ).strip()
            text = " ".join(prose.split())
            date, who = m.group(1), m.group(2)
            qid = _derive_id(date, who, fields.get("source", ""), text)
            yield note, raw, start, end, date, who, fields, text, qid


def parse_questions() -> list[dict]:
    """Read every question logged in Inbox/*.md: hand written and collected.

    Deliberately forgiving: a missing field becomes 'unknown' rather than an
    error, because the whole point is that pasting a question costs seconds.
    """
    out = []
    for _note, _raw, _start, _end, date, who, fields, text, qid in _iter_inbox_blocks():
        system = fields.get("system", "-")
        out.append({
            "id": qid,
            "date": date,
            "who": who,
            "channel": fields.get("channel", "unknown"),
            "system": system,
            "system_name": NAME_BY_SLUG.get(system, system),
            "status": fields.get("status", "unknown"),
            "subscriber": fields.get("subscriber", "unknown"),
            "source": fields.get("source", ""),
            "video_id": fields.get("video_id", ""),
            "video": fields.get("video", ""),
            "video_url": fields.get("video_url", ""),
            "text": text,
        })
    out.sort(key=lambda q: q["date"], reverse=True)
    return out


def find_question_by_id(qid: str) -> dict | None:
    for q in parse_questions():
        if q["id"] == qid:
            return q
    return None


def update_question_status(qid: str, new_status: str) -> bool:
    """Flip the `status:` line of one question block in place. Every other
    line in the block, and every other block in the file, is left exactly
    as it was.
    """
    for note, raw, start, end, _date, _who, _fields, _text, block_id in _iter_inbox_blocks():
        if block_id != qid:
            continue
        block = raw[start:end]
        new_block = re.sub(r"^status:\s*.*$", f"status: {new_status}", block,
                           count=1, flags=re.M)
        if new_block == block:
            return False  # no status: line found to replace
        note.write_text(raw[:start] + new_block + raw[end:], encoding="utf-8")
        return True
    return False


def append_answered_log(question: dict, answer: str, posted_to_youtube: bool) -> None:
    """Durable record of every reply sent from the panel.

    Deliberately a separate, always-appended file rather than writing into a
    system's `03 - Common issues` note: that note is yours to curate by hand
    (the collector already suggests pasting into it), and auto-appending
    every reply there would bury your own writing under machine output.
    """
    path = VAULT / "Inbox" / ANSWERED_LOG_NAME
    if not path.is_file():
        header = (
            "---\ntags: [locodev, inbox, answered, generated]\n---\n\n"
            "# Answered from the panel\n\n"
            "Every reply sent with the Reply button, appended here as a permanent "
            "record. Copy a good one into the matching system's "
            "`03 - Common issues` note when you get a moment; that is what makes "
            "the panel able to answer the next person by itself.\n\n---\n"
        )
        path.write_text(header, encoding="utf-8")

    where = ""
    if question.get("video"):
        where = f"\nvideo: {question['video']}"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = (
        f"\n### {stamp} reply to {question['who']}\n"
        f"channel: {question['channel']}\n"
        f"system: {question['system']}{where}\n"
        f"posted_to_platform: {'yes' if posted_to_youtube else 'no'}\n\n"
        f"**Q:** {question['text']}\n\n"
        f"**A:** {answer}\n"
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)


ANSWER_HEAD = re.compile(
    r"^###\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+reply to\s+(.+?)\s*$", re.M)


def parse_answers() -> list[dict]:
    """Read back what append_answered_log wrote, newest first, so the
    dashboard's Answers section shows the replies actually sent."""
    path = VAULT / "Inbox" / ANSWERED_LOG_NAME
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8", errors="replace")
    out = []
    matches = list(ANSWER_HEAD.finditer(raw))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        block = raw[m.end():end]
        fields = {}
        for line in block.splitlines():
            fm = re.match(r"^(channel|system|video|posted_to_platform):\s*(.*)$",
                          line.strip())
            if fm:
                fields[fm.group(1)] = fm.group(2).strip()
        qm = re.search(r"\*\*Q:\*\*\s*(.*?)(?=\n\*\*A:\*\*|\Z)", block, re.S)
        am = re.search(r"\*\*A:\*\*\s*(.*)", block, re.S)
        out.append({
            "when": m.group(1),
            "who": m.group(2),
            "channel": fields.get("channel", "unknown"),
            "system": fields.get("system", "-"),
            "video": fields.get("video", ""),
            "posted": fields.get("posted_to_platform", "no") == "yes",
            "q": " ".join((qm.group(1) if qm else "").split()),
            "a": (am.group(1).strip() if am else ""),
        })
    out.reverse()
    return out


# --------------------------------------------------------------------------
# Suggested answers: search your own notes, never fabricate one
# --------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "and",
    "in", "on", "for", "it", "this", "that", "with", "you", "your", "i",
    "can", "does", "do", "did", "will", "would", "how", "what", "why",
    "when", "where", "any", "there", "have", "has", "my", "me", "if",
}


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOPWORDS}


def suggest_answer(question: dict) -> dict:
    """Score every SECTION of the relevant notes against the question's
    keywords and return the best match, verbatim, with its source.

    Not AI-generated: this is a search over content you already wrote, the
    same idea as the kb_search tool designed for the Wingman plugin, just
    running locally against markdown instead of embeddings in Supabase. If
    nothing scores, the honest answer is that this gap has no source yet.

    Sections, not paragraphs, because the notes are written as
    Symptom / Cause / Fix triplets under one heading: splitting those apart
    would return a cause with no fix. The heading itself carries keywords
    ('## Symptom: the character grabs the rope but does not swing') so it
    is part of what gets scored.
    """
    q_words = _keywords(question["text"])
    if not q_words:
        return {"text": "", "source": ""}

    candidates: list[Path] = []
    system = question.get("system", "-")
    if system and system != "-":
        sysdir = VAULT / "Systems" / system
        if sysdir.is_dir():
            candidates.extend(sorted(sysdir.glob("*.md")))
    if not candidates:
        # Catalog-wide or unknown system: search everything rather than
        # nothing, small corpus (a few dozen files), brute force is fine.
        candidates.extend((VAULT / "Systems").glob("*/*.md"))

    best_score, best_text, best_source = 0, "", ""
    for path in candidates:
        text = strip_scaffold(path.read_text(encoding="utf-8", errors="replace"))
        for section in re.split(r"(?m)^(?=#{1,6}\s)", text):
            section = section.strip()
            # A section with no real author content is template residue; it
            # must never be offered as an answer no matter what it scores.
            if len(strip_template(section)) < 40:
                continue
            score = len(q_words & _keywords(section))
            if score > best_score:
                best_score, best_text, best_source = (
                    score, section, path.relative_to(VAULT))

    if best_score < 2:  # a single shared word is coincidence, not an answer
        return {"text": "", "source": ""}
    return {"text": best_text, "source": str(best_source).replace("\\", "/")}


# --------------------------------------------------------------------------
# Posting a reply for real: needs a one-time OAuth setup, not just the read
# only API key. See youtube_oauth_setup.py.
# --------------------------------------------------------------------------

def _youtube_access_token() -> str | None:
    """Exchange the stored refresh token for a short-lived access token.

    Returns None when OAuth has never been set up; the caller treats that as
    "cannot post", not as an error, and says so plainly instead of pretending.
    """
    refresh = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
    client_id = os.getenv("YOUTUBE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET", "").strip()
    if not (refresh and client_id and client_secret):
        return None

    body = urlparse.urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh, "grant_type": "refresh_token",
    }).encode()
    req = urlrequest.Request(YT_OAUTH_TOKEN_URL, data=body, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            return json.load(resp)["access_token"]
    except (urlerror.URLError, KeyError, ValueError):
        return None


def post_youtube_reply(comment_id: str, text: str) -> tuple[bool, str]:
    token = _youtube_access_token()
    if not token:
        return False, (
            "YouTube reply-posting is not set up. The vault was still updated. "
            "Run youtube_oauth_setup.py once to enable posting for real."
        )
    body = json.dumps({"snippet": {"parentId": comment_id, "textOriginal": text}}).encode()
    req = urlrequest.Request(
        f"{YT_API}/comments?part=snippet",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            json.load(resp)
        return True, "Posted to YouTube."
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return False, f"YouTube refused the reply ({exc.code}): {detail}"
    except urlerror.URLError as exc:
        return False, f"Could not reach YouTube: {exc.reason}"


# --------------------------------------------------------------------------
# Link telemetry: the locodev.dev short-link admin API (adminlocoILco).
# Server-to-server, option A of the integration report: this local server
# logs in with LOCODEV_ADMIN_SECRET, keeps the bearer token in memory and
# exposes a cached /links.json to the page. The secret and the token never
# reach the browser and are never logged.
# --------------------------------------------------------------------------

ADMIN_URL = os.getenv("LOCODEV_ADMIN_URL", "https://locodev.dev/adminlocoILco").rstrip("/")
ADMIN_CACHE_TTL = 120          # seconds; the page polls every 60
ADMIN_ERROR_TTL = 45           # failed fetches retry sooner, but never hammer
ADMIN_TOKEN_MAX_AGE = 11 * 3600  # remote invalidates at 12h; stay under it

_admin = {"token": "", "token_at": 0.0, "cache": None, "cache_at": 0.0}


def _admin_call(path: str, token: str = "", payload: dict | None = None):
    """One JSON request to the admin API: (http_status, parsed_or_None).
    Status 0 means the request never got an HTTP answer (network)."""
    # Cloudflare fronting locodev.dev returns 403 for the default
    # 'Python-urllib' User-Agent before the request ever reaches the app;
    # any browser-like UA passes. Verified 2026-08-13.
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LocoDevPanel/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urlrequest.Request(
        ADMIN_URL + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method="POST" if payload is not None else "GET",
        headers=headers,
    )
    try:
        with urlrequest.urlopen(req, timeout=8) as resp:
            return resp.status, json.load(resp)
    except urlerror.HTTPError as exc:
        return exc.code, None
    except (urlerror.URLError, TimeoutError, ValueError, OSError):
        return 0, None


def _admin_token() -> tuple[str, str]:
    """(token, error). error is '' on success, else a category the page can
    show honestly: not-configured / auth / network / http-<code>. These stay
    separate on purpose; a network failure must never read as a login one."""
    secret = os.getenv("LOCODEV_ADMIN_SECRET", "").strip()
    if not secret:
        return "", "not-configured"
    if _admin["token"] and time.time() - _admin["token_at"] < ADMIN_TOKEN_MAX_AGE:
        return _admin["token"], ""
    status, data = _admin_call("/login", payload={"password": secret})
    if status == 200 and isinstance(data, dict) and data.get("token"):
        _admin["token"] = data["token"]
        _admin["token_at"] = time.time()
        return _admin["token"], ""
    if status in (401, 429):
        return "", "auth"
    if status == 0:
        return "", "network"
    return "", f"http-{status}"


def fetch_link_telemetry() -> dict:
    """Stats + links + 7d country breakdown, behind a short in-memory cache
    so page refreshes do not hammer the remote service (or block this
    single-threaded server on a slow network for every request)."""
    now = time.time()
    cached = _admin["cache"]
    if cached is not None:
        ttl = ADMIN_CACHE_TTL if cached.get("ok") else ADMIN_ERROR_TTL
        if now - _admin["cache_at"] < ttl:
            return cached

    def keep(result: dict) -> dict:
        _admin["cache"] = result
        _admin["cache_at"] = now
        return result

    token, err = _admin_token()
    if err:
        return keep({"ok": False, "error": err})

    status, stats = _admin_call("/api/stats", token=token)
    if status == 401:
        # Remote restart or 12h TTL: the old token died. Log in once more.
        _admin["token"] = ""
        token, err = _admin_token()
        if err:
            return keep({"ok": False, "error": err})
        status, stats = _admin_call("/api/stats", token=token)
    if status != 200 or not isinstance(stats, dict):
        return keep({"ok": False,
                     "error": "network" if status == 0 else f"http-{status}"})

    _s1, links = _admin_call("/api/links", token=token)
    _s2, countries = _admin_call("/api/clicks/by-country?window=7d", token=token)

    return keep({
        "ok": True,
        "stats": stats,
        "links": links if isinstance(links, list) else [],
        "countries": countries if isinstance(countries, list) else [],
        "fetched_at": int(now),
    })


def build_gaps(questions: list[dict]) -> list[dict]:
    """Group unanswerable questions into a ranked backlog of what to write."""
    buckets: dict[str, dict] = {}
    for q in questions:
        if q["status"] != "no-source":
            continue
        key = q["system"] if q["system"] != "-" else "general"
        b = buckets.setdefault(key, {
            "key": key,
            "label": NAME_BY_SLUG.get(key, "General / catalog wide"),
            "questions": [],
        })
        b["questions"].append(q)
    gaps = list(buckets.values())
    for g in gaps:
        g["count"] = len(g["questions"])
    gaps.sort(key=lambda g: -g["count"])
    return gaps


def build_people(questions: list[dict]) -> list[dict]:
    people: dict[str, dict] = {}
    for q in questions:
        p = people.setdefault(q["who"], {
            "who": q["who"], "channel": q["channel"],
            "subscriber": q["subscriber"], "asked": 0, "open": 0,
            "esc": 0, "last": q["date"],
        })
        p["asked"] += 1
        if q["status"] in ("escalated", "no-source"):
            p["open"] += 1
        if q["status"] == "escalated":
            p["esc"] += 1
        if q["subscriber"] != "unknown":
            p["subscriber"] = q["subscriber"]
    ordered = sorted(people.values(), key=lambda p: (-p["open"], -p["asked"]))
    for p in ordered:
        # Someone who is not a subscriber and is asking how to subscribe is a
        # lead, not a support ticket.
        p["lead"] = p["subscriber"] == "no" and p["open"] > 0
    return ordered


def scan() -> dict:
    # Real demand first: with logged questions, a system's demand is how many
    # people actually asked and got nothing, not the hand-typed DEMAND table.
    # That table only fills the gap for a system nobody has asked about yet
    # (or before the collector has ever run), so the two numbers never argue
    # with the Gaps section, which is built from the same count.
    questions = parse_questions()
    open_demand: dict[str, int] = {}
    seen_systems: set[str] = set()
    for q in questions:
        if q["system"] == "-":
            continue
        seen_systems.add(q["system"])
        if q["status"] == "no-source":
            open_demand[q["system"]] = open_demand.get(q["system"], 0) + 1

    systems = [measure_system(slug, name) for slug, name, _c in CATALOG]
    for s in systems:
        # A system with any logged question uses the real open count, even
        # when that count is 0 (already answered): the hand-typed DEMAND
        # table is only a placeholder for a system nobody has asked about.
        if s["slug"] in seen_systems:
            s["demand"] = open_demand.get(s["slug"], 0)
    demand_max = max((s["demand"] for s in systems), default=0)
    for s in systems:
        s["pct"], s["urgency"] = urgency(s, demand_max)
    systems.sort(key=lambda s: (-s["pct"], -s["demand"], s["name"]))

    videos = []
    vroot = VAULT / "YouTube" / "Videos"
    if vroot.is_dir():
        # Newest first: the folder names start with the publish date.
        for folder in sorted(vroot.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            has = {}
            meta = {}
            for note in folder.glob("*.md"):
                text = note.read_text(encoding="utf-8", errors="replace")
                useful = len(strip_template(text))
                low = note.stem.lower()
                if "transcript" in low:
                    has["transcript"] = useful >= MIN_CONTENT
                elif "comment" in low:
                    has["comments"] = useful >= MIN_CONTENT
                elif "description" in low:
                    has["description"] = useful >= MIN_CONTENT
                elif "overview" in low:
                    has["overview"] = useful >= MIN_CONTENT
                    # The collector's frontmatter carries the id and url the
                    # dashboard needs for thumbnails and deep links.
                    for key in ("video_id", "url", "published", "system", "views"):
                        fm = re.search(rf"^{key}:[ \t]*(\S+)[ \t]*$", text, re.M)
                        if fm:
                            meta[key] = fm.group(1)
            videos.append({
                "name": folder.name,
                "video_id": meta.get("video_id", ""),
                "url": meta.get("url", ""),
                "published": meta.get("published", folder.name[:10]),
                "system": meta.get("system", ""),
                "views": meta.get("views", ""),
                "transcript": has.get("transcript", False),
                "comments": has.get("comments", False),
                "description": has.get("description", False),
                "overview": has.get("overview", False),
            })

    gaps = build_gaps(questions)
    people = build_people(questions)

    answered = sum(1 for q in questions if q["status"] == "answered")
    open_q = sum(1 for q in questions if q["status"] in ("escalated", "no-source"))
    answer_rate = round(answered * 100 / len(questions)) if questions else 0

    total_facets = len(CATALOG) * len(FACETS)
    written = sum(s["done"] for s in systems)

    # Counted here, over exactly the folders this scan reads, because the
    # footer labels it "notes scanned". Never fatal: it is display only.
    try:
        md_files = (
            sum(1 for _ in (VAULT / "Systems").rglob("*.md"))
            + sum(1 for _ in (VAULT / "Inbox").glob("*.md"))
            + sum(1 for _ in (VAULT / "YouTube" / "Videos").rglob("*.md"))
        )
    except OSError:
        md_files = 0

    return {
        "md_files": md_files,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": int(time.time()),
        "systems": systems,
        "videos": videos,
        "questions": questions,
        "gaps": gaps,
        "people": people,
        "answers": parse_answers(),
        "open_q": open_q,
        "answer_rate": answer_rate,
        "written": written,
        "total_facets": total_facets,
        "complete": sum(1 for s in systems if s["done"] == len(FACETS)),
        "empty": sum(1 for s in systems if s["done"] == 0),
        "critical": sum(1 for s in systems if s["urgency"] == "critical"),
        "urgent": sum(1 for s in systems if s["urgency"] == "urgent"),
    }


# --------------------------------------------------------------------------
# Markdown output
# --------------------------------------------------------------------------

def bar(n: int, total: int, width: int = 5) -> str:
    filled = round((n / total) * width) if total else 0
    return "█" * filled + "░" * (width - filled)


def render_markdown(d: dict) -> str:
    pct = d["written"] * 100 // d["total_facets"] if d["total_facets"] else 0
    lines = [
        "---",
        "tags: [locodev, panel, operations, generated]",
        f"generated: {d['generated_at']}",
        "source: clickup-mcp/panel.py",
        "---",
        "",
        "# LocoDev Operations Center",
        "",
        "Generated from disk. **Do not edit by hand**: changes are lost on the next",
        "run. To refresh, run `python panel.py`, or `python panel.py --watch` for the",
        "live dashboard in the browser.",
        "",
        "## Summary",
        "",
        f"- **Catalog coverage:** {d['written']} of {d['total_facets']} notes written ({pct}%)",
        f"- **Complete systems:** {d['complete']} of {len(CATALOG)}",
        f"- **Systems with nothing written:** {d['empty']}",
        f"- **Priority:** {d['critical']} critical · {d['urgent']} urgent",
        "",
        "---",
        "",
        "## Documentation coverage",
        "",
        "Ranked by need. Facets: overview, logic, setup, issues, blueprints.",
        "",
        "| Need | System | Coverage | Facets | Demand |",
        "|---|---|---|---|---|",
    ]
    for s in d["systems"]:
        marks = "".join("+" if f else "." for f in s["facets"])
        dem = f"{s['demand']}x" if s["demand"] else "-"
        need = f"**{s['pct']}% {s['urgency']}**" if s["urgency"] == "critical" else f"{s['pct']}% {s['urgency']}"
        lines.append(
            f"| {need} | {s['name']} | {bar(s['done'], len(FACETS))} {s['done']}/5 "
            f"| `{marks}` | {dem} |"
        )

    lines += [
        "",
        "> Need combines how much is missing (weighted: overview and setup count",
        "> most, since they answer on their own) with how many people have asked.",
        "> Demand counts 60%, the gap 40%.",
        "",
        "---",
        "",
        "## Incoming questions",
        "",
        f"{d['open_q']} open of {len(d['questions'])} logged · {d['answer_rate']}% answered.",
        "Written by hand in `Inbox/00 - Questions.md`.",
        "",
    ]
    if d["questions"]:
        lines += ["| When | Who | Channel | About | Status |", "|---|---|---|---|---|"]
        for q in d["questions"]:
            about = q["system_name"] if q["system"] != "-" else "catalog wide"
            sub = " (subscriber)" if q["subscriber"] == "yes" else ""
            lines.append(
                f"| {q['date']} | {q['who']}{sub} | {q['channel']} | {about} | {q['status']} |"
            )
    else:
        lines.append("*No questions logged yet.*")

    lines += ["", "---", "", "## Gaps to close", ""]
    if d["gaps"]:
        for g in d["gaps"]:
            lines.append(f"### {g['label']} — {g['count']} unanswered")
            lines.append("")
            for q in g["questions"]:
                lines.append(f'- "{q["text"][:160]}" — {q["who"]}, {q["channel"]}, {q["date"]}')
            lines.append("")
    else:
        lines.append("*Nothing marked `status: no-source`.*")

    lines += [
        "---",
        "",
        "## Priority queue",
        "",
    ]
    queue = [s for s in d["systems"] if s["demand"] > 0 and s["done"] < len(FACETS)]
    if queue:
        for i, s in enumerate(queue, 1):
            missing = [lbl for (_k, lbl, _p, _w), ok in zip(FACETS, s["facets"]) if not ok]
            lines.append(
                f"{i}. `{s['pct']}% {s['urgency']}` **{s['name']}** "
                f"({s['demand']} questions) missing: {', '.join(missing)}"
            )
    else:
        lines.append("*No gaps with recorded demand.*")

    lines += [
        "",
        "---",
        "",
        "## What is measured, and what is blind",
        "",
        "| Source | Volume | State | Notes |",
        "|---|---|---|---|",
    ]
    for source, vol, state, note in INSTRUMENTATION:
        lines.append(f"| {source} | {vol} | {state} | {note} |")

    lines += [
        "",
        "> The product has first-class telemetry; the customer has none.",
        "> Wiring the blind channels is what this panel needs to show real",
        "> questions instead of only coverage.",
        "",
        "---",
        "",
        "## Replying from the panel",
        "",
        "Every question in the live dashboard expands into Suggest + a reply box",
        "+ Reply. Suggest searches your own notes for the best matching paragraph",
        "(no AI, no fabrication: it either found something you wrote or it says so).",
        "Reply always updates the vault (marks the question `answered`, appends a",
        "permanent record to `Inbox/02 - Answered.md`). Posting the reply back to",
        "YouTube for real needs a one-time OAuth setup (`youtube_oauth_setup.py`);",
        "without it the vault still updates and the panel says plainly that it did",
        "not post anywhere, rather than pretending it did.",
        "",
        "---",
        "",
        "## Still manual, and what would automate it",
        "",
        "Discord questions above are typed into `Inbox/00 - Questions.md` by hand.",
        "YouTube ones are collected automatically by `collect_youtube.py`. What is",
        "still missing:",
        "",
        "- **Discord questions**: today they become an ephemeral alert and are",
        "  never stored. Storing them is a few lines in the bot.",
        "- **Subscriber status**: needs Discord identity matched against the",
        "  Patreon member list, so `subscriber:` stops being a guess.",
        "- **Per-video system tagging**: fill in `system:` on each video's",
        "  `00 - Overview` note, or every YouTube question lands in the catalog",
        "  wide bucket instead of the system it is actually about.",
        "- **Bot confidence log**: same Suggest search, wired into the Discord",
        "  bot so it can answer above a confidence threshold on its own.",
        "",
        "The demand column in the coverage table is also **estimated by hand**",
        "for a system nobody has asked about yet; once a real question is logged",
        "for it, the real count takes over.",
        "",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# HTML output
# --------------------------------------------------------------------------

def render_html(d: dict, live: bool) -> str:
    """The dashboard UI lives in panel_ui.py. This passes the scan through
    together with the static config the layout needs; splitting them keeps
    the data pipeline (scan/suggest/reply/serve) apart from presentation."""
    import panel_ui
    return panel_ui.render_html(d, live, FACETS, INSTRUMENTATION)


# --------------------------------------------------------------------------
# Build + watch
# --------------------------------------------------------------------------

_state = {"epoch": 0, "building": False}


def _update_history(out: Path, d: dict) -> list:
    """Real trend points for the header tiles' sparklines.

    One point per build whose numbers actually changed; a rebuild with the
    same numbers only refreshes the last timestamp. The lines start flat and
    grow meaning with use, rather than faking a trend that was never measured.
    """
    path = out / "history.json"
    try:
        hist = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(hist, list):
            hist = []
    except (OSError, ValueError):
        hist = []

    cov = d["written"] * 100 // d["total_facets"] if d["total_facets"] else 0
    point = {"t": d["epoch"], "open": d["open_q"], "rate": d["answer_rate"],
             "cov": cov, "crit": d["critical"], "complete": d["complete"]}
    keys = ("open", "rate", "cov", "crit", "complete")
    if hist and all(hist[-1].get(k) == point[k] for k in keys):
        hist[-1]["t"] = point["t"]
    else:
        hist.append(point)
    hist = hist[-400:]

    try:
        path.write_text(json.dumps(hist), encoding="utf-8")
    except OSError:
        pass  # a failed history write must never block the panel itself
    return hist


_build_lock = threading.Lock()


def build(live: bool) -> dict:
    """Serialized: the /reply handler and the watcher thread can both ask for
    a rebuild inside the same 2s window; unserialized, their interleaved
    writes could hand the browser a truncated panel.html and drop a history
    point. The finally guarantees the building flag never sticks: stuck true
    would freeze every status poll at 'rebuilding...' forever."""
    with _build_lock:
        _state["building"] = True
        try:
            t0 = time.perf_counter()
            data = scan()
            data["scan_ms"] = int((time.perf_counter() - t0) * 1000)
            out = VAULT / "Panel"
            out.mkdir(parents=True, exist_ok=True)
            data["history"] = _update_history(out, data)
            (out / "00 - Operations Center.md").write_text(render_markdown(data), encoding="utf-8")
            (out / "panel.html").write_text(render_html(data, live), encoding="utf-8")
            (out / "status.json").write_text(
                json.dumps({"epoch": data["epoch"], "generated_at": data["generated_at"],
                            "building": False}),
                encoding="utf-8")
            _state["epoch"] = data["epoch"]
        finally:
            _state["building"] = False
    return data


def fingerprint() -> tuple:
    """Cheap change detector: (path, mtime, size) for every note in the vault."""
    items = []
    skip = {".obsidian", ".trash", ".git"}
    for p in VAULT.rglob("*.md"):
        if p.parent.name == "Panel":
            continue  # the panel writes here; watching it would loop
        if any(part in skip for part in p.parts):
            continue  # Obsidian internals and trash: not content, no rebuilds
        try:
            st = p.stat()
        except OSError:
            continue
        items.append((str(p), st.st_mtime_ns, st.st_size))
    return tuple(sorted(items))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(VAULT / "Panel"), **kw)

    def end_headers(self):  # noqa: N802
        # A live dashboard must never be cached: a hard refresh after a
        # rebuild has to show the rebuilt page, not a stale browser copy.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):  # noqa: N802
        # self.path includes the query string; the page keeps its filter
        # state there ("/?st=no-source"), and that must still serve the
        # panel, never a directory listing of the Panel folder.
        route = self.path.split("?", 1)[0]
        if route == "/" or route.startswith("/index"):
            self.path = "/panel.html"
        if self.path.startswith("/status.json"):
            body = json.dumps({
                "epoch": _state["epoch"],
                "building": _state["building"],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/links.json"):
            body = json.dumps(fetch_link_telemetry()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        if self.path == "/rebuild":
            build(live=True)
            return self._send_json({"ok": True})

        if self.path == "/suggest":
            payload = self._json_body()
            question = find_question_by_id(str(payload.get("id", "")))
            if not question:
                return self._send_json({"ok": False, "error": "question not found"}, 404)
            hit = suggest_answer(question)
            return self._send_json({
                "ok": True, "text": hit["text"], "source": hit["source"],
            })

        if self.path == "/reply":
            payload = self._json_body()
            qid = str(payload.get("id", ""))
            answer = str(payload.get("text", "")).strip()
            if not answer:
                return self._send_json({"ok": False, "error": "empty reply"}, 400)

            question = find_question_by_id(qid)
            if not question:
                return self._send_json({"ok": False, "error": "question not found"}, 404)

            # Vault side always happens: this is the rigid part of the rule.
            # Posting to the platform is best-effort on top of it, never a
            # precondition for the vault to reflect that you replied.
            posted, platform_msg = False, "Not a YouTube question: nothing to post."
            if question["channel"] == "youtube" and question["source"].startswith("yt:"):
                comment_id = question["source"][len("yt:"):]
                posted, platform_msg = post_youtube_reply(comment_id, answer)

            update_question_status(qid, "answered")
            append_answered_log(question, answer, posted)
            build(live=True)  # vault changed: the dashboard must reflect it now

            return self._send_json({
                "ok": True, "posted_to_platform": posted, "platform_message": platform_msg,
            })

        self.send_error(404)

    def log_message(self, *a):  # silence per-request logging
        pass


def watch_loop() -> None:
    last = fingerprint()
    while True:
        time.sleep(POLL_SECONDS)
        try:
            now = fingerprint()
        except Exception:  # noqa: BLE001 - a transient disk error must not kill the watcher
            continue
        if now != last:
            last = now
            try:
                data = build(live=True)
            except Exception as exc:  # noqa: BLE001 - one failed build must not end watching
                print(f"build failed: {type(exc).__name__}: {exc}")
                continue
            print(f"[{data['generated_at']}] change detected, panel rebuilt in "
                  f"{data['scan_ms']}ms ({data['written']}/{data['total_facets']} notes written)")


def server_alive(port: int) -> bool:
    """True when a watcher is already serving on this port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    global VAULT

    # Running under pythonw (shortcut or scheduled task) means there is no
    # console: sys.stdout is None and any print would raise. Send output to a
    # log file next to the script instead.
    if sys.stdout is None or sys.stderr is None:
        # buffering=1 is line buffered: without it the log stays empty until the
        # process exits, which is exactly when you need to read it.
        log = open(Path(__file__).resolve().parent / "panel.log", "a",
                   encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"\n--- started {datetime.now():%Y-%m-%d %H:%M:%S}")

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--watch", action="store_true",
                    help="watch the vault, serve the panel and open the browser")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    VAULT = Path(args.vault)
    if not VAULT.is_dir():
        print(f"ERROR: vault not found at {VAULT}")
        return 1

    url = f"http://127.0.0.1:{args.port}/"

    # Someone is already watching (the scheduled task, or another shortcut
    # click). Do not fight over the port: just show the panel and get out.
    if args.watch and server_alive(args.port):
        print(f"watcher already running, opening {url}")
        if not args.no_open:
            webbrowser.open(url)
        return 0

    data = build(live=args.watch)
    out = VAULT / "Panel"
    print(f"panel built: {out / 'panel.html'}")
    print(f"note built:  {out / '00 - Operations Center.md'}")
    print(f"coverage: {data['written']}/{data['total_facets']} notes · "
          f"{data['critical']} critical · {data['urgent']} urgent")

    if not args.watch:
        return 0

    threading.Thread(target=watch_loop, daemon=True).start()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        print(f"\nwatching {VAULT}")
        print(f"panel live at {url}   (Ctrl+C to stop)")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
