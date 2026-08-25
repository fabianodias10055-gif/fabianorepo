"""The bulk send must report exactly what Resend created, never the 2xx.

These lock in the accounting that a prior version got wrong: a batch that
returned zero ids was counted as a full success, so a total failure looked
like a clean send. Every case below drives send_wingman_email with a mocked
Resend so no mail leaves and no key is needed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panel  # noqa: E402


@pytest.fixture
def sender(monkeypatch):
    """A stored RESEND_FROM, an audience of `n`, a silent log, no real sleep."""
    monkeypatch.setattr(panel, "_email_log", lambda *a, **k: True)
    monkeypatch.setattr(panel.time, "sleep", lambda *_: None)
    monkeypatch.setattr(panel, "get_secret",
                        lambda name, default="": "LocoDev <hi@locodev.dev>"
                        if name == "RESEND_FROM" else "key")

    def run(emails, outcome, result):
        monkeypatch.setattr(panel, "_email_audience", lambda seg: (list(emails), ""))
        monkeypatch.setattr(panel, "_resend_request",
                            lambda path, payload, idem="": (outcome, result))
        return panel.send_wingman_email("never_generated", "Subj", "<p>hi</p>",
                                        expect=len(emails))
    return run


def _ids(n):
    return {"data": [{"id": str(i)} for i in range(n)]}


def test_full_success(sender):
    out = sender(["a@x.dev", "b@x.dev"], "ok", _ids(2))
    assert out["ok"] and out["sent"] == 2
    assert out["failed"] == 0 and out["unknown"] == 0


def test_zero_ids_is_not_success(sender):
    # The regression: a 2xx with an empty data list is a total failure.
    out = sender(["a@x.dev", "b@x.dev"], "ok", _ids(0))
    assert out["sent"] == 0
    assert out["failed"] == 2
    assert out["ok"] is False


def test_partial_batch_counts_only_the_ids(sender):
    out = sender(["a@x.dev", "b@x.dev"], "ok", _ids(1))
    assert out["sent"] == 1 and out["failed"] == 1
    assert out["ok"] is False


def test_non_dict_response_is_not_success(sender):
    out = sender(["a@x.dev", "b@x.dev"], "ok", "surprise")
    assert out["sent"] == 0 and out["failed"] == 2
    assert out["ok"] is False


def test_fail_is_counted_failed_not_unknown(sender):
    out = sender(["a@x.dev", "b@x.dev"], "fail", "the Resend key is missing")
    assert out["failed"] == 2 and out["unknown"] == 0
    assert out["ok"] is False


def test_unknown_is_separate_from_failed(sender):
    # A timeout after the request left may have sent; it must not read as a
    # clean failure the operator would re-mail blindly.
    out = sender(["a@x.dev", "b@x.dev"], "unknown", "timed out after sending")
    assert out["unknown"] == 2 and out["failed"] == 0
    assert out["ok"] is False


@pytest.mark.parametrize("body", [
    "<p>plain paragraph</p>",
    "<div>hi <b>there</b></div>",
    "<!-- a balanced comment --><p>ok</p>",
    "<style>.x{color:red}</style><p>styled</p>",
])
def test_validate_accepts_wellformed(body):
    assert panel._validate_email_body(body) == ""


@pytest.mark.parametrize("body", [
    "<!-- oops never closed <p>hi</p>",
    "<style>.x{color:red} <p>the rest is eaten",
    "<title>subject smuggled <p>body",
    "<html><body><p>a whole page</p></body></html>",
    "<p>fine</p><body>",
])
def test_validate_rejects_footer_hiders(body):
    assert panel._validate_email_body(body) != ""


def test_bad_body_blocks_send_before_resend(monkeypatch):
    monkeypatch.setattr(panel, "get_secret",
                        lambda name, default="": "hi@locodev.dev")
    monkeypatch.setattr(panel, "_email_audience",
                        lambda seg: (["a@x.dev"], ""))
    called = {"sent": False}
    monkeypatch.setattr(panel, "_resend_request",
                        lambda *a, **k: called.__setitem__("sent", True) or ("ok", _ids(1)))
    out = panel.send_wingman_email("never_generated", "S",
                                   "<!-- unclosed", expect=1)
    assert out["ok"] is False
    assert called["sent"] is False


def test_reply_to_and_list_unsubscribe_attached(monkeypatch):
    monkeypatch.setattr(panel, "get_secret", lambda name, default="": {
        "RESEND_FROM": "LocoDev <hi@locodev.dev>"}.get(name, ""))
    monkeypatch.setattr(panel, "_email_audience", lambda seg: (["a@x.dev"], ""))
    monkeypatch.setattr(panel, "_email_log", lambda *a, **k: True)
    monkeypatch.setattr(panel.time, "sleep", lambda *_: None)
    captured = {}

    def fake(path, payload, idem=""):
        captured["p"] = payload
        return ("ok", _ids(len(payload)))
    monkeypatch.setattr(panel, "_resend_request", fake)
    panel.send_wingman_email("never_generated", "S", "<p>x</p>", expect=1)
    msg = captured["p"][0]
    assert msg["reply_to"] == "hi@locodev.dev"
    assert msg["headers"]["List-Unsubscribe"] == \
        "<mailto:hi@locodev.dev?subject=unsubscribe>"


def test_reply_to_refuses_header_injection(monkeypatch):
    monkeypatch.setattr(panel, "get_secret", lambda name, default="": {
        "RESEND_REPLY_TO": "evil@x.dev\r\nBcc: victim@x.dev"}.get(name, ""))
    assert panel._reply_address() == ""


def test_stale_count_blocks_send(monkeypatch):
    monkeypatch.setattr(panel, "get_secret",
                        lambda name, default="": "hi@locodev.dev"
                        if name == "RESEND_FROM" else "key")
    monkeypatch.setattr(panel, "_email_audience",
                        lambda seg: (["a@x.dev", "b@x.dev"], ""))
    called = {"sent": False}
    monkeypatch.setattr(panel, "_resend_request",
                        lambda *a, **k: called.__setitem__("sent", True) or ("ok", _ids(2)))
    out = panel.send_wingman_email("never_generated", "S", "<p>x</p>", expect=99)
    assert out["ok"] is False and out.get("code") == "stale"
    assert called["sent"] is False
