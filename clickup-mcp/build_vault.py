#!/usr/bin/env python3
"""Build the LocoDev knowledge vault: one folder per entity, one note per facet.

The folder name becomes the search filter, the file name becomes the section.
You keep writing in Obsidian; a separate script publishes to Drive/Supabase.

Idempotent on purpose: never overwrites an existing file. Re-run it whenever the
catalog grows and it only creates what is missing.

Usage:
    python build_vault.py
    python build_vault.py --dest "F:\\LocoDev Vault"
    python build_vault.py --dry-run
"""

import argparse
import re
import sys
from pathlib import Path


LEGACY_VAULT = Path(r"C:\Users\LocoDevPC\Documents\Vaults")
DEFAULT_DEST = Path(r"F:\LocoDev Vault")

# (slug, display name, category)
CATALOG = [
    ("climb", "Climb", "locomotion"),
    ("crawl-locomotion", "Crawl Locomotion", "locomotion"),
    ("directional-ledge", "Directional Ledge", "locomotion"),
    ("flight", "Flight", "locomotion"),
    ("grapple-hook", "Grapple Hook", "locomotion"),
    ("hang-and-swing", "Hang and Swing", "locomotion"),
    ("ladder", "Ladder", "locomotion"),
    ("ledge-system", "Ledge System", "locomotion"),
    ("motion-matching", "Motion Matching", "locomotion"),
    ("narrow-passage", "Narrow Passage", "locomotion"),
    ("obstacle-avoidance", "Obstacle Avoidance", "locomotion"),
    ("roll-dash", "Roll Dash + Pickup Pistols", "locomotion"),
    ("root-motion", "Root Motion", "locomotion"),
    ("rope", "Rope", "locomotion"),
    ("simple-gliding", "Simple Gliding", "locomotion"),
    ("skateboard", "Skateboard", "locomotion"),
    ("spider-man", "Spider-Man", "locomotion"),
    ("swim", "Swim", "locomotion"),
    ("vault-move", "Vault", "locomotion"),
    ("wall-run", "Wall Run", "locomotion"),
    ("ziplining", "Ziplining", "locomotion"),
    ("advanced-combat-punch", "Advanced Combat Punch", "combat"),
    ("bow-and-arrow", "Bow and Arrow", "combat"),
    ("pistol", "Pistol", "combat"),
    ("sword-combo", "Sword Combo", "combat"),
    ("weapon-system", "Weapon System", "combat"),
    ("hostage", "Hostage", "interaction"),
    ("sneak-cover", "Sneak Cover", "interaction"),
    ("stealth", "Stealth", "interaction"),
    ("telekinesis", "Telekinesis", "interaction"),
]

# Known videos, to seed the YouTube tree.
VIDEOS = [
    ("2024-05-20 Rope Locomotion System", "rope"),
    ("2026-03-22 Obstacle Avoidance System", "obstacle-avoidance"),
]


def fm(fields: dict) -> str:
    """Minimal YAML frontmatter, in the given order."""
    lines = ["---"]
    for k, v in fields.items():
        lines.append(f"{k}: {v}" if v != "" else f"{k}:")
    lines.append("---")
    return "\n".join(lines)


def overview(slug: str, name: str, category: str) -> str:
    return f"""{fm({
        "system": slug, "name": name, "category": category,
        "facet": "overview", "access": "public", "status": "draft",
        "tier": "", "video": "", "patreon": "", "files": "",
    })}

# {name}

## What it does

<!-- One sentence a beginner understands. No jargon. -->

## Who it is for

<!-- What kind of game or project needs this. -->

## Compatibility

<!-- This table answers the question that comes in most often. Fill it in even
     when the answer is "not tested": not knowing is a valid answer, guessing
     is not. -->

| Item | Status | Notes |
|---|---|---|
| Unreal Engine | | |
| GASP + ALS | | |
| GASP Mover | | |
| Other plugins | | |

## Requirements

<!-- What must already be in the project before installing. -->

## Where it lives

- **Video:**
- **Patreon post:**
- **Files:**

## License

<!-- Commercial use allowed? Credit required? Redistribution allowed? -->
"""


