"""Every field a collector writes must be a field the panel knows.

A name missing from QUESTION_FIELDS does not just go unread. _FIELD_LINE
stops matching that line, so it falls through into the prose and becomes
part of the question text: four questions were displayed, and drafted
against, as "context: @someone: ...".
"""
import re
from pathlib import Path

import panel

SRC = Path(__file__).resolve().parent.parent
# The collectors build their inbox blocks as f-strings, one field per line.
# Matched anywhere rather than at the start of a line: the context line is
# built as `ctx_line = f"context: {...}"`, and anchoring this to the margin
# was how the first version of this guard passed while the bug was live.
WRITTEN = re.compile(r'f"(\w+): ')


def _fields_written_by(module: str) -> set:
    text = (SRC / module).read_text(encoding="utf-8", errors="replace")
    return {m.group(1) for m in WRITTEN.finditer(text)}


def test_no_collector_writes_a_field_the_panel_drops():
    known = set(panel.QUESTION_FIELDS)
    for module in ("collect_discord.py", "collect_youtube.py"):
        written = _fields_written_by(module)
        # Only the names that look like inbox fields at all; the regex also
        # catches unrelated f-strings, and an unknown one is only a problem
        # when it lands in a question block.
        suspects = written & {
            "channel", "system", "status", "subscriber", "source", "video",
            "video_id", "video_url", "reply", "url", "thread", "context",
            "asker", "likes", "date", "kind", "praise",
        }
        missing = suspects - known
        assert not missing, f"{module} writes {sorted(missing)}, panel drops it"


def test_a_context_line_stays_a_field_and_not_the_question():
    """The exact shape that broke: one field the parser had never heard of."""
    from panel import _FIELD_LINE
    line = "context: @yogurt: the ragdoll walks from the locomotor"
    m = _FIELD_LINE.match(line)
    assert m, "context: no longer parses as a field, it will pollute the text"
    assert m.group(1) == "context"


def test_every_known_field_parses_as_a_field():
    from panel import _FIELD_LINE
    for name in panel.QUESTION_FIELDS:
        assert _FIELD_LINE.match(f"{name}: something"), name
