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
                    fields[fm.group(1)] = v if fm.group(1) == "video" else v.lower()
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
            "last": q["date"],
        })
        p["asked"] += 1
        if q["status"] in ("escalated", "no-source"):
            p["open"] += 1
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
        for folder in sorted(vroot.iterdir()):
            if not folder.is_dir():
                continue
            has = {}
            for note in folder.glob("*.md"):
                useful = len(strip_template(note.read_text(encoding="utf-8", errors="replace")))
                low = note.stem.lower()
                for key in ("overview", "description", "transcript", "comments"):
                    if key in low or low.startswith(("00", "01", "02", "03")):
                        pass
                if "transcript" in low:
                    has["transcript"] = useful >= MIN_CONTENT
                elif "comment" in low:
                    has["comments"] = useful >= MIN_CONTENT
                elif "description" in low:
                    has["description"] = useful >= MIN_CONTENT
                elif "overview" in low:
                    has["overview"] = useful >= MIN_CONTENT
            videos.append({
                "name": folder.name,
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
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": int(time.time()),
        "systems": systems,
        "videos": videos,
        "questions": questions,
        "gaps": gaps,
        "people": people,
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
    pct = d["written"] * 100 // d["total_facets"] if d["total_facets"] else 0

    rows = []
    for s in d["systems"]:
        cells = "".join(
            f'<span class="f{" on" if ok else ""}" title="{lbl}"></span>'
            for (_k, lbl, _p, _w), ok in zip(FACETS, s["facets"])
        )
        dem = f"{s['demand']}" if s["demand"] else "-"
        rows.append(
            f'<tr class="u-{s["urgency"]}">'
            f'<td class="need"><span class="pct">{s["pct"]}%</span>'
            f'<span class="lab">{s["urgency"]}</span></td>'
            f'<td class="nm">{s["name"]}<small>{s["slug"]}</small></td>'
            f'<td class="fx">{cells}</td>'
            f'<td class="num">{s["done"]}/5</td>'
            f'<td class="num">{dem}</td></tr>'
        )

    queue = [s for s in d["systems"] if s["demand"] > 0 and s["done"] < len(FACETS)]
    queue_html = "".join(
        f'<li><span class="qp u-{s["urgency"]}">{s["pct"]}%</span>'
        f'<b>{s["name"]}</b> <span class="qm">missing: '
        + ", ".join(lbl for (_k, lbl, _p, _w), ok in zip(FACETS, s["facets"]) if not ok)
        + f'</span> <span class="qd">{s["demand"]} asked</span></li>'
        for s in queue
    ) or "<li>No gaps with recorded demand.</li>"

    instr_html = "".join(
        f'<tr class="s-{state}"><td>{source}</td><td class="num">{vol}</td>'
        f'<td><span class="pill p-{state}">{state}</span></td><td class="dim">{note}</td></tr>'
        for source, vol, state, note in INSTRUMENTATION
    )

    def esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))

    # --- incoming questions -------------------------------------------------
    q_rows = []
    for q in d["questions"]:
        cls = STATUS_CLASS.get(q["status"], "mute")
        colour = CHANNELS.get(q["channel"], "var(--ink3)")
        sub = '<span class="pill p-mute">subscriber</span>' if q["subscriber"] == "yes" else ""
        sysname = esc(q["system_name"]) if q["system"] != "-" else "catalog wide"

        source_html = ""
        if q["video"]:
            link = (f'<a href="{esc(q["video_url"])}" target="_blank" rel="noopener">'
                    f'{esc(q["video"])} ↗</a>' if q["video_url"] else esc(q["video"]))
            source_html = f'<div class="q-src">from: {link}</div>'

        answered = q["status"] == "answered"
        q_rows.append(
            f'<div class="q q-{cls}" data-id="{esc(q["id"])}" data-ch="{esc(q["channel"])}" '
            f'data-st="{esc(q["status"])}" data-sys="{esc(q["system"])}" tabindex="0" '
            f'role="button" aria-expanded="false">'
            f'<div class="q-top">'
            f'<span class="who"><i class="cd" style="background:{colour}"></i>{esc(q["who"])}</span>'
            f'<span class="pill p-{cls}">{esc(q["status"])}</span>{sub}</div>'
            f'<p class="q-text">"{esc(q["text"])}"</p>'
            f'{source_html}'
            f'<div class="q-foot"><span>{sysname}</span>'
            f'<span>{esc(q["channel"])}</span><span>{q["date"]}</span></div>'
            f'<div class="q-panel" hidden>'
            f'<div class="q-panel-row">'
            f'<button class="qbtn qsuggest" type="button"{" disabled" if answered else ""}>Suggest answer</button>'
            f'<span class="qmsg"></span></div>'
            f'<textarea class="qbox" rows="3" placeholder="Type or generate a reply…"'
            f'{" disabled" if answered else ""}></textarea>'
            f'<div class="q-panel-row">'
            f'<button class="qbtn qreply" type="button"{" disabled" if answered else ""}>Reply</button>'
            f'<span class="qhint">'
            f'{"Already marked answered." if answered else "Updates the vault always; posts to YouTube only if reply-posting is set up."}'
            f'</span></div></div></div>'
        )
    questions_html = "".join(q_rows) or '<p class="dim">No questions logged yet. Paste one into Inbox/00 - Questions.md</p>'

    chans = sorted({q["channel"] for q in d["questions"]})
    chan_filter_html = '<button class="fchip" data-f="ch" data-v="all" aria-pressed="true">All channels</button>' + "".join(
        f'<button class="fchip" data-f="ch" data-v="{esc(c)}" aria-pressed="false">'
        f'<i class="cd" style="background:{CHANNELS.get(c, "var(--ink3)")}"></i>{esc(c)}</button>'
        for c in chans
    )

    statuses = sorted({q["status"] for q in d["questions"]})
    status_filter_html = '<button class="fchip" data-f="st" data-v="all" aria-pressed="true">All statuses</button>' + "".join(
        f'<button class="fchip" data-f="st" data-v="{esc(s)}" aria-pressed="false">{esc(s)}</button>'
        for s in statuses
    )

    systems_present = sorted(
        {(q["system"], q["system_name"] if q["system"] != "-" else "catalog wide")
         for q in d["questions"]},
        key=lambda t: t[1],
    )
    system_options = '<option value="all">All systems</option>' + "".join(
        f'<option value="{esc(slug)}">{esc(label)}</option>' for slug, label in systems_present
    )

    # --- gaps (expandable) --------------------------------------------------
    gap_rows = []
    max_gap = d["gaps"][0]["count"] if d["gaps"] else 1
    for g in d["gaps"]:
        items = "".join(
            f'<div class="gq-item"><span>"{esc(q["text"][:160])}"</span>'
            f'<span class="gq-who">{esc(q["who"])} · {esc(q["channel"])} · {q["date"]}</span></div>'
            for q in g["questions"]
        )
        action = (f'Write Systems/{esc(g["key"])}/00 - Overview and 02 - Setup'
                  if g["key"] != "general"
                  else "Write the catalog-wide answers: compatibility table per system, and the license")
        gap_rows.append(
            f'<div class="gap" tabindex="0" role="button" aria-expanded="false">'
            f'<span class="gname">{esc(g["label"])}<span class="caret">▸</span></span>'
            f'<span class="gcount">{g["count"]}×</span>'
            f'<div class="gbar"><span style="width:{round(g["count"] * 100 / max_gap)}%"></span></div>'
            f'<div class="gq" hidden>{items}<div class="gq-act">→ {action}</div></div></div>'
        )
    gaps_html = "".join(gap_rows) or '<p class="dim">No unanswerable questions logged. Mark a question <code>status: no-source</code> to see it here.</p>'

    # --- people (compact table, collapsed past the first 8) -----------------
    people_rows = []
    for i, p in enumerate(d["people"]):
        colour = CHANNELS.get(p["channel"], "var(--ink3)")
        if p["subscriber"] == "yes":
            tag = '<span class="pill p-ok">subscriber</span>'
        elif p["subscriber"] == "no":
            tag = '<span class="pill p-mute">not a subscriber</span>'
        else:
            tag = ""  # "unknown" on nearly every row is noise, not signal
        lead = '<span class="pill p-partial">hot lead</span>' if p["lead"] else ""
        people_rows.append(
            f'<tr class="prow"{" hidden" if i >= 8 else ""}>'
            f'<td class="nm"><i class="cd" style="background:{colour}"></i>'
            f'{esc(p["who"])}{tag}{lead}</td>'
            f'<td class="num">{p["asked"]}</td><td class="num">{p["open"]}</td>'
            f'<td class="num">{p["last"]}</td></tr>'
        )
    people_html = "".join(people_rows) or '<tr><td colspan="4" class="dim">Nobody logged yet.</td></tr>'
    people_hidden_count = max(0, len(d["people"]) - 8)

    def video_cells(v: dict) -> str:
        keys = ("overview", "description", "transcript", "comments")
        return "".join(
            '<span class="f on" title="{k}"></span>'.format(k=k) if v[k]
            else '<span class="f" title="{k}"></span>'.format(k=k)
            for k in keys
        )

    vid_html = "".join(
        '<tr><td class="nm">{name}</td><td>{cells}</td></tr>'.format(
            name=v["name"], cells=video_cells(v))
        for v in d["videos"]
    ) or '<tr><td colspan="2" class="dim">No video folders yet.</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>LocoDev Operations Panel</title>