def how_it_works(slug: str, name: str) -> str:
    return f"""{fm({
        "system": slug, "facet": "logic", "access": "public", "status": "draft",
    })}

# {name} - How it works

## The idea in one sentence

<!-- If you had one line to explain it, what would you say. -->

## Step by step

1.
2.
3.

## Unreal concepts involved

<!-- e.g. Event Overlap, Physics Constraints, Timeline, Motion Warping.
     This is for people who want to UNDERSTAND, not just copy. -->

## Design decisions

<!-- Why it was built this way and not another. This is what separates your
     content from any other tutorial. -->

![](media/)
"""


def setup(slug: str, name: str) -> str:
    return f"""{fm({
        "system": slug, "facet": "setup", "access": "public", "status": "draft",
    })}

# {name} - Setup

## Before you start

- [ ] Engine version:
- [ ] Required plugins:

## Steps

- [ ] 1.
- [ ] 2.
- [ ] 3.

## How to know it worked

<!-- The concrete test: press X, Y should happen. -->

## Settings that usually need tuning

<!-- Values, collision channels, Object Types, scales. -->

![](media/)
"""


def issues(slug: str, name: str) -> str:
    return f"""{fm({
        "system": slug, "facet": "issues", "access": "public", "status": "draft",
    })}

# {name} - Common issues

<!-- THIS is the note that saves you the most time. Every time someone asks
     something on Discord or YouTube and you answer, paste it here. Next time
     the bot answers on its own. -->

## Symptom:

**Cause:**

**Fix:**

---

## Symptom:

**Cause:**

**Fix:**
"""


def blueprints(slug: str, name: str) -> str:
    return f"""{fm({
        "system": slug, "facet": "blueprints", "access": "public", "status": "draft",
    })}

# {name} - Asset inventory

## Blueprints

| Asset | Type | What it does |
|---|---|---|
| | | |

## Inputs

| Action | Key / button | Handled in |
|---|---|---|
| | | |

## Supporting assets

<!-- Animations, curves, data tables, materials, sounds. -->

## What you can change without breaking it

<!-- Where the system is meant to be customized. -->
"""


FACETS = [
    ("00 - Overview.md", "overview", overview),
    ("01 - How it works.md", "logic", how_it_works),
    ("02 - Setup.md", "setup", setup),
    ("03 - Common issues.md", "issues", issues),
    ("04 - Blueprints.md", "blueprints", blueprints),
]


def video_overview(folder: str, system: str) -> str:
    return f"""{fm({
        "video": folder, "system": system, "facet": "overview",
        "access": "public", "status": "draft", "url": "",
        "published": folder[:10], "views": "",
    })}

# {folder[11:]}

## What it covers

## Which system it teaches

[[../../../Systems/{system}/00 - Overview|{system}]]

## Links mentioned in the video

## Notes

<!-- e.g. matching Patreon post, engine version used in the recording. -->
"""


def video_description(folder: str, system: str) -> str:
    return f"""{fm({"video": folder, "facet": "description", "access": "public"})}

# Published description

<!-- Paste the current YouTube description here. It is a source for the bot and
     a history of when you changed the links. -->
"""


def video_transcript(folder: str, system: str) -> str:
    return f"""{fm({"video": folder, "facet": "transcript", "access": "public"})}

# Transcript

<!-- Generated by: yt-dlp --write-auto-sub --skip-download --sub-lang en,pt <url>
     Format: [mm:ss] text. This is the note that lets the bot cite the exact
     minute of the video instead of you opening it. -->
"""


