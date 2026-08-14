#!/usr/bin/env python3
"""Export the vault's answers in the shape the Discord bot already reads.

The bot answers from /app/data/knowledge_base.json, a list of question and
answer pairs built one at a time by staff reacting with a check mark. The
vault holds 640 real answers already given on YouTube and Discord, plus
whatever documentation exists, and the bot cannot see any of it.

This writes that knowledge in the bot's exact format so it needs no new
parser: same keys, same list, same file. What it does not do is replace the
bot's own entries. Those were curated by hand and win every conflict; the
export merges into them and reports what it added.

Usage:
    python export_kb.py --dry-run
    python export_kb.py
    python export_kb.py --merge-with downloaded_knowledge_base.json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import panel  # noqa: E402

# Short answers are usually "yes" or a link with no context; they make the
# bot look confident about nothing.
MIN_ANSWER = 40
MIN_QUESTION = 15


def norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def from_vault() -> list[dict]:
    """Every answer the vault can prove was actually given."""
    out: list[dict] = []
    seen: set[str] = set()

    for q in panel.parse_questions():
        answer = (q.get("reply") or "").strip()
        if q["status"] != "answered" or len(answer) < MIN_ANSWER:
            continue
        question = q["text"].strip()
        if len(question) < MIN_QUESTION:
            continue
        key = norm(question)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "question": question,
            "answer": answer,
            "author": "LocoDev",
            "ts": f"{q['date']}T00:00:00",
            # Provenance the bot ignores and a human reading the file needs.
            "source": q.get("code", ""),
            "channel": q.get("channel", ""),
            "system": q.get("system", ""),
        })

    for a in panel.parse_answers():
        answer = (a.get("a") or "").strip()
        question = (a.get("q") or "").strip()
        if len(answer) < MIN_ANSWER or len(question) < MIN_QUESTION:
            continue
        key = norm(question)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "question": question,
            "answer": answer,
            "author": "LocoDev",
            "ts": f"{a['when'][:10]}T00:00:00",
            "source": a.get("code", ""),
            "channel": a.get("channel", ""),
            "system": a.get("system", ""),
        })
    return out


def merge(existing: list[dict], fresh: list[dict]) -> tuple[list[dict], int, int]:
    """The bot's own entries win: a human approved each of those."""
    by_key = {}
    for e in existing:
        k = norm(e.get("question", ""))
        if k:
            by_key[k] = e
    added = 0
    for e in fresh:
        k = norm(e["question"])
        if k in by_key:
            continue
        by_key[k] = e
        added += 1
    return list(by_key.values()), len(existing), added


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(panel.VAULT))
    ap.add_argument("--merge-with", default="",
                    help="the bot's current knowledge_base.json, so its own "
                         "curated entries survive")
    ap.add_argument("--out", default="",
                    help="where to write (default: <vault>/Panel/knowledge_base.json)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    panel.VAULT = Path(args.vault)
    if not panel.VAULT.is_dir():
        print(f"ERROR: vault not found at {panel.VAULT}")
        return 1

    fresh = from_vault()
    print(f"answers the vault can prove were given: {len(fresh)}")

    existing: list[dict] = []
    if args.merge_with:
        p = Path(args.merge_with)
        if not p.is_file():
            print(f"ERROR: {p} not found; refusing to write a file that would "
                  f"replace the bot's own entries")
            return 1
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            print(f"ERROR: {p} is not valid JSON")
            return 1
        if not isinstance(existing, list):
            print(f"ERROR: {p} is not a list of entries")
            return 1

    merged, kept, added = merge(existing, fresh)
    print(f"the bot's own entries kept: {kept}")
    print(f"added from the vault: {added}")
    print(f"total in the file: {len(merged)}")

    out = Path(args.out) if args.out else panel.VAULT / "Panel" / "knowledge_base.json"
    if args.dry_run:
        print(f"\n(simulation: would write {out})")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    size = out.stat().st_size / 1024
    print(f"\nwritten: {out} ({size:,.0f} KB)")
    print(f"stamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    if not args.merge_with:
        print("\nNote: no existing file was merged, so this contains vault answers "
              "only. Download the bot's knowledge_base.json and pass it with "
              "--merge-with before replacing the one it is using, or its "
              "check-mark entries are lost.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