<style>
:root {{
  --ground:#0D1311; --surface:#141C19; --surface2:#1B2521;
  --ink:#E6EDEA; --ink2:#93A59F; --ink3:#6B7D77;
  --line:#26312D; --line2:#1E2825; --accent:#3FD39C;
  --ok:#48D49F; --ok-bg:#12332A; --warn:#E8B15C; --warn-bg:#33260F;
  --crit:#F2818F; --crit-bg:#38191F; --info:#6FB4F5; --info-bg:#14283C;
  --mono:"Cascadia Code","Cascadia Mono",Consolas,ui-monospace,monospace;
  --ui:"Segoe UI Variable Display","Segoe UI",system-ui,-apple-system,sans-serif;
}}
@media (prefers-color-scheme: light) {{
  :root:not([data-theme="dark"]) {{
    --ground:#F5F7F6; --surface:#FFFFFF; --surface2:#EBEFED;
    --ink:#121D19; --ink2:#55665F; --ink3:#82938D;
    --line:#D9E1DE; --line2:#E7EDEA; --accent:#0B7A57;
    --ok:#0B7A57; --ok-bg:#DDF0E8; --warn:#965900; --warn-bg:#F8EAD2;
    --crit:#A32C3E; --crit-bg:#F8DFE3; --info:#1D5FA8; --info-bg:#DCE9F7;
  }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--ui); font-size:14.5px; line-height:1.5;
  -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width:1120px; margin:0 auto; padding:26px 20px 60px;
  display:flex; flex-direction:column; gap:22px; }}
