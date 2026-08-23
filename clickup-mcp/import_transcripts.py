#!/usr/bin/env python3
"""File caption files somebody sent you into the vault, with their timings.

This imports what a channel owner exported and handed over. It does not
fetch anything: YouTube only serves captions to the account that owns the
video, so the files have to come from them either way, and that same fact
is what keeps the permission attached to something real.

Every note records who allowed it and when. If this text ever shows up
behind a public answer, the reason it was allowed is written next to it
rather than remembered.

Timings are kept, coarsely. "He covers it at 4:12, <link>&t=252s" is worth
more to the person asking than a paragraph of quoted speech, and it is the
form the drafting prompt already uses for LocoDev's own videos.

Usage:
    python import_transcripts.py --from "D:\\mwt captions" \\
        --channel "Mathew Wadstein Tutorials" \\
        --granted-by "Mathew Wadstein" --granted-on 2026-08-22 \\
        --note "email, 2026-08-22" --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

import collect_youtube as yt

VAULT = yt.VAULT
# A YouTube id: eleven of these characters, which is specific enough to
# pick out of a filename and short enough to appear by accident, so it is
# only trusted when the rest of the name looks like a caption export.
_VID = re.compile(r"[A-Za-z0-9_-]{11}")
_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")
_CUE_NUM = re.compile(r"^\d+$")
_TAG = re.compile(r"<[^>]+>")


def seconds_of(h: str, m: str, s: str) -> int:
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse_captions(text: str) -> list[tuple[int, str]]:
    """(second, line) pairs from a WebVTT or SubRip file.

    Both formats are cue blocks separated by blank lines, with a timing
    line holding two stamps. The differences that matter here are the
    header WebVTT puts on top, its inline tags, and SubRip's cue numbers.
    """
    out: list[tuple[int, str]] = []
    at: int | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.upper().startswith("WEBVTT") or _CUE_NUM.match(line):
            continue
        if "-->" in line:
            m = _TS.search(line)
            at = seconds_of(*m.groups()[:3]) if m else None
            continue
        if at is None:
            continue
        clean = _TAG.sub("", line).strip()
        # YouTube's rolling captions repeat the previous line as the top
        # half of the next cue. Kept, the text roughly doubles.
        if clean and (not out or out[-1][1] != clean):
            out.append((at, clean))
    return out


def paragraphs(cues: list[tuple[int, str]], span: int = 30) -> list[tuple[int, str]]:
    """Group cues into readable blocks, each stamped with its start.

    One line per cue is unreadable and unsearchable: a sentence gets split
    across three of them. Thirty seconds a block keeps a thought together
    and still points close enough to be worth linking."""
    blocks: list[tuple[int, str]] = []
    start, words = None, []
    for at, line in cues:
        if start is None:
            start = at
        if at - start >= span and words:
            blocks.append((start, " ".join(words)))
            start, words = at, []
        words.append(line)
    if words and start is not None:
        blocks.append((start, " ".join(words)))
    return blocks


def stamp(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def index_titles(channel: str) -> dict:
    """video_id -> topic, from the index collect_reference.py wrote."""
    path = VAULT / "Reference" / yt.safe_name(channel) / "00 - Video index.md"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5 or "watch?v=" not in cells[-1]:
            continue
        out[cells[-1].rsplit("watch?v=", 1)[1]] = cells[0]
    return out


def video_id_of(path: Path) -> str:
    """The id inside the filename, if the exporter kept it there."""
    stem = path.stem
    for cand in _VID.findall(stem):
        # A bare eleven-character word is a coincidence; one sitting next
        # to a separator is how every exporter writes it.
        if re.search(r"[\[\](){}._\- ]" + re.escape(cand) + r"(?:[\[\](){}._\- ]|$)",
                     stem) or stem == cand:
            return cand
    return ""


def write_note(folder: Path, vid: str, title: str, blocks: list, src: Path,
               grant: dict, dry: bool) -> Path:
    path = folder / f"{vid} - {yt.safe_name(title or vid)[:60]}.md"
    url = f"https://www.youtube.com/watch?v={vid}"
    lines = [
        "---",
        f"video_id: {vid}",
        f"title: {title}",
        f"url: {url}",
        "facet: transcript",
        "kind: someone-elses-channel",
        f"granted_by: {grant['by']}",
        f"granted_on: {grant['on']}",
        f"granted_note: {grant['note']}",
        f"source_file: {src.name}",
        "---",
        "",
        f"# {title or vid}",
        "",
        f"Transcript of somebody else's video, kept here with permission from "
        f"{grant['by']} ({grant['note']}).",
        "",
        "Cite it by linking the moment, not by repeating the words: every",
        f"block below is a start time, so 4:12 is {url}&t=252s.",
        "",
    ]
    for at, text in blocks:
        lines.append(f"**[{stamp(at)}]({url}&t={at}s)** {text}")
        lines.append("")
    if not dry:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True,
                    help="folder of .vtt or .srt files the owner exported")
    ap.add_argument("--channel", required=True)
    ap.add_argument("--granted-by", required=True,
                    help="who gave permission, in their own name")
    ap.add_argument("--granted-on", required=True, help="YYYY-MM-DD")
    ap.add_argument("--note", default="",
                    help="where the permission is recorded: an email, a DM")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.is_dir():
        print(f"ERROR: {src} is not a folder")
        return 1
    if not args.note:
        print("ERROR: --note is required. Say where the permission is written "
              "down, so the file can point at it later.")
        return 1

    grant = {"by": args.granted_by, "on": args.granted_on, "note": args.note}
    titles = index_titles(args.channel)
    folder = VAULT / "Reference" / yt.safe_name(args.channel) / "transcripts"

    files = sorted(p for p in src.rglob("*")
                   if p.suffix.lower() in (".vtt", ".srt"))
    if not files:
        print(f"no .vtt or .srt files under {src}")
        return 1

    done = skipped = 0
    for f in files:
        vid = video_id_of(f)
        if not vid:
            print(f"  skipped, no video id in the name: {f.name}")
            skipped += 1
            continue
        cues = parse_captions(f.read_text(encoding="utf-8", errors="replace"))
        if not cues:
            print(f"  skipped, no cues read: {f.name}")
            skipped += 1
            continue
        blocks = paragraphs(cues)
        write_note(folder, vid, titles.get(vid, ""), blocks, f, grant, args.dry_run)
        done += 1

    verb = "would import" if args.dry_run else "imported"
    print(f"{verb} {done} transcripts into {folder}")
    if skipped:
        print(f"{skipped} skipped")
    if not titles:
        print("note: no video index found for this channel, so titles are "
              "blank. Run collect_reference.py first and re-run to fill them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
