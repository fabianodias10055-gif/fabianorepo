#!/usr/bin/env python3
"""Point at a series of our own videos from Reference/, without copying it.

Our videos already live in YouTube/Videos/<date title>/, transcript and
all, and that is where the drafting prompt reads them from. Copying them
into Reference/ would put the same transcript in the vault twice, and two
copies of one thing disagreeing is what half of this repo's bugs have been.

So this writes an index instead: one row per video, linking the folder that
holds it and the video itself. Searchable by topic in the same place the
other channels are searched, with nothing duplicated.

Usage:
    python index_own_series.py --match "Learn Blueprints" --name "LocoDev"
"""

import argparse
import re
import sys
from pathlib import Path

import collect_youtube as yt

VAULT = yt.VAULT
FIELD = re.compile(r"^(\w+):\s*(.*)$", re.M)


def frontmatter(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")[:1500]
    return {m.group(1): m.group(2).strip() for m in FIELD.finditer(text)}


def words_in(path: Path) -> int:
    if not path.is_file():
        return 0
    return int(frontmatter(path).get("words") or 0)


def series_folders(match: str) -> list[Path]:
    base = VAULT / "YouTube" / "Videos"
    return sorted(n.parent for n in base.rglob("00 - Overview.md") if match in n.parent.name)


# "2025-03-20 Learn Blueprints #4- Timelines" -> ("4", "Timelines")
_PART = re.compile(r"#(\d+)[-:]?\s*(.*)$")


def part_of(folder_name: str, match: str) -> tuple[int, str]:
    tail = folder_name.split(match, 1)[-1]
    m = _PART.search(tail)
    if not m:
        return (9999, tail.strip(" -"))
    return (int(m.group(1)), m.group(2).strip(" -."))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True,
                    help="text every folder of the series has in its name")
    ap.add_argument("--name", default="LocoDev",
                    help="the folder to write under Reference/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    folders = series_folders(args.match)
    if not folders:
        print(f"no video folders matching {args.match!r}")
        return 1

    rows = []
    for f in folders:
        over = frontmatter(f / "00 - Overview.md")
        vid = over.get("video_id", "")
        num, topic = part_of(f.name, args.match)
        rows.append({
            "num": num, "topic": topic or f.name,
            "folder": f.name, "video_id": vid,
            "words": words_in(f / "02 - Transcript.md"),
        })
    rows.sort(key=lambda r: r["num"])

    have = sum(1 for r in rows if r["words"])
    out = VAULT / "Reference" / yt.safe_name(args.name) / \
        f"00 - {yt.safe_name(args.match)} index.md"

    lines = [
        "---",
        f"series: {args.match}",
        "channel: LocoDev",
        "facet: reference",
        "kind: our-own-videos",
        f"videos: {len(rows)}",
        f"with_transcript: {have}",
        "---",
        "",
        f"# {args.match}",
        "",
        "Ours, indexed here so it sits beside the other channels when you go",
        "looking. The videos themselves live under YouTube/Videos/ and that is",
        "where the transcripts are: this file points, it does not copy, so",
        "there is only ever one version of each transcript in the vault.",
        "",
        "| # | topic | words | transcript | video |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        link = (f"https://www.youtube.com/watch?v={r['video_id']}"
                if r["video_id"] else "")
        note = f"[[{r['folder']}/02 - Transcript\\|open]]" if r["words"] else "none"
        lines.append(f"| {r['num'] if r['num'] < 9999 else ''} "
                     f"| {r['topic'].replace('|', '/')} "
                     f"| {r['words'] or ''} | {note} | {link} |")

    if not args.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {len(rows)} videos ({have} with a transcript) to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