header {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; }}
h1 {{ font-size:24px; margin:0; font-weight:650; letter-spacing:-.02em; }}
h2 {{ font-size:16px; margin:0 0 10px; font-weight:640; }}
.card {{ background:var(--surface); border:1px solid var(--line);
  border-radius:10px; padding:16px 17px; }}
.status {{ display:flex; align-items:center; gap:10px; }}
.chip {{ display:inline-flex; align-items:center; gap:7px; font-family:var(--mono);
  font-size:11.5px; padding:6px 11px; border-radius:999px;
  border:1px solid var(--line); background:var(--surface); }}
.chip .dot {{ width:7px; height:7px; border-radius:50%; background:var(--ok);
  box-shadow:0 0 0 3px var(--ok-bg); }}
.chip.stale .dot {{ background:var(--warn); box-shadow:0 0 0 3px var(--warn-bg); }}
.chip.off .dot {{ background:var(--crit); box-shadow:0 0 0 3px var(--crit-bg); }}
button {{ font-family:var(--ui); font-size:12.5px; font-weight:560;
  color:var(--ink); background:var(--surface); border:1px solid var(--line);
  border-radius:999px; padding:6px 14px; cursor:pointer;
  transition:border-color .15s, background .15s; }}
button:hover {{ border-color:var(--accent); background:var(--surface2); }}
button:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
button[disabled] {{ opacity:.5; cursor:default; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:11px; }}
.tile {{ background:var(--surface); border:1px solid var(--line);
  border-radius:10px; padding:14px 15px; display:flex; flex-direction:column; gap:2px; }}
.tile .l {{ font-size:12.5px; color:var(--ink2); }}
.tile .v {{ font-size:25px; font-weight:660; letter-spacing:-.02em;
  font-variant-numeric:tabular-nums; }}
