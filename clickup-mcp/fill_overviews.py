#!/usr/bin/env python3
"""Fill each video's 00 - Overview from material the vault already holds.

The Overviews were scaffolding: "What it covers" and "Which system it
teaches" sat empty on all 159 videos, so the one note meant to summarise a
video said nothing, and Ask Claude kept reporting empty templates.

Nothing here is invented. "What it covers" is the chapter list you wrote in
the video's own description, rendered as links that jump to that second.
"Which system it teaches" is the `system:` tag already in the frontmatter,
turned into a link to that system's folder. Where the material does not
exist, the note says so plainly instead of filling the space.

Your own writing is never touched: anything under "## Notes" is carried
through untouched, and a section you have written into by hand is left
exactly as it is.

Usage:
    python fill_overviews.py --dry-run
    python fill_overviews.py
"""

import argparse
import re
import sys
from pathlib import Path

VAULT = Path(r"F:\LocoDev Vault")

# "12:34 Title", "- 1:02:03 - Title", "⌚ 0:00 Intro". The title must contain
# a letter, so a bare duration in prose is not mistaken for a chapter.
CHAPTER = re.compile(
    r"^[\s\-\u2022\u23f0\u231a\U0001f552]*"
    r"(\d{1,2}:\d{2}(?::\d{2})?)"
    r"\s*[-\u2013\u2014:]?\s+"
    r"(?=.*[A-Za-z])(.+?)\s*$"
)


def to_seconds(stamp: str) -> int:
    parts = [int(p) for p in stamp.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^([a-z_]+):\s*(.*)$", line.strip())
        if kv:
            out[kv.group(1)] = kv.group(2).strip()
    return out


def chapters_from(description: str) -> list[tuple[int, str]]:
    out = []
    for line in description.splitlines():
        m = CHAPTER.match(line)
        if not m:
            continue
        title = m.group(2).strip(" -\u2013\u2014:")
        # A "chapter" that is really a URL or a bare hashtag line is noise.
        if not title or title.startswith("http") or len(title) > 120:
            continue
        out.append((to_seconds(m.group(1)), title))
    # Real chapter lists start at or near zero and climb.
    if len(out) < 2 or out[0][0] > 120:
        return []
    return [c for i, c in enumerate(out) if i == 0 or c[0] > out[i - 1][0]]


def stamp(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def keep_notes(body: str) -> str:
    """Whatever the author wrote under Notes, minus the guide comment."""
    m = re.search(r"(?ms)^##\s*Notes\s*$(.*)\Z", body)
    if not m:
        return ""
    notes = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip()
    return notes


def build_body(folder: Path, fm: dict, desc_body: str, has_transcript: bool) -> str:
    vid = fm.get("video_id", "")
    url = f"https://www.youtube.com/watch?v={vid}"
    title = folder.name[11:] if len(folder.name) > 11 else folder.name

    lines = [f"# {title}", "", "## What it covers", ""]
    chapters = chapters_from(desc_body)
    if chapters:
        for sec, name in chapters:
            lines.append(f"- **[{stamp(sec)}]({url}&t={sec}s)** {name}")
        lines += ["", "*Chapters as written in the video's own description.*", ""]
    else:
        lines += [
            "*No chapter list in this video's description.*"
            + (" The spoken content is in `02 - Transcript.md`."
               if has_transcript else ""),
            "",
        ]

    lines += ["## Which system it teaches", ""]
    slug = fm.get("system", "").strip()
    if slug and slug != "-":
        lines += [f"[[Systems/{slug}/00 - Overview|{slug}]]", ""]
    else:
        lines += [
            "*Not tagged.* Set `system:` in the frontmatter above to a folder "
            "slug under `Systems/` so the questions asked under this video are "
            "routed to that system.",
            "",
        ]

    facts = []
    if fm.get("published"):
        facts.append(f"published {fm['published']}")
    if fm.get("views"):
        facts.append(f"{int(fm['views']):,} views")
    if fm.get("comment_count"):
        facts.append(f"{int(fm['comment_count']):,} comments")
    if facts:
        joined = " \u00b7 ".join(facts)
        lines += [f"*{joined}.*", ""]

    lines += ["## Notes", ""]
    notes = keep_notes(desc_body)  # placeholder, replaced by the caller
    return "\n".join(lines), notes


def main() -> int:
    global VAULT

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    VAULT = Path(args.vault)
    root = VAULT / "YouTube" / "Videos"
    if not root.is_dir():
        print(f"ERROR: no video folders under {VAULT}")
        return 1

    filled = with_chapters = kept = skipped = 0
    for note in sorted(root.glob("*/00 - Overview.md")):
        folder = note.parent
        text = note.read_text(encoding="utf-8", errors="replace")
        fm = frontmatter(text)
        head = re.match(r"^---\n.*?\n---\n", text, re.S)
        if not head or not fm.get("video_id"):
            continue
        body = text[head.end():]

        # Anything the author already wrote outside the template stays put.
        author_notes = keep_notes(body)
        template_only = not re.sub(
            r"(?s)<!--.*?-->|^#.*$|^\s*$", "",
            re.sub(r"(?ms)^##\s*Notes\s*$.*\Z", "", body), flags=re.M).strip()
        if not template_only and "Chapters as written" not in body:
            skipped += 1
            continue

        desc_path = folder / "01 - Description.md"
        desc = (desc_path.read_text(encoding="utf-8", errors="replace")
                if desc_path.is_file() else "")
        desc_body = desc.split("---", 2)[-1]
        has_transcript = (folder / "02 - Transcript.md").is_file()

        new_body, _ = build_body(folder, fm, desc_body, has_transcript)
        if author_notes:
            new_body += author_notes + "\n"
            kept += 1
        new_text = text[:head.end()] + new_body

        if "**[" in new_body:
            with_chapters += 1
        if new_text != text:
            filled += 1
            if not args.dry_run:
                note.write_text(new_text, encoding="utf-8")

    verb = "would be " if args.dry_run else ""
    print(f"overviews {verb}filled: {filled} "
          f"(with a chapter list: {with_chapters}) "
          f"\u00b7 hand-written notes preserved: {kept} "
          f"\u00b7 left alone because you had written in them: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
