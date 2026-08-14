#!/usr/bin/env python3
"""Mirror the vault into Google Drive, which syncs it off this machine.

The vault is now the business: 1630 questions, 640 real answers, 139
transcripts, the whole Discord archive with its screenshots. All of it
lived on one drive with no copy anywhere. This mirrors it into the Google
Drive folder already syncing on this machine, so a disk failure stops being
a total loss. No new credentials: Drive Desktop is already signed in.

The guard matters more than the copy. A mirror deletes whatever is missing
from the source, so if F: is ever unplugged or unmounted, a naive run would
faithfully erase the backup to match an empty source. This refuses to run
unless the source looks like the real vault: present, above a floor of
files, and carrying the folders it should.

Usage:
    python backup_vault.py --dry-run
    python backup_vault.py
    python backup_vault.py --dest "G:/My Drive/Other place"
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VAULT = Path(r"F:\LocoDev Vault")
DEST = Path(r"G:\My Drive\LocoDev Vault Backup")
STAMP = "00 - Backup status.md"

# What the vault must look like for a mirror to be safe. These are floors,
# not expectations: they exist to catch "the drive is gone", not to police
# the vault's contents.
MIN_FILES = 200
MUST_HAVE = ("Inbox", "Systems", "YouTube")


def sanity(src: Path) -> tuple[bool, str]:
    if not src.is_dir():
        return False, f"source not found: {src}"
    missing = [d for d in MUST_HAVE if not (src / d).is_dir()]
    if missing:
        return False, f"source is missing {', '.join(missing)}; refusing to mirror"
    n = sum(1 for _ in src.rglob("*") if _.is_file())
    if n < MIN_FILES:
        return False, f"source has only {n} files, below the {MIN_FILES} floor"
    return True, f"{n:,} files"


def mirror(src: Path, dest: Path, dry: bool, media: bool = False) -> tuple[int, str]:
    """robocopy, because it is incremental, restartable and handles the
    long paths and odd characters this vault is full of."""
    args = [
        "robocopy", str(src), str(dest), "/MIR",
        "/R:2", "/W:2",          # two retries, two seconds; never hang on a lock
        "/NFL", "/NDL", "/NP",   # quiet: no per-file or per-directory spam
        "/XD", "Panel",          # generated output, rebuilt in seconds
        "/XF", "*.tmp", "~$*",
    ]
    if not media:
        # The Discord screenshots are 1.1 GB of the vault's 1.11 GB. Leaving
        # them out turns the backup into a few megabytes of text that can run
        # every hour; the images stay on disk and can be re-fetched from
        # Discord by the archiver if that copy is ever lost.
        args += ["/XD", "media"]
    if dry:
        args.append("/L")
    proc = subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    # robocopy: 0-7 are success (8+ means real failures), unlike every
    # other program, so this cannot be a plain returncode check.
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_summary(out: str) -> dict:
    stats = {}
    for line in out.splitlines():
        # robocopy writes "   Files :   3411   3411 ..." with the colon as
        # its own token, and "Bytes" carries a unit: "1.108 g". Splitting on
        # the colon first keeps both shapes readable.
        head, _, rest = line.partition(":")
        key = head.strip().lower()
        if key not in ("files", "bytes", "dirs"):
            continue
        cols = rest.split()
        if key == "bytes" and len(cols) >= 8:
            cols = [f"{cols[0]} {cols[1]}", f"{cols[2]} {cols[3]}",
                    f"{cols[4]} {cols[5]}", "", f"{cols[6]} {cols[7]}"]
        if len(cols) >= 5:
            stats[key] = {"total": cols[0], "copied": cols[1], "skipped": cols[2]}
    return stats


def write_stamp(dest: Path, src: Path, stats: dict, seconds: float, dry: bool) -> None:
    if dry:
        return
    lines = [
        "---", "tags: [locodev, backup, generated]", "---", "",
        "# Vault backup", "",
        f"Mirrored from `{src}` by `backup_vault.py`.", "",
        f"- Last run: **{datetime.now():%Y-%m-%d %H:%M}**",
        f"- Took: {seconds:.0f}s",
    ]
    for k in ("dirs", "files", "bytes"):
        if k in stats:
            s = stats[k]
            lines.append(f"- {k.capitalize()}: {s['total']} total, "
                         f"{s['copied']} copied, {s['skipped']} unchanged")
    lines += [
        "",
        ("The Discord screenshots under `media/` are deliberately left out: "
         "they are 1.1 GB against a few megabytes of text, and the archiver "
         "can fetch them again from Discord. Run with `--media` to include "
         "them."),
        "",
        "This is a mirror, not an archive: anything deleted in the vault is "
        "deleted here on the next run. Google Drive keeps its own 30 day "
        "version history and trash, which is what protects against an "
        "accidental deletion; this file only tells you the copy is current.",
        "",
        "The `Panel/` folder is deliberately not copied. It is generated "
        "output and rebuilds in about a second.",
        "",
    ]
    try:
        (dest / STAMP).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--dest", default=str(DEST))
    ap.add_argument("--media", action="store_true",
                    help="include the downloaded Discord images (adds ~1.1 GB)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src, dest = Path(args.vault), Path(args.dest)
    ok, detail = sanity(src)
    print(f"source: {src}")
    if not ok:
        print(f"REFUSING: {detail}")
        return 1
    print(f"  looks right: {detail}")

    if not dest.parent.exists():
        print(f"REFUSING: {dest.parent} does not exist. Is Google Drive running?")
        return 1
    print(f"destination: {dest}")

    t0 = time.time()
    code, out = mirror(src, dest, args.dry_run, args.media)
    stats = parse_summary(out)
    took = time.time() - t0

    for k in ("dirs", "files", "bytes"):
        if k in stats:
            s = stats[k]
            print(f"  {k}: {s['total']} total · {s['copied']} copied · "
                  f"{s['skipped']} unchanged")

    if code >= 8:
        print(f"\nrobocopy reported failures (exit {code}). Nothing was trusted; "
              f"the previous copy is still in place.")
        print(out[-800:])
        return 1

    write_stamp(dest, src, stats, took, args.dry_run)
    verb = "would take" if args.dry_run else "took"
    print(f"\nmirror complete, {verb} {took:.0f}s. Google Drive uploads it in the "
          f"background; the tray icon shows when it has finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