.tile.crit .v {{ color:var(--crit); }}
.tile.ok .v {{ color:var(--ok); }}
.scroll {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th {{ text-align:left; font-family:var(--mono); font-size:10.5px; letter-spacing:.05em;
  text-transform:uppercase; color:var(--ink3); font-weight:600;
  padding:0 12px 7px 0; border-bottom:1px solid var(--line); white-space:nowrap; }}
td {{ padding:8px 12px 8px 0; border-bottom:1px solid var(--line2); vertical-align:middle; }}
tr:last-child td {{ border-bottom:0; }}
td.num {{ font-family:var(--mono); font-size:12.5px; font-variant-numeric:tabular-nums;
  white-space:nowrap; color:var(--ink2); }}
td.nm {{ font-weight:560; }}
td.nm small {{ display:block; font-family:var(--mono); font-size:10px;
  color:var(--ink3); font-weight:400; }}
td.dim {{ color:var(--ink3); font-size:12.5px; }}
td.need {{ white-space:nowrap; }}
td.need .pct {{ font-family:var(--mono); font-weight:660; font-variant-numeric:tabular-nums; }}
td.need .lab {{ font-family:var(--mono); font-size:10px; text-transform:uppercase;
  letter-spacing:.04em; margin-left:6px; color:var(--ink3); }}
tr.u-critical td.need .pct {{ color:var(--crit); }}
tr.u-urgent td.need .pct {{ color:var(--warn); }}
tr.u-done td.need .pct {{ color:var(--ok); }}
.f {{ display:inline-block; width:24px; height:13px; border-radius:3px;
  background:var(--surface2); border:1px solid var(--line); margin-right:3px; }}
.f.on {{ background:var(--ok); border-color:var(--ok); }}
.pill {{ font-family:var(--mono); font-size:10px; letter-spacing:.04em;
  text-transform:uppercase; padding:2.5px 7px; border-radius:4px; font-weight:650; }}
.p-ok {{ color:var(--ok); background:var(--ok-bg); }}
.p-partial {{ color:var(--warn); background:var(--warn-bg); }}
.p-blind {{ color:var(--crit); background:var(--crit-bg); }}
.cols {{ display:grid; grid-template-columns:1.25fr 1fr; gap:16px; align-items:start; }}
@media (max-width:880px) {{ .cols {{ grid-template-columns:1fr; }} }}
.cd {{ display:inline-block; width:7px; height:7px; border-radius:2px; }}
.qhead {{ display:flex; align-items:baseline; justify-content:space-between; gap:8px; margin-bottom:2px; }}
.qhead h2 {{ margin:0; }}
.qcount {{ font-family:var(--mono); font-size:11.5px; color:var(--ink3); white-space:nowrap; }}
.fchips {{ display:flex; flex-wrap:wrap; gap:7px; margin-bottom:8px; }}
.fchip {{ font-family:var(--ui); font-size:12.5px; background:transparent;
  border:1px solid var(--line); color:var(--ink2); border-radius:999px;
  padding:5px 12px; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }}
.fchip:hover {{ border-color:var(--ink3); color:var(--ink); }}
.fchip[aria-pressed="true"] {{ border-color:var(--accent); background:var(--surface2);
  color:var(--ink); font-weight:560; }}
.fselect {{ font-family:var(--ui); font-size:12.5px; color:var(--ink); background:var(--surface);
  border:1px solid var(--line); border-radius:8px; padding:6px 10px; margin-bottom:12px;
  max-width:100%; }}
.fselect:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
.fmore {{ display:block; width:100%; margin-top:4px; font-family:var(--ui); font-size:12.5px;
  font-weight:560; color:var(--ink2); background:var(--surface2); border:1px solid var(--line);
  border-radius:8px; padding:9px; cursor:pointer; }}
.fmore:hover {{ border-color:var(--accent); color:var(--ink); }}
.fmore[hidden] {{ display:none; }}
.q[hidden] {{ display:none; }}
.feed {{ display:flex; flex-direction:column; gap:9px; }}
.q {{ border:1px solid var(--line); border-left:3px solid var(--line);
  border-radius:8px; padding:11px 13px; display:flex; flex-direction:column; gap:6px;
  cursor:pointer; }}
.q:hover {{ border-color:var(--ink3); }}
.q:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
.q-ok {{ border-left-color:var(--ok); }} .q-info {{ border-left-color:var(--info); }}
.q-crit {{ border-left-color:var(--crit); }} .q-mute {{ border-left-color:var(--ink3); }}
.q-top {{ display:flex; flex-wrap:wrap; align-items:center; gap:7px; }}
.who {{ font-weight:620; font-size:13.5px; display:inline-flex; align-items:center; gap:6px; }}
.q-text {{ margin:0; font-size:13.5px; color:var(--ink2); }}
.q-src {{ font-size:12px; color:var(--ink3); }}
.q-src a {{ color:var(--accent); text-decoration:none; }}
.q-src a:hover {{ text-decoration:underline; }}
.q-foot {{ display:flex; flex-wrap:wrap; gap:10px; font-family:var(--mono);
  font-size:10.5px; color:var(--ink3); }}
.q-panel {{ margin-top:6px; padding-top:10px; border-top:1px dashed var(--line);
  display:flex; flex-direction:column; gap:8px; cursor:default; }}
.q-panel[hidden] {{ display:none; }}
.q-panel-row {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
.qbtn {{ font-family:var(--ui); font-size:12.5px; font-weight:560; color:var(--ink);
  background:var(--surface2); border:1px solid var(--line); border-radius:7px;
  padding:6px 13px; cursor:pointer; }}
.qbtn:hover:not(:disabled) {{ border-color:var(--accent); }}
.qbtn:disabled {{ opacity:.5; cursor:default; }}
.qbtn.qreply {{ background:var(--accent-soft); border-color:var(--accent); color:var(--ink); }}
.qbox {{ width:100%; font-family:var(--ui); font-size:13px; color:var(--ink);
  background:var(--surface2); border:1px solid var(--line); border-radius:8px;
  padding:9px 11px; resize:vertical; }}
.qbox:focus-visible {{ outline:2px solid var(--accent); outline-offset:1px; }}
.qbox:disabled {{ opacity:.6; }}
.qmsg {{ font-size:12px; color:var(--ink2); }}
.qmsg.qerr {{ color:var(--crit); }}
.qmsg.qok {{ color:var(--ok); }}
.qhint {{ font-size:11.5px; color:var(--ink3); }}
.p-info {{ color:var(--info); background:var(--info-bg); }}
.p-crit {{ color:var(--crit); background:var(--crit-bg); }}
.p-mute {{ color:var(--ink3); background:var(--surface2); }}
.gaps {{ display:flex; flex-direction:column; gap:8px; }}
.gap {{ display:grid; grid-template-columns:1fr auto; gap:4px 12px; align-items:center;
  border:1px solid var(--line); border-radius:8px; padding:10px 12px; cursor:pointer; }}
.gap:hover {{ border-color:var(--ink3); }}
.gap:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
.gname {{ font-weight:620; font-size:13.5px; }}
.gcount {{ font-family:var(--mono); font-size:15px; font-weight:650; color:var(--crit);
  font-variant-numeric:tabular-nums; }}
.caret {{ font-family:var(--mono); font-size:10px; color:var(--ink3); margin-left:6px; }}
.gbar {{ grid-column:1/-1; height:4px; border-radius:2px; background:var(--surface2);
  overflow:hidden; margin-top:3px; }}
.gbar span {{ display:block; height:100%; background:var(--crit); border-radius:2px; }}
.gq {{ grid-column:1/-1; margin-top:8px; padding-top:9px;
  border-top:1px dashed var(--line); display:flex; flex-direction:column; gap:6px; }}
.gq[hidden] {{ display:none; }}
.gq-item {{ font-size:12.5px; color:var(--ink2); display:flex; flex-direction:column; gap:2px; }}
.gq-who {{ font-family:var(--mono); font-size:10.5px; color:var(--ink3); }}
.gq-act {{ margin-top:4px; font-family:var(--mono); font-size:10.5px; color:var(--accent); }}
.prow[hidden] {{ display:none; }}
.dim {{ color:var(--ink3); font-size:13px; }}
ol.queue {{ margin:0; padding-left:20px; display:flex; flex-direction:column; gap:7px; }}
ol.queue li {{ font-size:13.5px; }}
.qp {{ font-family:var(--mono); font-size:11.5px; font-weight:660; margin-right:8px; }}
.qp.u-critical {{ color:var(--crit); }} .qp.u-urgent {{ color:var(--warn); }}
.qm {{ color:var(--ink3); font-size:12.5px; }}
.qd {{ font-family:var(--mono); font-size:11px; color:var(--ink3); }}
.note {{ font-size:13px; color:var(--ink2); border-left:2px solid var(--accent);
  padding:3px 0 3px 12px; margin:12px 0 0; max-width:74ch; }}
footer {{ color:var(--ink3); font-size:12px; border-top:1px solid var(--line);
  padding-top:14px; font-family:var(--mono); }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>LocoDev Operations Panel</h1>
  <div class="status">
    <span class="chip" id="chip"><span class="dot"></span><span id="chiptext">checking…</span></span>
    <button id="refresh" type="button">Update now</button>
  </div>
</header>

<div class="tiles">
  <div class="tile crit"><span class="l">Open questions</span><span class="v">{d['open_q']}</span>
    <span class="l">waiting on you</span></div>
  <div class="tile"><span class="l">Answered</span><span class="v">{d['answer_rate']}%</span>
    <span class="l">of {len(d['questions'])} logged</span></div>
  <div class="tile"><span class="l">Catalog coverage</span><span class="v">{pct}%</span>
    <span class="l">{d['written']} of {d['total_facets']} notes</span></div>
  <div class="tile crit"><span class="l">Critical systems</span><span class="v">{d['critical']}</span>
    <span class="l">{d['urgent']} more urgent</span></div>
  <div class="tile ok"><span class="l">Complete</span><span class="v">{d['complete']}</span>
    <span class="l">of {len(CATALOG)} systems</span></div>
</div>

<div class="cols">
  <section class="card">
    <div class="qhead">
      <h2>Incoming questions</h2>
      <span class="qcount" id="qcount"></span>
    </div>
    <div class="fchips" id="chanFilter">{chan_filter_html}</div>
    <div class="fchips" id="statusFilter">{status_filter_html}</div>
    <select class="fselect" id="sysFilter">{system_options}</select>
    <div class="feed" id="feed">{questions_html}</div>
    <button class="fmore" id="showMore" type="button" hidden>Show more</button>
    <p class="note">Click a question to expand it: Suggest searches your own
    notes for a draft, Reply updates the vault for real and posts to YouTube
    once <code>youtube_oauth_setup.py</code> has been run once.</p>
  </section>

  <section class="card">
    <h2>Gaps to close</h2>
    <div class="gaps">{gaps_html}</div>
    <p class="note">Click a row to see the actual questions behind it. This list is
    written by demand, not by guesswork: every entry is somebody who asked and got
    nothing.</p>
  </section>
</div>

<div class="cols">
  <section class="card">
    <div class="qhead">
      <h2>Who is asking</h2>
      <span class="qcount">{len(d['people'])} people</span>
    </div>
    <div class="scroll">
    <table>
      <thead><tr><th>Who</th><th>Asked</th><th>Open</th><th>Last</th></tr></thead>
      <tbody id="peopleBody">{people_html}</tbody>
    </table>
    </div>
    <button class="fmore" id="peopleMore" type="button"{' hidden' if people_hidden_count <= 0 else ''}>Show {people_hidden_count} more</button>
    <p class="note">Ranked by how many of their questions are still open. A non-subscriber
    who is stuck is a <span class="pill p-partial">hot lead</span>, not a support ticket.</p>
  </section>

  <section class="card">
    <h2>Priority queue</h2>
    <ol class="queue">{queue_html}</ol>
    <p class="note">Need combines how much is missing (overview and setup weigh most,
    since they answer on their own) with real open demand where it exists, the old
    guess only where nobody has asked yet. Demand counts 60%, the gap 40%.</p>
  </section>
</div>

<section class="card">
  <h2>Documentation coverage</h2>
  <div class="scroll">
  <table>
    <thead><tr><th>Need</th><th>System</th>
      <th>Overview · Logic · Setup · Issues · Blueprints</th>
      <th>Done</th><th>Asked</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  </div>
</section>

<section class="card">
  <h2>Videos</h2>
  <div class="scroll">
  <table>
    <thead><tr><th>Video</th><th>Overview · Description · Transcript · Comments</th></tr></thead>
    <tbody>{vid_html}</tbody>
  </table>
  </div>
</section>

<section class="card">
  <h2>What is measured, and what is blind</h2>
  <div class="scroll">
  <table>
    <thead><tr><th>Source</th><th>Volume</th><th>State</th><th>Notes</th></tr></thead>
    <tbody>{instr_html}</tbody>
  </table>
  </div>
  <p class="note">The product has first-class telemetry; the customer has none.
  Wiring the blind channels is what this panel needs to show real questions
  instead of only coverage.</p>
</section>

<footer>
  Generated {d['generated_at']} from {VAULT} · {"live watch mode" if live else "static build"}
</footer>

</div>
<script>
// Incoming questions: three filters (channel, status, system) combined with
// AND, plus a collapse that only grows the visible slice of whatever
// currently matches. All three live in one small state object so a filter
// change and a "show more" click go through the same render path.
(function () {{
  var PAGE = 8;
  var state = {{ ch: 'all', st: 'all', sys: 'all', limit: PAGE }};
  var rows = Array.prototype.slice.call(document.querySelectorAll('#feed .q'));
  var countEl = document.getElementById('qcount');
  var moreBtn = document.getElementById('showMore');

  function matches(row) {{
    return (state.ch === 'all' || row.dataset.ch === state.ch)
      && (state.st === 'all' || row.dataset.st === state.st)
      && (state.sys === 'all' || row.dataset.sys === state.sys);
  }}

  function render() {{
    var matched = rows.filter(matches);
    matched.forEach(function (row, i) {{ row.hidden = i >= state.limit; }});
    rows.filter(function (r) {{ return !matches(r); }}).forEach(function (r) {{ r.hidden = true; }});

    var shown = Math.min(state.limit, matched.length);
    countEl.textContent = matched.length
      ? 'showing ' + shown + ' of ' + matched.length
      : 'no matches';
    moreBtn.hidden = shown >= matched.length;
    if (!moreBtn.hidden) {{
      moreBtn.textContent = 'Show more (' + (matched.length - shown) + ' left)';
    }}
  }}

  function wireGroup(id, key) {{
    document.querySelectorAll('#' + id + ' .fchip').forEach(function (b) {{
      b.addEventListener('click', function () {{
        document.querySelectorAll('#' + id + ' .fchip').forEach(function (o) {{
          o.setAttribute('aria-pressed', String(o === b));
        }});
        state[key] = b.dataset.v;
        state.limit = PAGE;
        render();
      }});
    }});
  }}
  if (!rows.length) {{
    return; // nothing logged yet: leave the empty-state message alone
  }}
  wireGroup('chanFilter', 'ch');
  wireGroup('statusFilter', 'st');

  document.getElementById('sysFilter').addEventListener('change', function (e) {{
    state.sys = e.target.value;
    state.limit = PAGE;
    render();
  }});

  moreBtn.addEventListener('click', function () {{
    state.limit += 20;
    render();
  }});

  render();
}})();

// Question rows expand to a panel: Suggest reads your own notes for a
// starting draft, Reply writes it to the vault for real (and to YouTube too,
// once reply-posting is set up). A successful reply changes the vault, which
// bumps the build epoch, which the status poll below picks up and reloads --
// so this code does not need to hand-patch the row afterward.
document.querySelectorAll('.q').forEach(function (row) {{
  var panel = row.querySelector('.q-panel');
  var box = row.querySelector('.qbox');
  var msg = row.querySelector('.qmsg');
  var suggestBtn = row.querySelector('.qsuggest');
  var replyBtn = row.querySelector('.qreply');

  function setMsg(text, kind) {{
    msg.textContent = text || '';
    msg.className = 'qmsg' + (kind ? ' ' + kind : '');
  }}

  row.addEventListener('click', function (e) {{
    if (panel.contains(e.target)) return; // clicks inside the panel do not toggle it
    var open = !panel.hidden;
    panel.hidden = open;
    row.setAttribute('aria-expanded', String(!open));
  }});
  row.addEventListener('keydown', function (e) {{
    if ((e.key === 'Enter' || e.key === ' ') && e.target === row) {{
      e.preventDefault();
      row.click();
    }}
  }});

  if (suggestBtn) {{
    suggestBtn.addEventListener('click', function () {{
      suggestBtn.disabled = true;
      setMsg('searching your notes…');
      fetch('/suggest', {{
        method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ id: row.dataset.id }}),
      }})
        .then(function (r) {{ return r.json(); }})
        .then(function (r) {{
          suggestBtn.disabled = false;
          if (!r.ok) {{ setMsg(r.error || 'failed', 'qerr'); return; }}
          if (!r.text) {{ setMsg('Nothing in your notes matches this yet.', 'qerr'); return; }}
          box.value = r.text;
          setMsg('from ' + r.source, 'qok');
        }})
        .catch(function () {{ suggestBtn.disabled = false; setMsg('request failed', 'qerr'); }});
    }});
  }}

  if (replyBtn) {{
    replyBtn.addEventListener('click', function () {{
      var text = box.value.trim();
      if (!text) {{ setMsg('write or generate a reply first', 'qerr'); return; }}
      replyBtn.disabled = true;
      box.disabled = true;
      setMsg('sending…');
      fetch('/reply', {{
        method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ id: row.dataset.id, text: text }}),
      }})
        .then(function (r) {{ return r.json(); }})
        .then(function (r) {{
          if (!r.ok) {{
            replyBtn.disabled = false; box.disabled = false;
            setMsg(r.error || 'failed', 'qerr');
            return;
          }}
          setMsg('Vault updated. ' + r.platform_message,
                r.posted_to_platform ? 'qok' : 'qerr');
          // The vault changed; the live status poll reloads the page shortly.
        }})
        .catch(function () {{
          replyBtn.disabled = false; box.disabled = false;
          setMsg('request failed', 'qerr');
        }});
    }});
  }}
}});

