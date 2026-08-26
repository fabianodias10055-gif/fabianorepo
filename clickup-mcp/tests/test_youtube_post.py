"""Answering a thread reply must post to the top-level comment, not the reply.

YouTube rejects a reply whose parentId is itself a reply, so post_youtube_reply
targets the part of the id before the dot.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panel  # noqa: E402


class _FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"{}"


def _capture(monkeypatch):
    monkeypatch.setattr(panel, "_youtube_access_token", lambda: ("tok", ""))
    grabbed = {}

    def fake_urlopen(req, timeout=0):
        grabbed["body"] = json.loads(req.data)
        return _FakeResp()
    monkeypatch.setattr(panel.urlrequest, "urlopen", fake_urlopen)
    return grabbed


def test_reply_to_a_reply_posts_to_the_top_level(monkeypatch):
    g = _capture(monkeypatch)
    ok, _ = panel.post_youtube_reply("UgxTOP123.AVreplySUFFIX", "thanks")
    assert ok is True
    assert g["body"]["snippet"]["parentId"] == "UgxTOP123"


def test_top_level_comment_id_is_unchanged(monkeypatch):
    g = _capture(monkeypatch)
    panel.post_youtube_reply("UgxTOP123", "answer")
    assert g["body"]["snippet"]["parentId"] == "UgxTOP123"
