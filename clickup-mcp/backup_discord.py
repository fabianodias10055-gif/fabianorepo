#!/usr/bin/env python3
"""Archive every readable Discord channel into the vault as markdown.

collect_discord.py takes only what looks like a question. This takes the
whole conversation, because the answers live in the exchange around a
question as much as in the question itself, and Discord's own history is
not a backup: it lives on their servers and is one deleted channel away
from gone.

Split, not one giant file: a text channel becomes one file per month, a
forum becomes one file per post. Both stay small enough to open in Obsidian
and to hand to a model without swamping it.

Incremental: each channel remembers the last message archived, so later
runs append only what is new. A month already written is rewritten in full
when it gains messages, which keeps a month's file coherent.

Usage:
    python backup_discord.py --dry-run
    python backup_discord.py
    python backup_discord.py --exclude backup,moderator-only
    python backup_discord.py --full          re-archive everything
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib import error, request

from collect_discord import (api_get, author_handle, channel_info,
                             fetch_messages, forum_threads, FORUM_TYPES)
from secrets_store import get_secret

VAULT = Path(r"F:\LocoDev Vault")
BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / ".discord_backup_state.json"

READABLE = (0, 5, 15, 16)     # text, announcement, forum, media
ROOT_NAME = "Discord"
# The backup channel is an archive of an archive; the user asked to skip it.
DEFAULT_EXCLUDE = "backup"


IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
_media_budget = {"bytes": 0, "files": 0, "skipped": 0}


def download_media(att: dict, folder: Path, msg_id: str, want: set,
                   max_mb: int, dry: bool) -> str | None:
    """Save one attachment next to the note and return its relative path.

    Downloading, not linking: Discord signs attachment URLs with an expiry
    of about a day, so a stored link is dead by tomorrow and the archive
    would be text with holes where the screenshots used to be.
    """
    name = att.get("filename") or "file"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in want:
        return None
    size = int(att.get("size") or 0)
    if size > max_mb * 1024 * 1024:
        _media_budget["skipped"] += 1
        return None

    target = folder / "media" / f"{msg_id}-{safe_name(name)}"
    if target.is_file() and target.stat().st_size > 0:
        return f"media/{target.name}"
    if dry:
        _media_budget["files"] += 1
        _media_budget["bytes"] += size
        return f"media/{target.name}"

    url = att.get("url") or att.get("proxy_url")
    if not url:
        return None
    try:
        req = request.Request(url, headers={"User-Agent": "LocoDevPanel/1.0"})
        with request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception:  # noqa: BLE001 - a dead attachment must not end the run
        _media_budget["skipped"] += 1
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    _media_budget["files"] += 1
    _media_budget["bytes"] += len(data)
    return f"media/{target.name}"


def safe_name(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|]", "-", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    # Truncate first, then strip again: Windows silently drops a trailing
    # space when creating a directory, and the path Python holds then stops
    # matching the one on disk.
    return (s[:60].strip(" .") or "channel")


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


def render(messages: list[dict], guild: str, channel_id: str,
           media: dict | None = None) -> str:
    """Messages oldest first, grouped under a heading per day."""
    lines = []
    day = None
    for m in messages:
        ts = m.get("timestamp") or ""
        d, t = ts[:10], ts[11:16]
        if d != day:
            day = d
            lines += ["", f"## {d}", ""]
        author = (m.get("author") or {})
        name = author_handle(author)
        if author.get("bot"):
            name += " [bot]"

        text = (m.get("content") or "").strip()
        parts = []
        ref = m.get("message_reference") or {}
        if ref.get("message_id"):
            parts.append("↪ reply")
        embeds_local = []
        for a in m.get("attachments") or []:
            saved = (media or {}).get(str(a.get("id", "")))
            if saved:
                embeds_local.append(f"![[{saved}]]")
            else:
                parts.append(f"[attachment: {a.get('filename', 'file')}]")
        for e in m.get("embeds") or []:
            title = e.get("title") or e.get("url") or "embed"
            parts.append(f"[embed: {title}]")
        if not text and not parts:
            continue

        prefix = (" ".join(parts) + " ") if parts else ""
        body = " ".join(text.split()) if text else ""
        url = f"https://discord.com/channels/{guild}/{channel_id}/{m['id']}"
        lines.append(f"- **{t}** **{name}**: {prefix}{body}  [·]({url})")
        for e in embeds_local:
            lines.append(f"  {e}")
    return "\n".join(lines).strip() + "\n"


def write_note(path: Path, header: dict, body: str, dry: bool) -> bool:
    front = ["---"]
    for k, v in header.items():
        front.append(f"{k}: {v}")
    front += ["---", ""]
    content = "\n".join(front) + body
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == content:
        return False
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def collect_media(messages: list[dict], folder: Path, want: set,
                  max_mb: int, dry: bool) -> dict:
    saved: dict[str, str] = {}
    if not want:
        return saved
    for m in messages:
        for a in m.get("attachments") or []:
            path = download_media(a, folder, m["id"], want, max_mb, dry)
            if path:
                saved[str(a.get("id", ""))] = path
    return saved


def backup_text_channel(cid: str, name: str, folder: Path, guild: str,
                        after: str | None, cap: int, dry: bool,
                        want: set | None = None,
                        max_mb: int = 12) -> tuple[int, int, str | None]:
    messages = fetch_messages(cid, after, cap)
    if not messages:
        return 0, 0, None
    messages.sort(key=lambda m: int(m["id"]))
    media = collect_media(messages, folder, want or set(), max_mb, dry)

    by_month: dict[str, list[dict]] = {}
    for m in messages:
        by_month.setdefault((m.get("timestamp") or "")[:7] or "unknown", []).append(m)

    written = 0
    for month, batch in sorted(by_month.items()):
        path = folder / f"{month}.md"
        # A month that already exists is re-read and merged, so appending
        # never leaves a half month behind.
        existing_ids = set()
        if path.is_file() and after:
            existing_ids = set(re.findall(r"/(\d{17,20})\)", path.read_text(
                encoding="utf-8", errors="replace")))
        merged = batch
        if existing_ids:
            old_body = path.read_text(encoding="utf-8", errors="replace")
            body = old_body.split("---", 2)[-1].strip()
            new_only = [m for m in batch if m["id"] not in existing_ids]
            if not new_only:
                continue
            body = body + "\n" + render(new_only, guild, cid, media)
            if write_note(path, {"channel": f"#{name}", "channel_id": cid,
                                 "month": month, "source": "backup_discord.py"},
                          body, dry):
                written += 1
            continue
        if write_note(path, {"channel": f"#{name}", "channel_id": cid,
                             "month": month, "messages": len(merged),
                             "source": "backup_discord.py"},
                      render(merged, guild, cid, media), dry):
            written += 1
    return len(messages), written, str(max(int(m["id"]) for m in messages))


def backup_forum(cid: str, name: str, folder: Path, guild: str,
                 cap: int, dry: bool, want: set | None = None,
                 max_mb: int = 12) -> tuple[int, int]:
    posts = forum_threads(cid, guild)
    total = written = 0
    for t in posts:
        msgs = fetch_messages(t["id"], None, cap)
        if not msgs:
            continue
        msgs.sort(key=lambda m: int(m["id"]))
        total += len(msgs)
        media = collect_media(msgs, folder, want or set(), max_mb, dry)
        opened = (msgs[0].get("timestamp") or "")[:10]
        path = folder / f"{opened} {safe_name(t.get('name', t['id']))}.md"
        if write_note(path, {"channel": f"#{name}", "post": t.get("name", ""),
                             "thread_id": t["id"], "opened": opened,
                             "messages": len(msgs), "source": "backup_discord.py"},
                      render(msgs, guild, t["id"], media), dry):
            written += 1
    return total, written


def main() -> int:
    global VAULT

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--exclude", default=DEFAULT_EXCLUDE,
                    help="comma separated channel names to skip")
    ap.add_argument("--only", default="", help="comma separated names to include")
    ap.add_argument("--max-per-channel", type=int, default=50000)
    ap.add_argument("--media", default="images",
                    help="images | none | a comma list of extensions")
    ap.add_argument("--max-media-mb", type=int, default=12)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    VAULT = Path(args.vault)
    guild = os.getenv("DISCORD_GUILD_ID", "").strip()
    if not get_secret("DISCORD_BOT_TOKEN") or not guild:
        print("ERROR: DISCORD_BOT_TOKEN and DISCORD_GUILD_ID must be set in .env")
        return 1
    if not VAULT.is_dir():
        print(f"ERROR: vault not found at {VAULT}")
        return 1

    if args.media == "none":
        want = set()
    elif args.media == "images":
        want = set(IMAGE_EXT)
    else:
        want = {e.strip().lower().lstrip(".") for e in args.media.split(",") if e.strip()}

    skip = {s.strip().lower() for s in args.exclude.split(",") if s.strip()}
    only = {s.strip().lower() for s in args.only.split(",") if s.strip()}

    chans = api_get(f"/guilds/{guild}/channels")
    cats = {c["id"]: c["name"] for c in chans if c["type"] == 4}
    targets = [c for c in chans if c["type"] in READABLE]

    state = {} if args.full else load_state()
    root = VAULT / ROOT_NAME
    total_msgs = total_files = skipped = denied = 0
    t0 = time.time()

    for c in sorted(targets, key=lambda x: (cats.get(x.get("parent_id"), ""),
                                            x.get("position", 0))):
        name = c["name"]
        plain = re.sub(r"[^a-z0-9\- ]", "", name.lower()).strip()
        if any(s in plain for s in skip) or (only and not any(o in plain for o in only)):
            skipped += 1
            continue

        category = safe_name(cats.get(c.get("parent_id"), "Uncategorised"))
        folder = root / category / safe_name(name)
        is_forum = c["type"] in FORUM_TYPES
        # A media pass has to re-read the history: the URLs it needs are
        # only valid at fetch time, and the notes stored none.
        after = (state.get(c["id"], {}).get("last_id")
                 if not args.full and not want else None)

        try:
            if is_forum:
                read, files = backup_forum(c["id"], name, folder, guild,
                                           args.max_per_channel, args.dry_run,
                                           want, args.max_media_mb)
                newest = None
            else:
                read, files, newest = backup_text_channel(
                    c["id"], name, folder, guild, after,
                    args.max_per_channel, args.dry_run, want, args.max_media_mb)
        except error.HTTPError as exc:
            if exc.code == 403:
                denied += 1
                print(f"  {category}/{name}: no access")
            else:
                print(f"  {category}/{name}: HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001 - one channel must not end the run
            print(f"  {category}/{name}: FAILED {type(exc).__name__}")
            continue

        total_msgs += read
        total_files += files
        if read:
            print(f"  {category}/{name}: {read} messages, {files} files")
        if newest and not args.dry_run:
            state[c["id"]] = {"last_id": newest, "name": name}

    if not args.dry_run:
        save_state(state)
        index = [
            "---", "tags: [locodev, discord, backup, generated]", "---", "",
            "# Discord archive", "",
            "Every readable channel, one folder per category. Text channels are "
            "split one file per month; forum posts are one file each. Written by "
            "`backup_discord.py`; re-running appends only what is new.", "",
            f"Last run: {time.strftime('%Y-%m-%d %H:%M')} · "
            f"{total_msgs:,} messages · {total_files} files touched.", "",
        ]
        write_note(root / "00 - Index.md", {}, "\n".join(index[3:]), args.dry_run)

    verb = "would be " if args.dry_run else ""
    mb = _media_budget["bytes"] / 1024 / 1024
    saved_n = _media_budget["files"]
    skipped_n = _media_budget["skipped"]
    print(f"\nmedia {verb}saved: {saved_n:,} files, {mb:,.0f} MB · too large or unreachable: {skipped_n}")
    print(f"messages read: {total_msgs:,} · files {verb}written: {total_files} "
          f"· channels skipped by name: {skipped} · no access: {denied} "
          f"· {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