// "Who is asking" table: reveal the rest in one click, no re-filtering needed.
var peopleMore = document.getElementById('peopleMore');
if (peopleMore) {{
  peopleMore.addEventListener('click', function () {{
    document.querySelectorAll('#peopleBody .prow[hidden]').forEach(function (r) {{
      r.hidden = false;
    }});
    peopleMore.hidden = true;
  }});
}}

// Gap rows expand to show the questions behind the number.
document.querySelectorAll('.gap').forEach(function (g) {{
  function toggle() {{
    var box = g.querySelector('.gq');
    if (!box) return;
    var open = !box.hidden;
    box.hidden = open;
    g.setAttribute('aria-expanded', String(!open));
    var c = g.querySelector('.caret');
    if (c) c.textContent = open ? '\\u25b8' : '\\u25be';
  }}
  g.addEventListener('click', toggle);
  g.addEventListener('keydown', function (e) {{
    if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); toggle(); }}
  }});
}});

var BUILT = {d['epoch']};
var LIVE = {str(live).lower()};
var chip = document.getElementById('chip');
var text = document.getElementById('chiptext');
var btn = document.getElementById('refresh');

function ago(sec) {{
  if (sec < 5) return 'just now';
  if (sec < 60) return sec + 's ago';
  if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
  return Math.floor(sec / 3600) + 'h ago';
}}