def video_comments(folder: str, system: str) -> str:
    return f"""{fm({"video": folder, "facet": "comments", "access": "public"})}

# Comments

<!-- Collected through the YouTube Data API. This is the FAQ your audience
     already wrote. A comment you answered is a ready-made answer. -->

| Who | Comment | Your reply |
|---|---|---|
| | | |
"""


VIDEO_FACETS = [
    ("00 - Overview.md", video_overview),
    ("01 - Description.md", video_description),
    ("02 - Transcript.md", video_transcript),
    ("03 - Comments.md", video_comments),
]


def pull_legacy(name: str) -> dict[str, str]:
    """Reuse whatever already exists in the old vault, so you do not rewrite it.

    Today only two systems have a note (Ledge and Rope), with sections
    'O que faz', 'Logica' and 'Conceitos UE5'.
    """
    found: dict[str, str] = {}
    candidates = [
        LEGACY_VAULT / "LocoDev Negocio UE5" / "05-Systems-UE5" / f"{name}.md",
        LEGACY_VAULT / "LocoDev Negocio UE5" / "05-Systems-UE5" / f"{name} System.md",
    ]
    source = next((c for c in candidates if c.is_file()), None)
    if not source:
        return found

    text = source.read_text(encoding="utf-8", errors="replace")
    found["_source"] = str(source)

    m = re.search(r"\*\*O que faz:\*\*\s*\n(.+?)(?=\n\*\*|\n---|\Z)", text, re.S)
    if m:
        found["what"] = m.group(1).strip()
    m = re.search(r"\*\*L[oó]gica:\*\*\s*\n(.+?)(?=\n\*\*|\n---|\Z)", text, re.S)
    if m:
        found["logic"] = m.group(1).strip()
    m = re.search(r"\*\*Conceitos UE5:\*\*\s*\n(.+?)(?=\n\*\*|\n---|\Z)", text, re.S)
    if m:
        found["concepts"] = m.group(1).strip()
    return found


def apply_legacy(content: str, facet: str, data: dict[str, str]) -> str:
    """Drop migrated content into the right slot of the template."""
    if not data:
        return content
    note = f"\n<!-- migrated from {data.get('_source', '')} on 2026-08-13 -->\n"

    if facet == "overview" and "what" in data:
        content = content.replace(
            "## What it does\n\n<!-- One sentence a beginner understands. No jargon. -->",
            f"## What it does\n{note}\n{data['what']}",
        )
    if facet == "logic":
        if "logic" in data:
            content = content.replace(
                "## Step by step\n\n1.\n2.\n3.",
                f"## Step by step\n{note}\n{data['logic']}",
            )
        if "concepts" in data:
            content = content.replace(
                "## Unreal concepts involved\n",
                f"## Unreal concepts involved\n\n{data['concepts']}\n",
            )
    return content


def write(path: Path, content: str, dry: bool, counters: dict) -> None:
    if path.exists():
        counters["skipped"] += 1
        return
    counters["created"] += 1
    if dry:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def systems_index() -> str:
    lines = [
        fm({"tags": "[locodev, systems, index]"}),
        "",
        "# UE5 Systems",
        "",
        "One folder per system, five notes per folder. Always the same anatomy:",
        "",
        "| Note | What it is for |",
        "|---|---|",
        "| `00 - Overview` | what it is, compatibility, where the files are, license |",
        "| `01 - How it works` | the internals, for people who want to understand |",
        "| `02 - Setup` | installation checklist |",
        "| `03 - Common issues` | the technical FAQ, fed by day to day support |",
        "| `04 - Blueprints` | asset inventory, inputs and customization points |",
        "",
        "Images go in `media/` inside the system folder.",
        "",
        "## Where to start",
        "",
        "By demand, not alphabetically. The Panel note ranks this for you, but the",
        "short version is: **Ledge System**, **Obstacle Avoidance** and **Rope**",
        "are asked about constantly and have nothing written.",
        "",
        "Within each system, start with the **Overview**: the compatibility table",
        "alone answers the question that comes in most often.",
        "",
        "## Catalog",
        "",
        "| System | Category | Folder |",
        "|---|---|---|",
    ]
    for slug, name, cat in CATALOG:
        lines.append(f"| {name} | {cat} | [[{slug}/00 - Overview\\|{slug}]] |")
    return "\n".join(lines) + "\n"


