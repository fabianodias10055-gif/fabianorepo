#!/usr/bin/env python3
"""Collect the LocoDev channel into the vault: videos, descriptions, comments.

The comments your audience already wrote are the FAQ you never had to write.
This pulls them in and, when a comment looks like a question, drops it into the
inbox so it shows up in the panel and ranks the gaps.

Usage:
    python collect_youtube.py --dry-run
    python collect_youtube.py
    python collect_youtube.py --max-videos 5      # try it on a few first

Needs YOUTUBE_API_KEY in the environment or in a .env file. A plain API key is
enough: reading public comments needs no OAuth. Replying would, and this script
deliberately does not reply.

Quota: the daily free budget is 10,000 units. A full first run over ~200 videos
costs roughly 400. After that it is nearly free, because the script only
re-fetches comments for videos whose comment count actually changed.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib import error, parse, request

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional here
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")
    # The bot already keeps a YouTube key; reuse it instead of asking for a second.
    load_dotenv(BASE_DIR.parent / "discord-feedback-bot" / ".env")

API = "https://www.googleapis.com/youtube/v3"
VAULT = Path(r"F:\LocoDev Vault")
CHANNEL_ID = "UCr8NttLeGyLd6m4qVS2Zb8g"  # LocoDev
UA = "LocoDev-KB-Collector/1.0"

# A comment is treated as a question when it ends with a question mark or opens
# with a question word. Deliberately loose: a false positive costs one line in
# the inbox, a false negative costs a customer nobody answered.
QUESTION_WORDS = (
    "how", "what", "why", "when", "where", "which", "who", "can", "could",
    "does", "do", "did", "is", "are", "will", "would", "should", "any",
    "anyone", "is there", "como", "qual", "quando", "onde", "porque", "por que",
    "tem", "da pra", "dá pra", "alguem", "alguém", "quanto",
)
MIN_QUESTION_LEN = 15

_quota = {"units": 0}


def api_get(endpoint: str, params: dict, cost: int = 1) -> dict:
    params = {**params, "key": os.getenv("YOUTUBE_API_KEY", "")}
    req = request.Request(f"{API}/{endpoint}?{parse.urlencode(params)}",
                          headers={"User-Agent": UA})
    try:
        with request.urlopen(req, timeout=30) as resp:
            _quota["units"] += cost
            return json.load(resp)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 403 and "commentsDisabled" in body:
            return {"items": [], "_disabled": True}
        if exc.code == 403 and "quotaExceeded" in body:
            raise SystemExit(
                "YouTube quota exhausted for today. The run stops here; what was "
                "already written stays. Try again after the quota resets "
                "(midnight Pacific)."
            ) from exc
        raise RuntimeError(f"YouTube API {exc.code} on {endpoint}: {body[:300]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"cannot reach YouTube API: {exc.reason}") from exc


def uploads_playlist(channel_id: str) -> str:
    data = api_get("channels", {"part": "contentDetails", "id": channel_id})
    items = data.get("items", [])
    if not items:
        raise SystemExit(f"channel not found: {channel_id}")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def list_videos(playlist_id: str, limit: int | None) -> list[dict]:
    videos, token = [], None
    while True:
        params = {"part": "snippet,contentDetails", "playlistId": playlist_id,
                  "maxResults": 50}
        if token:
            params["pageToken"] = token
        data = api_get("playlistItems", params)
        for it in data.get("items", []):
            sn = it["snippet"]
            videos.append({
                "id": it["contentDetails"]["videoId"],
                "title": sn["title"],
                "published": sn["publishedAt"][:10],
                "description": sn.get("description", ""),
            })
            if limit and len(videos) >= limit:
                return videos
        token = data.get("nextPageToken")
        if not token:
            return videos


def video_stats(ids: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(ids), 50):
        data = api_get("videos", {"part": "statistics", "id": ",".join(ids[i:i + 50])})
        for it in data.get("items", []):
            out[it["id"]] = it.get("statistics", {})
    return out


def fetch_comments(video_id: str, max_pages: int = 10) -> list[dict]:
    """Top level comments plus their replies, newest first."""
    out, token, pages = [], None, 0
    while pages < max_pages:
        params = {"part": "snippet,replies", "videoId": video_id,
                  "maxResults": 100, "order": "time", "textFormat": "plainText"}
        if token:
            params["pageToken"] = token
        data = api_get("commentThreads", params)
        if data.get("_disabled"):
            return []
        for th in data.get("items", []):
            top = th["snippet"]["topLevelComment"]
            sn = top["snippet"]
            out.append({
                "id": top["id"],
                "author": sn.get("authorDisplayName", "?"),
                "text": " ".join((sn.get("textOriginal") or "").split()),
                "date": (sn.get("publishedAt") or "")[:10],
                "likes": sn.get("likeCount", 0),
                "replies": [
                    {
                        "author": r["snippet"].get("authorDisplayName", "?"),
                        "text": " ".join((r["snippet"].get("textOriginal") or "").split()),
                        "date": (r["snippet"].get("publishedAt") or "")[:10],
                    }
                    for r in (th.get("replies", {}).get("comments") or [])
                ],
            })
        token = data.get("nextPageToken")
        pages += 1
        if not token:
            break
    return out


def looks_like_question(text: str) -> bool:
    t = text.strip().lower()
    if len(t) < MIN_QUESTION_LEN:
        return False
    if "?" in t:
        return True
    return any(t.startswith(w + " ") for w in QUESTION_WORDS)


def _norm_author(name: str) -> str:
    """Comment authors are '@Handle'; the channels.list title has no '@'.

    Whitespace is stripped before the '@', not after: stripping in the other
    order leaves the '@' in place for a name with leading space, which is
    exactly the kind of case that only shows up once and is a pain to trace.
    """
    return name.strip().lstrip("@").strip().lower()


def answered_by_channel(c: dict, channel_name: str) -> bool:
    target = _norm_author(channel_name)
    return any(_norm_author(r["author"]) == target for r in c["replies"])


def needs_your_answer(c: dict, channel_name: str) -> bool:
    """A question that is actually waiting on you.

    Two things disqualify a comment: it already got a reply from the channel,
    or the channel wrote the top-level comment itself. That second case is
    common (pinned or engagement comments from you) and without this check
    every one of your own comments would show up as an unanswered customer
    question, which is nonsense.
    """
    if _norm_author(c["author"]) == _norm_author(channel_name):
        return False
    return looks_like_question(c["text"]) and not answered_by_channel(c, channel_name)


def safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "-", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    # Windows silently drops a trailing space or dot when a directory is
    # created, so the string Python holds and the name actually on disk
    # diverge and every later write misses. Truncating can land the cut
    # right after a space, so strip again post-slice, not just before it.
    return s[:70].strip(" .")


def existing_folders() -> dict[str, Path]:
    """Map video_id -> folder, so a renamed video keeps its folder."""
    found = {}
    root = VAULT / "YouTube" / "Videos"
    if not root.is_dir():
        return found
    for note in root.glob("*/00 - Overview.md"):
        m = re.search(r"^video_id:\s*(\S+)", note.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            found[m.group(1)] = note.parent
    return found


def read_frontmatter(path: Path) -> dict:
    if not path.is_file():
        return {}
    m = re.match(r"^---\n(.*?)\n---", path.read_text(encoding="utf-8", errors="replace"), re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^([a-z_]+):\s*(.*)$", line.strip())
        if kv:
            out[kv.group(1)] = kv.group(2).strip()
    return out


def write_overview(folder: Path, v: dict, stats: dict, dry: bool) -> None:
    path = folder / "00 - Overview.md"
    head = "\n".join([
        "---",
        f"video: {folder.name}",
        f"video_id: {v['id']}",
        f"url: https://www.youtube.com/watch?v={v['id']}",
        f"published: {v['published']}",
        f"views: {stats.get('viewCount', '')}",
        f"comment_count: {stats.get('commentCount', '0')}",
        "facet: overview",
        "access: public",
        "system:",
        "---",
    ])
    if path.is_file():
        # Refresh the stats block only; whatever you wrote below it survives.
        text = path.read_text(encoding="utf-8", errors="replace")
        body = re.sub(r"^---\n.*?\n---", "", text, count=1, flags=re.S)
        # Keep the system: value you may have filled in.
        old = read_frontmatter(path).get("system", "")
        if old:
            head = head.replace("system:", f"system: {old}")
        new = head + body
    else:
        new = head + f"""