function paint(state, msg) {{
  chip.className = 'chip' + (state ? ' ' + state : '');
  text.textContent = msg;
}}

if (!LIVE) {{
  paint('stale', 'static file · run panel.py --watch for live updates');
  btn.disabled = true;
}} else {{
  var lastSeen = BUILT;
  setInterval(function () {{
    fetch('/status.json?t=' + Date.now(), {{ cache: 'no-store' }})
      .then(function (r) {{ return r.json(); }})
      .then(function (s) {{
        if (s.epoch > lastSeen) {{ location.reload(); return; }}
        var age = Math.max(0, Math.floor(Date.now() / 1000) - s.epoch);
        if (s.building) paint('stale', 'rebuilding…');
        else paint('', 'live · updated ' + ago(age));
      }})
      .catch(function () {{ paint('off', 'watcher stopped · start panel.py --watch'); }});
  }}, 2000);

  btn.addEventListener('click', function () {{
    btn.disabled = true;
    paint('stale', 'rebuilding…');
    fetch('/rebuild', {{ method: 'POST' }})
      .then(function () {{ setTimeout(function () {{ location.reload(); }}, 400); }})
      .catch(function () {{ paint('off', 'watcher stopped'); btn.disabled = false; }});
  }});
}}
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Build + watch
# --------------------------------------------------------------------------

