"""Put the right creator's name on each transcript.

Whatever wrote these copied its frontmatter from the Mathew Wadstein
import and never changed `source:`, so 2,431 notes across seven channels
credit him for work that is not his. The vault feeds replies published
under LocoDev's name, so left alone this hands one creator's video to
another creator's audience under a third party's byline.

The folder is right and the field is wrong: sampled video ids resolve
through the API to Ryan Laley, Gorka Games, Smart Poly and Ali Elzoheiry,
matching their folders. The channel title is read from the API rather than
guessed from the folder so the credit is spelled the way its owner spells
it.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, r"C:\Users\LocoDevPC\Documents\fabianorepo\clickup-mcp")
import collect_youtube as y

BASE = r"F:\LocoDev Vault\Reference"
VID = re.compile(r"^video_id:\s*(\S+)", re.M)
SRC = re.compile(r"^source:[ \t]*(.*)$", re.M)


def notes_of(folder: str):
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if fn.endswith(".md") and not fn.startswith("00 "):
                yield os.path.join(root, fn)


def real_title(folder: str) -> str:
    """Ask YouTube who owns the first video this folder mentions."""
    for path in notes_of(folder):
        m = VID.search(open(path, encoding="utf-8", errors="replace").read(900))
        if not m:
            continue
        data = y.api_get("videos", {"part": "snippet", "id": m.group(1)})
        items = data.get("items") or []
        if items:
            return items[0]["snippet"]["channelTitle"]
        break
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = fixed = 0
    for chan in sorted(os.listdir(BASE)):
        folder = os.path.join(BASE, chan)
        if not os.path.isdir(folder):
            continue
        title = real_title(folder)
        if not title:
            print(f"{chan}: could not resolve a channel, left alone")
            continue

        touched = 0
        for path in notes_of(folder):
            text = open(path, encoding="utf-8", errors="replace").read()
            m = SRC.search(text)
            if not m:
                continue
            total += 1
            if m.group(1).strip().strip('"') == title:
                continue
            if args.apply:
                open(path, "w", encoding="utf-8").write(
                    SRC.sub(f"source: {title}", text, count=1))
            touched += 1
        fixed += touched
        print(f"{chan:<30} -> {title:<28} {touched} to correct")

    verb = "corrected" if args.apply else "would correct"
    print(f"\n{verb} {fixed} of {total} notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
