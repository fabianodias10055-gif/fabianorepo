#!/usr/bin/env python3
"""Tag each video folder with the system it teaches, by matching the title.

Fills `system:` in YouTube/Videos/*/00 - Overview.md when the video title
confidently names a catalog system, then rewrites the matching questions'
`system:` lines in Inbox/01 - From YouTube.md in place (preserving any status
edits, unlike a collector re-run).

Only confident matches are written: a title that names two systems, or none,
is left for you to tag by hand. Wrong automatic tags would silently misroute
questions, which is worse than an empty field the panel already reports.

Usage:
    python tag_videos.py --dry-run
    python tag_videos.py
"""

import argparse
import re
import sys
from pathlib import Path

VAULT = Path(r"F:\LocoDev Vault")

# slug -> phrases that must appear in the title (lowercase). Longer, specific
# phrases only: "swim" alone would tag an unrelated devlog that mentions it.
TITLE_PATTERNS = {
    "rope": ("rope locomotion", "rope system", "rope swing"),
    "ledge-system": ("ledge system", "advanced ledge"),
    "directional-ledge": ("directional ledge",),
    "obstacle-avoidance": ("obstacle avoidance",),
    "crawl-locomotion": ("crawl locomotion", "crawl system"),
    "grapple-hook": ("grapple hook", "grappling hook"),
    "hang-and-swing": ("hang and swing",),
    "ladder": ("ladder system", "ladder climb"),
    "motion-matching": ("motion matching",),
    "narrow-passage": ("narrow passage",),
    "roll-dash": ("roll dash",),
    "root-motion": ("root motion",),
    "simple-gliding": ("gliding system", "simple gliding"),
    "skateboard": ("skateboard",),
    "spider-man": ("spider-man", "spider man", "spiderman"),
    "swim": ("swim system", "swimming system"),
    "vault-move": ("vault system", "vaulting"),
    "wall-run": ("wall run", "wallrun"),
    "ziplining": ("zipline", "ziplining"),
    "climb": ("climb system", "climbing system", "free climb"),
    "flight": ("flight system", "flying system"),
    "advanced-combat-punch": ("combat punch", "punch combat"),
    "bow-and-arrow": ("bow and arrow", "bow system"),
    "pistol": ("pistol system",),
    "sword-combo": ("sword combo", "sword combat"),
    "weapon-system": ("weapon system",),
    "hostage": ("hostage",),
    "sneak-cover": ("sneak cover",),
    "stealth": ("stealth system",),
    "telekinesis": ("telekinesis",),
}


def _flat(text: str) -> str:
    """Lowercase, and punctuation reduced to single spaces.

    "Sneak - Cover System Tutorial" is a sneak cover video, and a hyphen
    was enough to hide that from a plain substring test.
    """
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def match_title(title: str) -> str | None:
    """The system a title names, or None when it genuinely says two.

    Longest phrase wins rather than refusing whenever two match. "Directional
    Ledge Climbing System" contains both "directional ledge" and "climbing
    system", and it is plainly a directional ledge video: the more specific
    phrase is the one the title is about. A refusal is kept only for a real
    tie, where the title names two systems just as strongly and a guess
    would misroute every question under it.
    """
    low = _flat(title)
    hits = []
    for slug, phrases in TITLE_PATTERNS.items():
        best = None
        for p in phrases:
            at = low.find(_flat(p).strip())
            if at >= 0 and (best is None or at < best[0]):
                best = (at, -len(p))
        if best:
            hits.append((best[0], best[1], slug))
    if not hits:
        return None
    # Earliest wins, because a title leads with its subject: "Ladder
    # Climbing System" is about ladders, and picking the longer phrase
    # instead filed it under climbing. Length only breaks a tie at the
    # same position.
    hits.sort()
    if len(hits) > 1 and hits[0][:2] == hits[1][:2]:
        return None
    return hits[0][2]


def tag_overviews(dry: bool) -> dict[str, str]:
    """Fill empty system: fields; return video_id -> slug for every tagged
    video (including ones already tagged by hand, so the inbox pass sees all).
    """
    mapping: dict[str, str] = {}
    tagged = skipped = ambiguous = 0
    root = VAULT / "YouTube" / "Videos"
    for note in sorted(root.glob("*/00 - Overview.md")):
        text = note.read_text(encoding="utf-8", errors="replace")
        vid = re.search(r"^video_id:\s*(\S+)", text, re.M)
        if not vid:
            continue
        # [ \t]* and not \s*: \s crosses the newline even with re.M, which
        # made this match 'system:\n---' and read the frontmatter fence as
        # the value. Every video then looked already-tagged.
        current = re.search(r"^system:[ \t]*(\S+)?[ \t]*$", text, re.M)
        existing = (current.group(1) or "").strip() if current else ""

        if existing and existing != "-":
            mapping[vid.group(1)] = existing  # hand-tagged wins, never touch
            skipped += 1
            continue

        slug = match_title(note.parent.name)
        if not slug:
            ambiguous += 1
            continue

        mapping[vid.group(1)] = slug
        tagged += 1
        if not dry:
            new = re.sub(r"^system:[ \t]*$", f"system: {slug}", text,
                         count=1, flags=re.M)
            if new != text:
                note.write_text(new, encoding="utf-8")

    print(f"overviews tagged: {tagged} · already tagged (kept): {skipped} "
          f"· no confident match: {ambiguous}")
    return mapping


def retag_inbox(mapping: dict[str, str], dry: bool) -> int:
    """Rewrite `system: -` lines in the generated YouTube inbox, in place.

    In place rather than re-collecting: a collector re-run would rebuild the
    file and lose any status edits made from the panel or by hand.
    """
    path = VAULT / "Inbox" / "01 - From YouTube.md"
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")

    changed = 0

    def fix_block(block: str) -> str:
        nonlocal changed
        vid = re.search(r"^video_id:\s*(\S+)", block, re.M)
        if not vid:
            return block
        slug = mapping.get(vid.group(1))
        if not slug:
            return block
        new, n = re.subn(r"^system:[ \t]*-*[ \t]*$", f"system: {slug}", block,
                         count=1, flags=re.M)
        changed += n
        return new

    parts = re.split(r"(?m)(?=^###\s)", text)
    rebuilt = parts[0] + "".join(fix_block(b) for b in parts[1:])

    if not dry and changed:
        path.write_text(rebuilt, encoding="utf-8")
    print(f"inbox questions retagged: {changed}")
    return changed


def main() -> int:
    global VAULT

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    VAULT = Path(args.vault)
    if not (VAULT / "YouTube" / "Videos").is_dir():
        print(f"ERROR: no video folders under {VAULT}")
        return 1

    mapping = tag_overviews(args.dry_run)
    retag_inbox(mapping, args.dry_run)
    if args.dry_run:
        print("(dry run: nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
