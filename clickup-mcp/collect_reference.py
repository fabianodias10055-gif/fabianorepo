#!/usr/bin/env python3
"""Index someone else's channel so answers can point at it.

Mathew Wadstein has a video on very nearly every Blueprint node, titled
after the node itself. That makes his catalog the best node index in the
Unreal world, and a link to the right one of his videos answers "what does
this node do" better than a paragraph rewriting it would.

What this collects is the public listing: title, url, date, duration and
the description. It does not collect transcripts. Those are his writing
and his voice, and this vault feeds replies published under someone else's
name; a link sends the person to him, which is both the honest thing and
the more useful one.

Usage:
    python collect_reference.py --handle @MathewWadsteinTutorials --dry-run
    python collect_reference.py --handle @MathewWadsteinTutorials

Quota: about one unit per fifty videos, so a thousand-video channel costs
roughly forty of the ten thousand daily units.
"""

import argparse
import re
import sys
from pathlib import Path

import collect_youtube as yt

VAULT = yt.VAULT
DEST = "Reference"


def channel_by_handle(handle: str) -> dict:
    if not handle.startswith("@"):
        handle = "@" + handle
    data = yt.api_get("channels", {"part": "contentDetails,snippet,statistics",
                                   "forHandle": handle})
    items = data.get("items") or []
    if not items:
        raise SystemExit(f"no channel for {handle}")
    return items[0]


def iso_duration(text: str) -> str:
    """PT1H2M3S as 1:02:03. Length is how you judge whether to send someone
    to a two minute answer or a forty minute build-along."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text or "")
    if not m:
        return ""
    h, mi, sec = (int(x) if x else 0 for x in m.groups())
    return f"{h}:{mi:02d}:{sec:02d}" if h else f"{mi}:{sec:02d}"


def all_videos(uploads: str, limit: int | None) -> list[dict]:
    vids = yt.list_videos(uploads, limit)
    # Durations come from a second endpoint, fifty ids per call.
    ids = [v["id"] for v in vids]
    extra: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        data = yt.api_get("videos", {"part": "contentDetails",
                                     "id": ",".join(ids[i:i + 50])})
        for it in data.get("items", []):
            extra[it["id"]] = it.get("contentDetails", {})
    for v in vids:
        v["duration"] = iso_duration(extra.get(v["id"], {}).get("duration", ""))
    return vids


# His titles are the index, and they come in two shapes: "WTF Is? <node>"
# for what a thing does and "HTF do I? <task>" for how to do one. Both end
# with "in Unreal Engine 4 ( UE4 )" or similar, which is true of every one
# of the thousand and so carries no information here.
_PREFIX = re.compile(
    r"^\s*(?P<kind>WTF\s*Is|What\s*Is|HTF\s*do\s*I|How\s*To\s*Fix)"
    r"\s*[?:.\-]*\s*", re.I)
_SUFFIX = re.compile(
    r"\s*(?:in|for)\s+Unreal\s+Engine[^()]*(?:\(\s*UE\s*\d*\s*\))?\s*$", re.I)

_KINDS = {"wtfis": "what is", "whatis": "what is",
          "htfdoi": "how to", "howtofix": "how to fix"}


def split_title(title: str) -> tuple[str, str]:
    """(kind, topic). Kind is empty for the videos that are neither."""
    raw = (title or "").strip()
    m = _PREFIX.match(raw)
    kind = ""
    if m:
        kind = _KINDS.get(re.sub(r"\s+", "", m.group("kind")).lower(), "")
        raw = raw[m.end():]
    raw = _SUFFIX.sub("", raw).strip(" -–")
    return kind, raw or (title or "").strip()


def write_index(chan: dict, videos: list[dict], dry: bool) -> Path:
    name = chan["snippet"]["title"]
    folder = VAULT / DEST / yt.safe_name(name)
    path = folder / "00 - Video index.md"

    lines = [
        "---",
        f"channel: {name}",
        f"channel_id: {chan['id']}",
        f"url: https://www.youtube.com/channel/{chan['id']}",
        "facet: reference",
        "access: public",
        "kind: someone-elses-channel",
        f"videos: {len(videos)}",
        "---",
        "",
        f"# {name}, every video",
        "",
        "Someone else's channel, indexed so an answer can link to the right",
        "video instead of restating it. Titles, links and lengths only:",
        "no transcripts, because the words are his.",
        "",
        "Search this file by node name. The topic column is the title with",
        '"What Is" stripped off, which is usually the node itself.',
        "",
        "| topic | kind | length | published | link |",
        "|---|---|---|---|---|",
    ]
    for v in sorted(videos, key=lambda x: x.get("published", ""), reverse=True):
        kind, topic = split_title(v["title"])
        lines.append(f"| {topic.replace('|', '/')} | {kind} | {v.get('duration','')} "
                     f"| {v.get('published','')} "
                     f"| https://www.youtube.com/watch?v={v['id']} |")
    text = "\n".join(lines) + "\n"

    if not dry:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle", required=True)
    ap.add_argument("--max-videos", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not yt.get_secret("YOUTUBE_API_KEY"):
        print("ERROR: YOUTUBE_API_KEY is not set")
        return 1

    chan = channel_by_handle(args.handle)
    uploads = chan["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"channel: {chan['snippet']['title']} "
          f"({chan['statistics'].get('videoCount','?')} videos)")

    videos = all_videos(uploads, args.max_videos)
    path = write_index(chan, videos, args.dry_run)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {len(videos)} videos to {path}")
    print(f"quota used: {yt._quota['units']} units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
