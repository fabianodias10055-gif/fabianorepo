#!/usr/bin/env python3
"""Pull each video's spoken transcript into its folder in the vault.

Why this exists: every system's notes are still empty templates, so the
panel's Suggest and Ask Claude keep answering "the vault does not cover
this" for questions the videos answer out loud. The transcript is the
largest body of knowledge the channel already produced and the only one
that was never written down anywhere searchable.

Why yt-dlp and not the Data API: captions.download costs 200 quota units
per video plus 50 to list, so 159 videos is about 39,750 units against a
10,000/day ceiling, roughly four days of collecting. yt-dlp reads the same
caption tracks the web player uses, with no quota and no OAuth. The API
route stays available as a fallback for anything yt-dlp cannot fetch.

Manual captions are preferred over automatic ones: they are punctuated and
correctly spelled, which matters when the text is going to be searched for
node and variable names. Automatic captions are used when that is all there
is, and the note says which one it got so nobody mistakes a machine
transcript for an edited one.

Usage:
    python collect_transcripts.py --dry-run
    python collect_transcripts.py --limit 5
    python collect_transcripts.py
    python collect_transcripts.py --force        refetch everything
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None

VAULT = Path(r"F:\LocoDev Vault")

# Preference order. json3 carries start times per segment and needs no
# timestamp parsing; vtt is the fallback every track has.
FORMATS = ("json3", "vtt")
LANG_PREFS = ("en", "en-US", "en-GB", "en-orig")

# Roughly one paragraph per this many characters, each stamped with the
# time it starts, so an answer can cite the minute to watch.
PARA_CHARS = 320
MIN_USEFUL = 400  # characters below which a transcript is not worth keeping


def _stamp(ms: int) -> str:
    total = int(ms // 1000)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_json3(raw: str) -> list[tuple[int, str]]:
    """[(start_ms, text)] from YouTube's json3 caption format."""
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    out = []
    for ev in data.get("events") or []:
        segs = ev.get("segs") or []
        text = "".join(sg.get("utf8", "") for sg in segs)
        text = " ".join(text.split())
        if text:
            out.append((int(ev.get("tStartMs", 0)), text))
    return out


_VTT_TIME = re.compile(
    r"^(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s", re.M)


def parse_vtt(raw: str) -> list[tuple[int, str]]:
    out = []
    cur_ms = None
    buf: list[str] = []
    for line in raw.splitlines():
        m = _VTT_TIME.match(line)
        if m:
            if cur_ms is not None and buf:
                text = " ".join(" ".join(buf).split())
                if text:
                    out.append((cur_ms, text))
            h = int(m.group(1) or 0)
            cur_ms = ((h * 3600 + int(m.group(2)) * 60 + int(m.group(3))) * 1000
                      + int(m.group(4)))
            buf = []
            continue
        if cur_ms is None:
            continue
        if line.strip() in ("", "WEBVTT") or line.strip().isdigit():
            continue
        # Inline karaoke timing tags and positioning cruft.
        buf.append(re.sub(r"<[^>]+>", "", line).strip())
    if cur_ms is not None and buf:
        text = " ".join(" ".join(buf).split())
        if text:
            out.append((cur_ms, text))
    return out