def youtube_index() -> str:
    return f"""{fm({"tags": "[locodev, youtube, index]"})}

# Channel videos

One folder per video, four notes per folder:

| Note | What it is for |
|---|---|
| `00 - Overview` | link, date, views, which system it teaches |
| `01 - Description` | the description published on YouTube |
| `02 - Transcript` | the spoken text with timestamps |
| `03 - Comments` | the FAQ your audience wrote |

Folder name: `YYYY-MM-DD Video title`. The leading date keeps chronological
order and works as a stable identifier.

## Filling in the transcript

The Discord bot already has `yt-dlp` wired in. The command that produces it:

```
yt-dlp --write-auto-sub --skip-download --sub-lang en,pt <url>
```

Without a transcript, answering someone means opening the video. With it, the
bot cites the exact minute.
"""


def readme(dest: Path) -> str:
    return f"""{fm({"tags": "[locodev, vault, index]", "created": "2026-08-13"})}

# LocoDev Vault

Knowledge base for the ecosystem. The vault is where you **write**; the cloud
copy is what **answers** clients, subscribers and anyone with a question, so you
do not have to open the Unreal project or scrub through a video to reply.

## Structure

```
{dest.name}/
├── Panel/           generated note + live dashboard
├── Systems/         one folder per UE5 system, 5 notes each
└── YouTube/Videos/  one folder per video, 4 notes each
```

## The rules

1. **The folder is the identifier.** Its name becomes the search filter.
   Renaming it reorganizes the whole base on the next sync.
2. **One note per facet.** Do not merge setup into the logic note: search
   returns the note, and you want it to return the right answer.
3. **Images in `media/`** inside the entity folder, referenced with a relative
   path. They travel with the excerpt in the answer.
4. **Frontmatter is read by machines.** The `system`, `facet` and `access`
   fields become database columns. `access: internal` never leaves through the
   public door.
5. **Never edit the Panel note.** It is generated; run the panel script.

## Scripts

In `fabianorepo/clickup-mcp/`:

- `build_vault.py` creates missing folders and notes (never overwrites)
- `panel.py` regenerates the Panel note and the live dashboard
- `panel.py --watch` watches this vault and updates the dashboard as you type
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dest = Path(args.dest)
    c = {"created": 0, "skipped": 0, "migrated": 0}

    write(dest / "00 - How this vault works.md", readme(dest), args.dry_run, c)
    write(dest / "Systems" / "00 - Index.md", systems_index(), args.dry_run, c)
    write(dest / "YouTube" / "00 - Index.md", youtube_index(), args.dry_run, c)

    for slug, name, category in CATALOG:
        folder = dest / "Systems" / slug
        legacy = pull_legacy(name)
        if legacy:
            c["migrated"] += 1
        for filename, facet, builder in FACETS:
            body = builder(slug, name, category) if facet == "overview" else builder(slug, name)
            body = apply_legacy(body, facet, legacy)
            write(folder / filename, body, args.dry_run, c)
        if not args.dry_run:
            (folder / "media").mkdir(parents=True, exist_ok=True)

    for folder_name, system in VIDEOS:
        folder = dest / "YouTube" / "Videos" / folder_name
        for filename, builder in VIDEO_FACETS:
            write(folder / filename, builder(folder_name, system), args.dry_run, c)
        if not args.dry_run:
            (folder / "media").mkdir(parents=True, exist_ok=True)

    verb = "would be created" if args.dry_run else "created"
    print(f"{c['created']} files {verb}, {c['skipped']} skipped (already existed)")
    print(f"{c['migrated']} systems with content migrated from the legacy vault")
    print(f"destination: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