_state = {"epoch": 0, "building": False}


def build(live: bool) -> dict:
    _state["building"] = True
    data = scan()
    out = VAULT / "Panel"
    out.mkdir(parents=True, exist_ok=True)
    (out / "00 - Operations Center.md").write_text(render_markdown(data), encoding="utf-8")
    (out / "panel.html").write_text(render_html(data, live), encoding="utf-8")
    (out / "status.json").write_text(
        json.dumps({"epoch": data["epoch"], "generated_at": data["generated_at"],
                    "building": False}),
        encoding="utf-8")
    _state["epoch"] = data["epoch"]
    _state["building"] = False
    return data


def fingerprint() -> tuple:
    """Cheap change detector: (path, mtime, size) for every note in the vault."""
    items = []
    for p in VAULT.rglob("*.md"):
        if p.parent.name == "Panel":
            continue  # the panel writes here; watching it would loop
        try:
            st = p.stat()
        except OSError:
            continue
        items.append((str(p), st.st_mtime_ns, st.st_size))
    return tuple(sorted(items))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(VAULT / "Panel"), **kw)

    def do_GET(self):  # noqa: N802
        if self.path == "/" or self.path.startswith("/index"):
            self.path = "/panel.html"
        if self.path.startswith("/status.json"):
            body = json.dumps({
                "epoch": _state["epoch"],
                "building": _state["building"],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
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
            data = build(live=True)
            print(f"[{data['generated_at']}] change detected, panel rebuilt "
                  f"({data['written']}/{data['total_facets']} notes written)")


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
