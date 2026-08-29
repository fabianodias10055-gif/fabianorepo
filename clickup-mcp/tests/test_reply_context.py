"""A YouTube reply carries the thread it answers, so a draft for
"Same, did you figure out why?" reads the comment above instead of guessing.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panel  # noqa: E402
import collect_youtube as cy  # noqa: E402


def test_thread_lead_builds_the_lead_up():
    c = {"author": "@a", "text": "gun wont attach", "replies": [
        {"id": "r1", "author": "@b", "text": "set has handgun false"},
        {"id": "r2", "author": "@k", "text": "same, did you figure out why?"}]}
    ctx = cy._thread_lead(c, {"id": "r2"})
    assert ctx.startswith("@a: gun wont attach")
    assert "@b: set has handgun false" in ctx
    assert "same, did you figure out why" not in ctx   # not the reply itself


def test_thread_lead_for_the_first_reply_is_just_the_parent():
    c = {"author": "@a", "text": "topic",
         "replies": [{"id": "r1", "author": "@b", "text": "first reply"}]}
    assert cy._thread_lead(c, {"id": "r1"}) == "@a: topic"


def test_reply_rows_carry_context():
    c = {"id": "top", "author": "@a", "text": "my gun glitches", "replies": [
        {"id": "r1", "author": "@k",
         "text": "how do I center the crosshair?", "date": "2026-08-28"}]}
    rows = cy.reply_rows(c, "sys", "vid", "folder", "@LocoDev")
    assert rows and rows[0]["context"].startswith("@a: my gun glitches")


def test_qhash_includes_context_only_when_present():
    assert panel._qhash({"text": "hi"}) == hashlib.sha1(b"hi").hexdigest()[:12]
    assert panel._qhash({"text": "hi", "context": "x"}) != panel._qhash({"text": "hi"})


def test_ensure_reply_context_fetches_the_parent_for_a_reply(monkeypatch):
    monkeypatch.setattr(panel, "_parent_comment_text", lambda t: "@a: the parent problem")
    q = {"channel": "youtube", "source": "yt:TOP.REPLY", "context": ""}
    panel._ensure_reply_context(q)
    assert q["context"] == "@a: the parent problem"


def test_reply_to_a_reply_is_addressed_to_the_asker():
    q = {"channel": "youtube", "source": "yt:TOP.REPLY", "who": "@wafflewafflewaffle"}
    assert panel._addressed_reply(q, "Hi thanks :)") == "@wafflewafflewaffle Hi thanks :)"


def test_top_level_answer_is_not_prefixed():
    q = {"channel": "youtube", "source": "yt:TOPONLY", "who": "@raun"}
    assert panel._addressed_reply(q, "Hi thanks") == "Hi thanks"


def test_addressed_reply_does_not_double_mention():
    q = {"channel": "youtube", "source": "yt:TOP.REPLY", "who": "@x"}
    assert panel._addressed_reply(q, "@x already here") == "@x already here"


def test_addressed_reply_does_not_double_mention_case_insensitively():
    q = {"channel": "youtube", "source": "yt:TOP.REPLY", "who": "@wafflewafflewaffle"}
    assert panel._addressed_reply(q, "@WaffleWaffleWaffle hi") == "@WaffleWaffleWaffle hi"


def test_addressed_reply_leaves_discord_alone():
    q = {"channel": "discord", "source": "d:1.2", "who": "@x"}
    assert panel._addressed_reply(q, "hi") == "hi"


def test_addressed_reply_skips_a_non_handle_author():
    q = {"channel": "youtube", "source": "yt:TOP.REPLY", "who": "someone"}
    assert panel._addressed_reply(q, "hi") == "hi"


def test_ensure_reply_context_skips_when_present_or_not_a_reply(monkeypatch):
    monkeypatch.setattr(panel, "_parent_comment_text", lambda t: "SHOULD NOT BE USED")
    q1 = {"channel": "youtube", "source": "yt:TOP.REPLY", "context": "already here"}
    panel._ensure_reply_context(q1)
    assert q1["context"] == "already here"
    q2 = {"channel": "youtube", "source": "yt:TOPONLY", "context": ""}   # top-level
    panel._ensure_reply_context(q2)
    assert q2["context"] == ""
    q3 = {"channel": "discord", "source": "d:1.2", "context": ""}
    panel._ensure_reply_context(q3)
    assert q3["context"] == ""