# {v['title']}

## What it covers

## Which system it teaches

<!-- Fill in `system:` above with the folder slug under Systems/ and link it here. -->

## Notes
"""
    if not dry:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")


def write_description(folder: Path, v: dict, dry: bool) -> None:
    path = folder / "01 - Description.md"
    if path.is_file():
        body = re.sub(r"^---\n.*?\n---", "", path.read_text(encoding="utf-8", errors="replace"),
                      count=1, flags=re.S)
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        if len(re.sub(r"^#.*$", "", body, flags=re.M).strip()) > 40:
            return  # you already wrote or pasted something here
    text = (f"---\nvideo: {folder.name}\nfacet: description\naccess: public\n---\n\n"
            f"# Published description\n\n{v['description'].strip()}\n")
    if not dry:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def write_comments(folder: Path, v: dict, comments: list[dict], channel_name: str,
                   dry: bool) -> None:
    """Fully generated: this file mirrors YouTube, so it is safe to overwrite."""
    questions = [c for c in comments
                if _norm_author(c["author"]) != _norm_author(channel_name)
                and looks_like_question(c["text"])]
    unanswered = [c for c in questions if not answered_by_channel(c, channel_name)]

    lines = [
        "---",
        f"video: {folder.name}",
        f"video_id: {v['id']}",
        "facet: comments",
        "access: public",
        f"collected: {datetime.now():%Y-%m-%d %H:%M}",
        f"total: {len(comments)}",
        f"questions: {len(questions)}",
        f"unanswered: {len(unanswered)}",
        "---",
        "",
        "# Comments",
        "",
        "Generated by `collect_youtube.py`. **Do not edit by hand.**",
        "",
        f"{len(comments)} comments · {len(questions)} look like questions · "
        f"**{len(unanswered)} of those never got a reply from the channel**.",
        "",
    ]

    if unanswered:
        lines += ["## Questions with no reply", ""]
        for c in unanswered:
            lines.append(f"- **{c['author']}** ({c['date']}): {c['text']}")
        lines.append("")

    answered = [c for c in questions if c not in unanswered]
    if answered:
        lines += ["## Questions you already answered", "",
                  "*These are ready made answers: paste them into the system's "
                  "`03 - Common issues` note.*", ""]
        for c in answered:
            lines.append(f"- **{c['author']}** ({c['date']}): {c['text']}")
            for r in c["replies"]:
                if _norm_author(r["author"]) == _norm_author(channel_name):
                    lines.append(f"  - **reply:** {r['text']}")
        lines.append("")

    rest = [c for c in comments if c not in questions]
    if rest:
        lines += ["## Everything else", ""]
        for c in rest:
            like = f" · {c['likes']} likes" if c["likes"] else ""
            lines.append(f"- **{c['author']}** ({c['date']}{like}): {c['text']}")
        lines.append("")

    if not dry:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "03 - Comments.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_inbox(rows: list[dict], dry: bool) -> int:
    """Unanswered questions go to their own inbox file.

    A separate file on purpose: the collector must never touch the note you
    write by hand.
    """
    path = VAULT / "Inbox" / "01 - From YouTube.md"
    seen = set()
    if path.is_file():
        seen = set(re.findall(r"^source:\s*(\S+)", path.read_text(encoding="utf-8", errors="replace"), re.M))

    fresh = [r for r in rows if f"yt:{r['id']}" not in seen]
    if not fresh:
        return 0

    blocks = []
    for r in fresh:
        blocks.append(
            f"\n### {r['date']} {r['author']}\n"
            f"channel: youtube\n"
            f"system: {r['system'] or '-'}\n"
            f"status: no-source\n"
            f"subscriber: unknown\n"
            f"source: yt:{r['id']}\n\n"
            f"{r['text'][:400]}\n"
        )

    if not path.is_file():
        header = (
            "---\ntags: [locodev, inbox, youtube, generated]\n---\n\n"
            "# Questions from YouTube\n\n"
            "Collected by `collect_youtube.py` from comments on your own videos that\n"
            "look like questions and never got a reply from the channel.\n\n"
            "Appended only, never rewritten, so your edits survive. Change a\n"
            "`status:` to `answered` once you handle it.\n\n---\n"
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

    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=CHANNEL_ID)
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--max-videos", type=int, default=None)
    ap.add_argument("--force", action="store_true",
                    help="refetch comments even when the count has not changed")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    VAULT = Path(args.vault)

    if not os.getenv("YOUTUBE_API_KEY", "").strip():
        print("ERROR: YOUTUBE_API_KEY is not set.")
        print("Put it in clickup-mcp/.env (the bot's key works: it only needs read access).")
        print("Get one at console.cloud.google.com > APIs > YouTube Data API v3 > Credentials.")
        return 1
    if not VAULT.is_dir():
        print(f"ERROR: vault not found at {VAULT}")
        return 1

    t0 = time.time()
    ch = api_get("channels", {"part": "snippet,contentDetails", "id": args.channel})
    if not ch.get("items"):
        print(f"ERROR: channel not found: {args.channel}")
        return 1
    channel_name = ch["items"][0]["snippet"]["title"]
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"channel: {channel_name}")

    videos = list_videos(uploads, args.max_videos)
    print(f"videos found: {len(videos)}")

    stats = video_stats([v["id"] for v in videos])
    known = existing_folders()

    created = updated = skipped = 0
    inbox_rows: list[dict] = []
    total_comments = total_unanswered = 0

    for v in videos:
        folder = known.get(v["id"])
        if folder is None:
            folder = VAULT / "YouTube" / "Videos" / safe_name(f"{v['published']} {v['title']}")
            created += 1
        st = stats.get(v["id"], {})
        remote_count = int(st.get("commentCount", 0) or 0)
        local_count = int(read_frontmatter(folder / "03 - Comments.md").get("total", -1) or -1)

        write_overview(folder, v, st, args.dry_run)
        write_description(folder, v, args.dry_run)

        if not args.force and remote_count == local_count:
            skipped += 1
            continue

        comments = fetch_comments(v["id"])
        total_comments += len(comments)
        system = read_frontmatter(folder / "00 - Overview.md").get("system", "")
        write_comments(folder, v, comments, channel_name, args.dry_run)
        updated += 1

        for c in comments:
            if needs_your_answer(c, channel_name):
                total_unanswered += 1
                inbox_rows.append({**c, "system": system})

    added = write_inbox(inbox_rows, args.dry_run)

    verb = "would be" if args.dry_run else ""
    print(f"\nfolders {verb} created: {created} · comment files {verb} updated: {updated} "
          f"· unchanged: {skipped}")
    print(f"comments read: {total_comments} · unanswered questions: {total_unanswered}")
    print(f"added to inbox: {added} (new ones only)")
    print(f"quota used: {_quota['units']} units of the 10,000 daily · "
          f"{time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
