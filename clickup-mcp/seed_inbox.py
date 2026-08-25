#!/usr/bin/env python3
"""Create the question inbox note in the vault, with example questions.

The panel reads this file. Today you paste questions here by hand as they come
in; later a collector writes the same format automatically. Either way the
dashboard updates within seconds, because the watcher is already watching it.
"""

import sys
from pathlib import Path

VAULT = Path(r"F:\LocoDev Vault")

CONTENT = """---
tags: [locodev, inbox, questions]
---

# Question inbox

Every question that reaches you, in one place. The panel reads this file and
turns it into the incoming feed, the people list and the gap ranking.

Paste a question the moment it arrives. It costs you fifteen seconds and it is
what makes the priority queue reflect reality instead of a guess.

## Format

One block per question. The header line is `### YYYY-MM-DD Name`, then the
fields, then a blank line, then the question itself.

```
### 2026-08-13 SomeUser
channel: discord
system: ledge-system
status: escalated
subscriber: yes

The actual question, in their words.
```

**channel:** `discord` · `youtube` · `patreon` · `email`
**system:** the folder slug under `Systems/`, or `-` when it is not about one
**status:** `answered` (you or the bot handled it) · `escalated` (needs you) ·
`no-source` (nothing written to answer from) · `out-of-scope`
**subscriber:** `yes` · `no` · `unknown`

A question marked `no-source` is what feeds the gap ranking. That is the whole
point: the questions you cannot answer become the list of what to write next.

---

### 2026-08-13 example_user_1
channel: discord
system: ledge-system
status: escalated
subscriber: yes

The 180 degree leap does not reset the jump, and the arms stay stuck in the
high position until the character moves along the ledge. Also the sphere trace
misses on gamepad.

### 2026-08-13 example_user_2
channel: discord
system: rope
status: no-source
subscriber: unknown

Interested in the Rope Locomotion System. Is it still available after the
account migration?

### 2026-08-13 example_user_3
channel: youtube
system: -
status: no-source
subscriber: no

By subscribing to the premium tier, can I get access to all the content and its
files, and use them in my games? Are the packs compatible with GASP Mover 5.8?

### 2026-08-13 example_user_4
channel: youtube
system: -
status: no-source
subscriber: no

Can these systems be used commercially?

### 2026-08-13 example_user_5
channel: discord
system: obstacle-avoidance
status: no-source
subscriber: yes

How do I install Obstacle Avoidance in a project that already has ALS?

### 2026-08-13 example_user_6
channel: youtube
system: -
status: answered
subscriber: no

What is the difference between regular GASP and GASP Mover?
"""


def main() -> int:
    dest = VAULT / "Inbox"
    dest.mkdir(parents=True, exist_ok=True)
    note = dest / "00 - Questions.md"
    if note.exists():
        print(f"already exists, not overwriting: {note}")
        return 0
    note.write_text(CONTENT, encoding="utf-8")
    print(f"created: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
