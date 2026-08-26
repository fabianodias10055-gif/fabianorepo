"""Viewer replies (a thank-you, a follow-up question in a thread) become inbox
rows, so praise and questions that live one level down are no longer invisible.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collect_youtube as cy  # noqa: E402


def _comment(replies):
    return {"id": "top", "author": "@viewer",
            "text": "does this work in 5.4?", "replies": replies}


def test_reply_praise_becomes_a_praise_row():
    c = _comment([{"id": "r1", "author": "@ronas1996",
                   "text": "Brother you're a hero, thank you so much for "
                           "answering my question!", "date": "2026-08-25"}])
    rows = cy.reply_rows(c, "sys", "vid1", "folder", "@LocoDev")
    assert len(rows) == 1
    assert rows[0]["praise"] is True and rows[0]["id"] == "r1"


def test_channel_own_reply_is_skipped():
    c = _comment([{"id": "r1", "author": "@LocoDev",
                   "text": "Great question, here is how you do it",
                   "date": "2026-08-25"}])
    assert cy.reply_rows(c, "sys", "vid1", "folder", "@LocoDev") == []


def test_reply_question_is_open_when_channel_never_replied():
    c = _comment([{"id": "r1", "author": "@someone",
                   "text": "how do I make the crosshair centered?",
                   "date": "2026-08-25"}])
    rows = cy.reply_rows(c, "sys", "vid1", "folder", "@LocoDev")
    assert len(rows) == 1
    assert not rows[0].get("praise") and not rows[0].get("answered")


def test_reply_question_is_answered_when_channel_replied_in_thread():
    c = _comment([
        {"id": "r1", "author": "@someone",
         "text": "how do I center the crosshair?", "date": "2026-08-25"},
        {"id": "r2", "author": "@LocoDev",
         "text": "set the Wants to aim variable", "date": "2026-08-25"},
    ])
    rows = cy.reply_rows(c, "sys", "vid1", "folder", "@LocoDev")
    q = [r for r in rows if r["id"] == "r1"][0]
    assert q.get("answered") is True and "Wants to aim" in q["reply"]


def test_reply_without_id_is_ignored():
    c = _comment([{"author": "@nope", "text": "thanks a lot, great work",
                   "date": "2026-08-25"}])   # no id -> cannot make a stable row
    assert cy.reply_rows(c, "sys", "vid1", "folder", "@LocoDev") == []
