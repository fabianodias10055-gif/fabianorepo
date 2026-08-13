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
import http.server
import json
import re
import socketserver
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path


VAULT = Path(r"F:\LocoDev Vault")
LEGACY_VAULT = Path(r"C:\Users\LocoDevPC\Documents\Vaults")
PORT = 8765
POLL_SECONDS = 2.0

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

# Observed demand. Manual today because no question is recorded anywhere; once
# capture exists this comes from the database.
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

def strip_template(text: str) -> str:
    """Remove frontmatter, guide comments and headings, leaving author prose."""
    body = re.sub(r"^---.*?---", "", text, count=1, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"^\s*[#|>*\-\d.]+.*$", "", body, flags=re.M)
    return body.strip()


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


def parse_questions() -> list[dict]:
    """Read the hand written question inbox.

    Deliberately forgiving: a missing field becomes 'unknown' rather than an
    error, because the whole point is that pasting a question costs seconds.
    """
    inbox = VAULT / "Inbox"
    if not inbox.is_dir():
        return []

    out = []
    # Every note in Inbox/ counts: the one you write by hand and the ones the
    # collectors append to.
    for note in sorted(inbox.glob("*.md")):
        text = note.read_text(encoding="utf-8", errors="replace")

        # Strip frontmatter first, otherwise its closing --- is mistaken for the
        # separator below and the whole instructions block gets parsed as data.
        text = re.sub(r"^---.*?\n---\n", "", text, count=1, flags=re.S)
        # Fenced code blocks hold the format example: never read them as questions.
        text = re.sub(r"```.*?```", "", text, flags=re.S)

        parts = text.split("\n---\n", 1)
        body = parts[1] if len(parts) > 1 else text

        matches = list(QUESTION_HEAD.finditer(body))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            block = body[start:end]

            fields = {}
            for line in block.splitlines():
                fm = re.match(
                    r"^(channel|system|status|subscriber|source):\s*(.*)$", line.strip())
                if fm:
                    fields[fm.group(1)] = fm.group(2).strip().lower()
            prose = "\n".join(
                l for l in block.splitlines()
                if l.strip()
                and not re.match(r"^(channel|system|status|subscriber|source):", l.strip())
            ).strip()

            system = fields.get("system", "-")
            out.append({
                "date": m.group(1),
                "who": m.group(2),
                "channel": fields.get("channel", "unknown"),
                "system": system,
                "system_name": NAME_BY_SLUG.get(system, system),
                "status": fields.get("status", "unknown"),
                "subscriber": fields.get("subscriber", "unknown"),
                "source": fields.get("source", ""),
                "text": " ".join(prose.split()),
            })

    out.sort(key=lambda q: q["date"], reverse=True)
    return out


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
    systems = [measure_system(slug, name) for slug, name, _c in CATALOG]
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

    questions = parse_questions()
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
        "- **Bot confidence log**: what it answered, what it declined and with",
        "  what score. Needs the answer path to write a row per question.",
        "",
        "The demand column in the coverage table is also **estimated by hand**.",
        "Once the confidence log exists, it comes from there instead.",
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
        q_rows.append(
            f'<div class="q q-{cls}" data-ch="{esc(q["channel"])}">'
            f'<div class="q-top">'
            f'<span class="who"><i class="cd" style="background:{colour}"></i>{esc(q["who"])}</span>'
            f'<span class="pill p-{cls}">{esc(q["status"])}</span>{sub}</div>'
            f'<p class="q-text">"{esc(q["text"])}"</p>'
            f'<div class="q-foot"><span>{sysname}</span>'
            f'<span>{esc(q["channel"])}</span><span>{q["date"]}</span></div></div>'
        )
    questions_html = "".join(q_rows) or '<p class="dim">No questions logged yet. Paste one into Inbox/00 - Questions.md</p>'

    chans = sorted({q["channel"] for q in d["questions"]})
    filter_html = '<button class="fchip" data-ch="all" aria-pressed="true">All</button>' + "".join(
        f'<button class="fchip" data-ch="{esc(c)}" aria-pressed="false">'
        f'<i class="cd" style="background:{CHANNELS.get(c, "var(--ink3)")}"></i>{esc(c)}</button>'
        for c in chans
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

    # --- people -------------------------------------------------------------
    people_rows = []
    for p in d["people"]:
        colour = CHANNELS.get(p["channel"], "var(--ink3)")
        if p["subscriber"] == "yes":
            tag = '<span class="pill p-ok">subscriber</span>'
        elif p["subscriber"] == "no":
            tag = '<span class="pill p-mute">not a subscriber</span>'
        else:
            tag = '<span class="pill p-mute">unknown</span>'
        lead = '<span class="pill p-partial">hot lead</span>' if p["lead"] else ""
        people_rows.append(
            f'<div class="person"><div class="pname">'
            f'<i class="cd" style="background:{colour}"></i>{esc(p["who"])}{tag}{lead}</div>'
            f'<div class="pmeta">{p["asked"]} asked · {p["open"]} open · last {p["last"]}</div></div>'
        )
    people_html = "".join(people_rows) or '<p class="dim">Nobody logged yet.</p>'

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
.fchips {{ display:flex; flex-wrap:wrap; gap:7px; margin-bottom:12px; }}
.fchip {{ font-family:var(--ui); font-size:12.5px; background:transparent;
  border:1px solid var(--line); color:var(--ink2); border-radius:999px;
  padding:5px 12px; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }}
.fchip:hover {{ border-color:var(--ink3); color:var(--ink); }}
.fchip[aria-pressed="true"] {{ border-color:var(--accent); background:var(--surface2);
  color:var(--ink); font-weight:560; }}
.feed {{ display:flex; flex-direction:column; gap:9px; }}
.q {{ border:1px solid var(--line); border-left:3px solid var(--line);
  border-radius:8px; padding:11px 13px; display:flex; flex-direction:column; gap:6px; }}
.q-ok {{ border-left-color:var(--ok); }} .q-info {{ border-left-color:var(--info); }}
.q-crit {{ border-left-color:var(--crit); }} .q-mute {{ border-left-color:var(--ink3); }}
.q-top {{ display:flex; flex-wrap:wrap; align-items:center; gap:7px; }}
.who {{ font-weight:620; font-size:13.5px; display:inline-flex; align-items:center; gap:6px; }}
.q-text {{ margin:0; font-size:13.5px; color:var(--ink2); }}
.q-foot {{ display:flex; flex-wrap:wrap; gap:10px; font-family:var(--mono);
  font-size:10.5px; color:var(--ink3); }}
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
.people {{ display:flex; flex-direction:column; gap:8px; }}
.person {{ border:1px solid var(--line); border-radius:8px; padding:10px 12px; }}
.pname {{ font-weight:620; font-size:13.5px; display:flex; align-items:center;
  gap:7px; flex-wrap:wrap; }}
.pmeta {{ font-family:var(--mono); font-size:10.5px; color:var(--ink3);
  font-variant-numeric:tabular-nums; margin-top:3px; }}
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
    <h2>Incoming questions</h2>
    <div class="fchips" id="chans">{filter_html}</div>
    <div class="feed" id="feed">{questions_html}</div>
    <p class="note">Written by hand in <code>Inbox/00 - Questions.md</code>.
    Paste a question when it arrives and this updates within seconds.</p>
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
    <h2>Who is asking</h2>
    <div class="people">{people_html}</div>
  </section>

  <section class="card">
    <h2>Priority queue</h2>
    <ol class="queue">{queue_html}</ol>
    <p class="note">Need combines how much is missing (overview and setup weigh most,
    since they answer on their own) with how many people asked. Demand counts 60%,
    the gap 40%.</p>
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
// Channel filter on the incoming feed.
var chips = document.querySelectorAll('#chans .fchip');
chips.forEach(function (b) {{
  b.addEventListener('click', function () {{
    chips.forEach(function (o) {{ o.setAttribute('aria-pressed', String(o === b)); }});
    var want = b.dataset.ch;
    document.querySelectorAll('#feed .q').forEach(function (q) {{
      q.style.display = (want === 'all' || q.dataset.ch === want) ? '' : 'none';
    }});
  }});
}});

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

    def do_POST(self):  # noqa: N802
        if self.path == "/rebuild":
            build(live=True)
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
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
