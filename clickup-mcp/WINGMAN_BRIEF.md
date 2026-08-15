# Brief: documenting a system from its Unreal project

You have the project files. This vault has the questions customers actually
asked about them, and a Discord bot that answers from whatever is written
here. What is missing is the middle: notes that describe the systems.

Read this before writing anything. Most of it is not style preference, it is
the difference between a note that reaches customers and a note that is
invisible.

## What you are producing

Documentation notes under `F:\LocoDev Vault\Systems\<system>\<Tier>\`, written
from the project you can read, aimed at questions people actually asked.

Two things consume what you write, both automatically:

- **Suggest**, in the operations panel, when the owner answers a question
- **The Discord bot**, which syncs this vault hourly and answers in six
  channels on its own

Neither needs configuration. Write the file in the right place and it is live
within the hour.

## Where the files go

```
Systems/<system-slug>/
  Premium/
    00 - Overview.md
    01 - How it works/
      00 - The idea in one sentence.md
      01 - Step by step.md
      02 - Animations.md
      03 - Using it in your project.md
      04 - Versions.md
      05 - Replication.md
      06 - Input.md
      07 - Design decisions.md
    02 - Setup.md
    03 - Common issues.md
    04 - Blueprints.md
  Standard/
    (same shape, describing the Standard project)
  05 - Answered questions - <Tier>.md   <- GENERATED, never edit
```

`advanced-combat-punch/Premium/` is the worked example. Copy its shape.

**Which tier gets which note.** The same system ships as up to three different
projects, and the same question has a different answer in each: a Premium
customer has the complete project, a Standard customer has fewer files, a
tutorial viewer built it themselves by following a video. Document what is
true of the project you are reading, in that tier's folder. If a fact holds
everywhere, it still goes in each tier's note rather than a shared one:
duplication is cheaper than a customer being told about a file they do not
have.

## Rules that decide whether anyone sees it

1. **A section is found by its heading.** The heading is the searchable
   field, so write it the way a customer would ask: "How to use your own
   animations", not "Animation notes". `## Functions on the bot` is why a
   question about the punch bot's functions finds its table.

2. **Tables are good.** They were invisible until today and are the most
   factual thing in the catalog. Write them as normal markdown; they are
   flattened into lines automatically before reaching Discord, which does not
   draw tables.

3. **A section under ~40 characters of content is dropped.** A heading with
   an empty template body does not exist as far as the search is concerned.

4. **Never edit `05 - Answered questions - *.md`.** They are regenerated from
   the panel on every collect, and hand edits are overwritten.

5. **Keep the frontmatter** that the existing notes carry. `system:` must be
   the slug.

6. **Name real things.** Blueprint names, function names, variable names,
   folder paths, montage names. `MoveBOTTowardsPlayer` is worth more than a
   paragraph of description, because customers search for the name they see
   in the editor.

7. **Never invent.** If the project does not show it, leave it out. The bot
   presents this as its own knowledge and a wrong file path becomes a wrong
   answer given to a paying customer.

## What to put in each note

The sections were chosen from 454 real questions. The percentage is that
theme's share of everything ever asked.

| Note | Share of questions | What it must answer |
|---|---|---|
| `02 - Animations.md` | **31.5%** | which montages and anim assets, where they live, how to swap in your own, retarget steps, root motion settings, naming the system expects |
| `03 - Using it in your project.md` | **19.2%** | merging into GASP, ALS, Motion Matching or an existing project: what to copy, what conflicts, in what order |
| `03 - Common issues.md` | 11.7% | the failures people actually hit, with the fix |
| `04 - Versions.md` | 8.4% | which engine versions, what changed between them, what breaks |
| `05 - Replication.md` | 4.2% | what is replicated, what is not, what it costs to add |
| `06 - Input.md` | 3.5% | actions, mappings, gamepad |
| `01 - Step by step.md` | — | the runtime flow, in order. This is what produced the best answers so far |
| `04 - Blueprints.md` | — | inventory: every blueprint, function, component, variable, as tables |
| `07 - Design decisions.md` | — | why it is built this way. Answers the "why not X" questions |

Animations and integration are 59% of everything asked and were absent from
the old template. They are the two that matter most.

## Start here, and why

```bash
python questions_for.py --list
```

```
  88 waiting   weapon-system                   268 chars documented
  25 waiting   advanced-combat-punch         19516 chars documented
  18 waiting   vault-move                      268 chars documented
  15 waiting   root-motion                     268 chars documented
```

**weapon-system**: 88 questions waiting, 268 characters written. It is the
most asked-about system in the catalog and it has nothing. The punch, which
is documented, has 25 waiting. That is the whole argument.

Read the questions before writing, not after:

```bash
python questions_for.py weapon-system
```

It prints every waiting question with the date, the channel and the asker's
tier, grouped by theme. For weapon-system today: 26 about animation and
retarget, 18 about using it in a project, 10 broken, 8 versions, 8
multiplayer, 5 input. Write the note that answers those 26 first.

To see how the owner answered similar things before, in his voice:

```bash
python questions_for.py weapon-system --answered
```

## Answering questions directly

If a question is fully answered by what you found in the project, it can be
answered rather than only documented. Do that in the panel at
`http://127.0.0.1:8765` so the reply is recorded and sent, not by editing the
vault: answers written into the vault by hand are not delivered to anyone and
get overwritten.

Prefer documenting. One good note answers the same question for everyone who
asks it next month.

## Check that it landed

```bash
python export_kb.py --dry-run
```

The section count should rise by roughly what you wrote. Then confirm the
section is findable by its heading:

```bash
python -c "import sys; sys.path.insert(0,'.'); import export_kb as x; print([d['question'] for d in x.from_docs() if 'weapon' in d['question'].lower()][:20])"
```

If a note you wrote is not in that list, it is invisible to both the panel
and the bot. Usual causes: the section body is too short, or the file is
outside `Systems/<slug>/`.

## What is already handled, so you do not rebuild it

- Collecting questions from Discord and YouTube, every 15 minutes
- Tier of each asker, from the Discord roles snapshot
- Generating `05 - Answered questions - <Tier>.md` per system
- Exporting the vault to the bot, every 2 hours, and the bot syncing hourly
- Flattening tables for Discord, and the bot's answer voice

Your job is the middle piece only: read the project, write what is true.
