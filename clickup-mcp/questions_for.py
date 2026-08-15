#!/usr/bin/env python3
"""The real questions asked about one system, so documentation answers them.

Writing from the code alone produces a note that explains what the author
already knew. These are the words customers used, with who asked and from
which tier, which is what decides whether an answer belongs in Premium,
Standard or the tutorial notes.

Usage:
    python questions_for.py weapon-system
    python questions_for.py weapon-system --answered
    python questions_for.py --list
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import panel  # noqa: E402

THEMES = (
    ("animation and retarget", ("animation", "montage", "retarget", "mixamo",
                                "anim", "skeleton", " ik ", "root motion")),
    ("using it in a project", ("gasp", "als", "motion matching", "integrate",
                               "combine", "my project", "add this", "implement")),
    ("something is broken", ("not work", "doesnt", "does not work", "error",
                             "crash", "bug", "broken", "stuck", "fail", "wrong")),
    ("engine version", ("5.4", "5.5", "5.6", "5.7", "version", "update")),
    ("multiplayer", ("replicat", "multiplayer", "server", "client")),
    ("input", ("input", " key", "button", "mapping", "gamepad")),
    ("access and download", ("download", "patreon", "tier", "access", "link")),
)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("system", nargs="?", default="")
    ap.add_argument("--answered", action="store_true",
                    help="show the ones already answered, with the reply")
    ap.add_argument("--list", action="store_true",
                    help="systems ranked by how many questions are waiting")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    questions = panel.parse_questions()

    if args.list or not args.system:
        open_q = [q for q in questions if q["status"] != "answered"]
        counts = Counter(q.get("system") or "" for q in open_q)
        print(f"{len(open_q)} questions waiting, by system\n")
        for slug, n in counts.most_common(20):
            if not slug:
                continue
            folder = panel.VAULT / "Systems" / slug
            written = sum(
                len(panel.strip_boilerplate(panel.strip_scaffold(
                    p.read_text(encoding="utf-8", errors="replace"))))
                for p in folder.rglob("*.md") if not p.name.startswith("05 -")
            ) if folder.is_dir() else 0
            print(f"  {n:4d} waiting   {slug:28s} {written:6d} chars documented")
        return 0

    wanted = [q for q in questions if q.get("system") == args.system
              and (q["status"] == "answered") == bool(args.answered)]
    if not wanted:
        print(f"nothing for {args.system!r}. --list shows the systems.")
        return 1

    state = "answered" if args.answered else "waiting"
    print(f"{len(wanted)} {state} questions about {args.system}\n")

    print("what they are about:")
    for label, words in sorted(
            THEMES, key=lambda t: -sum(
                1 for q in wanted if any(w in q["text"].lower() for w in t[1]))):
        n = sum(1 for q in wanted if any(w in q["text"].lower() for w in words))
        if n:
            print(f"  {n:4d}  {label}")
    print()

    for q in wanted[:args.limit]:
        tier = panel.member_tier(q.get("who", ""), q.get("channel", ""))
        text = " ".join(q["text"].split())
        print(f"[{q.get('code','')}] {q['date']} · {q['channel']} · {tier}")
        print(f"  Q: {text}")
        if args.answered and q.get("reply"):
            print(f"  A: {' '.join(q['reply'].split())}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
