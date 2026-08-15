#!/usr/bin/env python3
"""Export the vault's answers in the shape the Discord bot already reads.

The bot answers from /app/data/knowledge_base.json, a list of question and
answer pairs built one at a time by staff reacting with a check mark. The
vault holds 640 real answers already given on YouTube and Discord, plus
whatever documentation exists, and the bot cannot see any of it.

This writes that knowledge in the bot's exact format so it needs no new
parser: same keys, same list, same file. Every entry is marked origin=vault,
which is how the bot keeps the two halves apart: it replaces its vault half
on each sync and never touches the entries staff approved with a check mark,
and only those approved ones are ever posted verbatim.

The copy in the Drive folder is the one the bot reads. It runs on Railway and
cannot see F:\\LocoDev Vault, so Drive is the only route from this PC to it.

Usage:
    python export_kb.py --dry-run
    python export_kb.py                       vault + Drive copies
    python export_kb.py --no-drive            local copy only
    python export_kb.py --merge-with x.json   only to hand-replace the bot's file
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
# A documentation section can run long, and three of them can be injected
# into one prompt.
MAX_DOC = 1400

# The bot runs in the cloud and cannot see F:\LocoDev Vault, so the export
# goes through Drive. Its own folder, not the vault mirror: that one is kept
# with robocopy /MIR, which deletes anything in the destination that is not
# in the source, and this file is not part of the vault tree it copies.
DRIVE_OUT = Path(r"G:\My Drive\LocoDev Bot KB\knowledge_base.json")


def norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def teaches_nothing(question: str, answer: str) -> bool:
    """True when the pair cannot inform an answer to anyone else.

    A reply of "Hello, what are the 3 assets you have bought?" is a real
    thing LocoDev wrote, but as knowledge it is worse than absent: the model
    reads these as examples of how to respond and starts asking the customer
    a question back instead of answering. Same for a question that is only a
    pasted link, which carries no words to match against.
    """
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s]
    if sentences and all(s.rstrip().endswith("?") for s in sentences):
        return True
    if not re.sub(r"https?://\S+", "", question).strip():
        return True
    return False


def from_vault() -> list[dict]:
    """Every answer the vault can prove was actually given."""
    out: list[dict] = []
    seen: set[str] = set()

    for q in panel.parse_questions():
        answer = (q.get("reply") or "").strip()
        if q["status"] != "answered" or len(answer) < MIN_ANSWER:
            continue
        question = q["text"].strip()
        if len(question) < MIN_QUESTION or teaches_nothing(question, answer):
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
            # The bot keys on this: vault entries are refreshed wholesale on
            # every sync and never auto-posted verbatim, unlike the ones
            # staff approved with a check mark.
            "origin": "vault",
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
        if teaches_nothing(question, answer):
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
            "origin": "vault",
            "source": a.get("code", ""),
            "channel": a.get("channel", ""),
            "system": a.get("system", ""),
        })
    return out


def flatten_tables(text: str) -> str:
    """Markdown tables into lines, because Discord does not draw tables.

    A table reaches the reader as raw pipes and dashes, one long broken row
    per line. Asking the model to reformat is unreliable, since it repeats
    the shape it was given; it cannot repeat a table it never saw. The
    header names are kept inline so a cell still says what it is.
    """
    out: list[str] = []
    rows: list[list[str]] = []

    def flush() -> None:
        if not rows:
            return
        header = rows[0]
        for row in rows[1:]:
            if not any(c for c in row):
                continue
            first, rest = row[0], row[1:]
            parts = [f"{header[i + 1]}: {c}" for i, c in enumerate(rest)
                     if c and i + 1 < len(header)]
            out.append(f"- {first}" + (" - " + ", ".join(parts) if parts else ""))
        rows.clear()

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set(s) <= set("|-: "):   # the separator row
                continue
            rows.append(cells)
            continue
        flush()
        out.append(line)
    flush()
    return "\n".join(out)


def from_docs() -> list[dict]:
    """The catalog notes, which are where the facts actually live.

    Exporting only the answered questions left the bot able to recall what
    someone was once told and unable to describe its own systems. Asked
    which functions the punch system's bot has, it said it did not know,
    while "Functions on the bot" sat in the Blueprints note with the four
    names in a table.

    The question field is what the bot searches, so it carries the system
    name and the heading: "advanced combat punch - Functions on the bot"
    matches a question about functions in the punch system on four words.
    """
    out: list[dict] = []
    seen: set[str] = set()
    # One definition of what counts as a section, shared with the panel's
    # sync report. Two copies would let the panel show a note as delivered
    # while the bot never received it.
    for sec in panel.doc_sections():
        path, heading = sec["path"], sec["heading"]
        body = flatten_tables(sec["body"]).strip()
        if len(body) < MIN_ANSWER:
            continue
        slug, tier = sec["slug"], sec["tier"]
        system = slug.replace("-", " ")
        # The tier belongs in the searchable field. The same system ships as
        # three different projects, and "where is the punch montage" has a
        # different answer in each; an answer that does not say which project
        # it describes is worse than no answer for the other two.
        question = f"{system}{' ' + tier if tier else ''} - {heading}"
        key = norm(question)
        if key in seen:
            continue
        seen.add(key)
        # Three of these can land in one prompt, so a long section is cut
        # rather than allowed to crowd out the other two.
        if len(body) > MAX_DOC:
            body = body[:MAX_DOC].rsplit("\n", 1)[0] + "\n(...)"
        out.append({
            "question": question,
            "answer": body,
            "author": "LocoDev",
            "ts": datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "origin": "vault",
            "kind": "doc",
            "tier": tier,
            # The path relative to Systems, because Premium and Standard hold
            # files with the same name and the panel matches on this to say
            # which note reached the bot.
            "source": path.relative_to(panel.VAULT / "Systems").as_posix(),
            "system": slug,
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
    ap.add_argument("--drive-out", default=str(DRIVE_OUT),
                    help="the Google Drive folder the bot reads from")
    ap.add_argument("--no-drive", action="store_true",
                    help="write the local copy only")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    panel.VAULT = Path(args.vault)
    if not panel.VAULT.is_dir():
        print(f"ERROR: vault not found at {panel.VAULT}")
        return 1

    answers = from_vault()
    docs = from_docs()
    fresh = answers + docs
    print(f"answers the vault can prove were given: {len(answers)}")
    print(f"documentation sections from the catalog: {len(docs)}")

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
    targets = [out]
    if not args.no_drive:
        targets.append(Path(args.drive_out))

    if args.dry_run:
        for t in targets:
            print(f"\n(simulation: would write {t})")
        return 0

    payload = json.dumps(merged, ensure_ascii=False, indent=1)
    written = 0
    for t in targets:
        # Drive Desktop mounts G: only while it is running. Creating the
        # folder on a drive that is not there would write to a path the bot
        # never sees and report success for a file nobody receives.
        if t.parent.parent.exists() or t.parent.exists():
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(payload, encoding="utf-8")
            print(f"\nwritten: {t} ({t.stat().st_size / 1024:,.0f} KB)")
            written += 1
        else:
            print(f"\nSKIPPED {t}: {t.parent.parent} does not exist. If this is "
                  f"the Drive copy, Google Drive Desktop is not running, and "
                  f"the bot will keep serving the last version it fetched.")

    print(f"stamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print("\nEvery entry is marked origin=vault. The bot replaces its vault "
          "half on each sync and leaves the check-mark entries alone, so this "
          "file is meant to hold vault answers only.")
    if args.merge_with:
        print("Merged with an existing file, which is what you want only when "
              "you are replacing /app/data/knowledge_base.json by hand. For "
              "the Drive path, export without --merge-with.")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
