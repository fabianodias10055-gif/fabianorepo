"""The page's JavaScript has to parse.

panel_ui.py holds the whole front end as Python strings, so Python compiles
it happily whatever is inside them. Twice in one afternoon a stray quote and
a heredoc's mangled newline went into the page and took every function on it
down with a syntax error: the panel served 5 MB of HTML, no button worked,
and the suite was green through both, because nothing here had ever asked
whether the JavaScript was JavaScript.

Checked against the built page rather than against the source, since the
page is what the browser is handed and the builder does its own stitching
on the way out.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import panel

SCRIPT = re.compile(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", re.S)
BUILT = panel.VAULT / "Panel" / "panel.html"
NODE = shutil.which("node")


def _inline_script() -> str:
    if not BUILT.is_file():
        pytest.skip(f"no built page at {BUILT}; run panel.py first")
    blocks = SCRIPT.findall(BUILT.read_text(encoding="utf-8", errors="replace"))
    assert blocks, "the built page carries no inline script at all"
    return max(blocks, key=len)


@pytest.mark.skipif(NODE is None, reason="node is not on PATH")
def test_the_built_page_script_parses(tmp_path):
    js = tmp_path / "panel.js"
    js.write_text(_inline_script(), encoding="utf-8")
    done = subprocess.run([NODE, "--check", str(js)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:900]


def test_the_functions_the_card_needs_are_defined():
    """A cheap second net for when node is missing.

    A syntax error takes the whole script down, so the names simply stop
    being there. Naming the ones the bulk card cannot work without means a
    break shows up as a missing function rather than as a dead button.
    """
    js = _inline_script()
    for name in ("function bulkRender", "function bulkBusy",
                 "function bulkSendable", "function refsNote",
                 "function askContext"):
        assert name in js, f"{name} is missing from the built page"