def dedupe(cues: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Automatic captions repeat the previous line as the caption rolls, so
    a raw dump is roughly double length and reads badly. Keep only what each
    cue adds to the one before it."""
    out: list[tuple[int, str]] = []
    prev = ""
    for ms, text in cues:
        if not text or text == prev:
            continue
        if prev and text.startswith(prev):
            text = text[len(prev):].strip()
            if not text:
                continue
        out.append((ms, text))
        prev = out[-1][1] if not prev else text
        prev = text
    return out


def paragraphs(cues: list[tuple[int, str]]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    start = None
    buf: list[str] = []
    for ms, text in cues:
        if start is None:
            start = ms
        buf.append(text)
        if sum(len(b) for b in buf) >= PARA_CHARS:
            out.append((start, " ".join(buf)))
            start, buf = None, []
    if buf:
        out.append((start or 0, " ".join(buf)))
    return out


def pick_track(info: dict) -> tuple[str, str, bool] | None:
    """(url, lang, is_auto) for the best available English caption track."""
    for source, is_auto in ((info.get("subtitles") or {}, False),
                            (info.get("automatic_captions") or {}, True)):
        for lang in LANG_PREFS:
            tracks = source.get(lang)
            if not tracks:
                continue
            by_ext = {t.get("ext"): t.get("url") for t in tracks if t.get("url")}
            for ext in FORMATS:
                if by_ext.get(ext):
                    return by_ext[ext], lang, is_auto
    return None


def existing_videos() -> list[tuple[str, Path]]:
    """(video_id, folder) for every collected video, newest first."""
    out = []
    root = VAULT / "YouTube" / "Videos"
    if not root.is_dir():
        return out
    # Videos may sit in category subfolders (YT Tutorials/ etc), so recurse.
    for note in sorted(root.rglob("00 - Overview.md"), reverse=True):
        text = note.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^video_id:\s*(\S+)", text, re.M)
        if m:
            out.append((m.group(1), note.parent))
    return out


def has_transcript(folder: Path) -> bool:
    path = folder / "02 - Transcript.md"
    if not path.is_file():
        return False
    body = re.sub(r"^---.*?---", "", path.read_text(encoding="utf-8", errors="replace"),
                  count=1, flags=re.S)
    return len(body.strip()) >= MIN_USEFUL


def write_transcript(folder: Path, video_id: str, lang: str, is_auto: bool,
                     paras: list[tuple[int, str]], dry: bool) -> int:
    words = sum(len(t.split()) for _ms, t in paras)
    lines = [
        "---",
        f"video: {folder.name}",
        f"video_id: {video_id}",
        f"url: https://www.youtube.com/watch?v={video_id}",
        "facet: transcript",
        f"language: {lang}",
        f"caption_source: {'automatic' if is_auto else 'manual'}",
        f"words: {words}",
        f"collected: {time.strftime('%Y-%m-%d %H:%M')}",
        "---",
        "",
        f"# Transcript: {folder.name}",
        "",
        "Collected by `collect_transcripts.py`. **Do not edit by hand.**",
        "",
    ]
    if is_auto:
        lines += [
            "> Automatic captions: YouTube's speech recognition, so node and",
            "> variable names are often misspelled. Good enough to find the",
            "> moment, not to quote verbatim.",
            "",
        ]
    for ms, text in paras:
        url = f"https://www.youtube.com/watch?v={video_id}&t={ms // 1000}s"
        lines.append(f"**[{_stamp(ms)}]({url})** {text}")
        lines.append("")

    if not dry:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "02 - Transcript.md").write_text("\n".join(lines) + "\n",
                                                   encoding="utf-8")
    return words


def fetch(video_id: str) -> tuple[list[tuple[int, str]], str, bool] | None:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "writesubtitles": False, "extract_flat": False,
            "socket_timeout": 30, "retries": 2}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}",
                                download=False)
        picked = pick_track(info)
        if not picked:
            return None
        url, lang, is_auto = picked
        raw = ydl.urlopen(url).read().decode("utf-8", errors="replace")
    cues = parse_json3(raw) if raw.lstrip().startswith("{") else parse_vtt(raw)
    return dedupe(cues), lang, is_auto


def main() -> int:
    global VAULT

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true",
                    help="refetch videos that already have a transcript")
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="seconds between videos, to stay polite")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Several video titles contain emoji, and the Windows console is cp1252:
    # printing a progress line for one of those killed a run mid-collection.
    # Reconfiguring the stream is the fix, not stripping the names.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    VAULT = Path(args.vault)
    if YoutubeDL is None:
        print("ERROR: yt-dlp is not installed. pip install yt-dlp")
        return 1
    if not (VAULT / "YouTube" / "Videos").is_dir():
        print(f"ERROR: no video folders under {VAULT}")
        return 1

    videos = existing_videos()
    todo = [(v, f) for v, f in videos if args.force or not has_transcript(f)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"videos: {len(videos)} · already have a transcript: "
          f"{len(videos) - len([1 for v, f in videos if not has_transcript(f)])} "
          f"· to fetch now: {len(todo)}")

    done = auto = skipped = failed = 0
    total_words = 0
    t0 = time.time()
    for i, (video_id, folder) in enumerate(todo, 1):
        label = folder.name[:58]
        try:
            got = fetch(video_id)
        except Exception as exc:  # noqa: BLE001 - one bad video must not end the run
            print(f"[{i}/{len(todo)}] FAILED {label}: {type(exc).__name__}")
            failed += 1
            continue
        if not got or not got[0]:
            print(f"[{i}/{len(todo)}] no captions  {label}")
            skipped += 1
            continue
        cues, lang, is_auto = got
        paras = paragraphs(cues)
        words = write_transcript(folder, video_id, lang, is_auto, paras, args.dry_run)
        if words * 6 < MIN_USEFUL:
            print(f"[{i}/{len(todo)}] too short    {label}")
            skipped += 1
            continue
        total_words += words
        done += 1
        auto += 1 if is_auto else 0
        kind = "auto" if is_auto else "manual"
        print(f"[{i}/{len(todo)}] {words:6,} words  {kind:6s} {label}")
        if args.sleep and i < len(todo):
            time.sleep(args.sleep)

    verb = "would be " if args.dry_run else ""
    print(f"\ntranscripts {verb}written: {done} ({auto} automatic, "
          f"{done - auto} manual) · no captions: {skipped} · failed: {failed}")
    print(f"words collected: {total_words:,} · {time.time() - t0:.0f}s")
    if done and not args.dry_run:
        print("The panel picks these up on its next rebuild; Ask Claude can now "
              "cite the minute of the video.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
