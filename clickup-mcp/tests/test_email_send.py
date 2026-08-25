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
                                        expect=len(emails),
                                        confirm=str(len(emails)))
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
    panel.send_wingman_email("never_generated", "S", "<p>x</p>", expect=1, confirm="1")
    msg = captured["p"][0]
    assert msg["reply_to"] == "hi@locodev.dev"
    assert msg["headers"]["List-Unsubscribe"] == \
        "<mailto:hi@locodev.dev?subject=unsubscribe>"


def test_load_suppressions_missing_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "_wingman_private_dir", lambda: tmp_path)
    supp, err = panel._load_suppressions()
    assert supp == set() and err == ""


def test_load_suppressions_reads_and_normalizes(tmp_path, monkeypatch):
    (tmp_path / "email-suppress.txt").write_text(
        "# unsubscribes\nA@X.dev\n\n  b@x.dev  \n", encoding="utf-8")
    monkeypatch.setattr(panel, "_wingman_private_dir", lambda: tmp_path)
    supp, err = panel._load_suppressions()
    assert err == "" and supp == {"a@x.dev", "b@x.dev"}


def test_load_suppressions_malformed_errors_without_leaking(tmp_path, monkeypatch):
    (tmp_path / "email-suppress.txt").write_text(
        "a@x.dev\nnot an address\n", encoding="utf-8")
    monkeypatch.setattr(panel, "_wingman_private_dir", lambda: tmp_path)
    supp, err = panel._load_suppressions()
    assert supp == set() and "line 2" in err and "not an address" not in err


def test_apply_suppressions_filters_and_recounts():
    doc = {"segments": {"never_generated":
                        {"emails": ["a@x.dev", "b@x.dev"], "count": 2}}}
    out = panel._apply_suppressions(doc, {"b@x.dev"})
    seg = out["segments"]["never_generated"]
    assert seg["emails"] == ["a@x.dev"] and seg["count"] == 1


def test_send_refuses_when_suppression_unreadable(monkeypatch):
    monkeypatch.setattr(panel, "get_secret", lambda n, d="": "hi@locodev.dev")
    monkeypatch.setattr(panel, "_load_suppressions",
                        lambda: (set(), "the unsubscribe list has a bad entry on line 3"))
    monkeypatch.setattr(panel, "_email_audience", lambda seg: (["a@x.dev"], ""))
    sent = {"n": 0}
    monkeypatch.setattr(panel, "_resend_request",
                        lambda *a, **k: (sent.__setitem__("n", sent["n"] + 1),
                                         ("ok", _ids(1)))[1])
    out = panel.send_wingman_email("never_generated", "S", "<p>x</p>",
                                   expect=1, confirm="1")
    assert out["ok"] is False and "line 3" in out["error"]
    assert sent["n"] == 0


def test_email_log_masks_addresses_and_flattens(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "_wingman_private_dir", lambda: tmp_path)
    panel._email_log("test", "operator@locodev.dev",
                     "line one\nline two contact me@evil.dev", 1, 0)
    log = (tmp_path / "email-log.md").read_text(encoding="utf-8")
    entry = [x for x in log.splitlines() if x.startswith("- ")][-1]
    assert "operator@locodev.dev" not in entry   # full test address gone
    assert "me@evil.dev" not in entry            # address pasted in subject gone
    assert "@locodev.dev" in entry               # masked, domain kept for triage
    assert "line one line two" in entry          # the newline was flattened


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
    # confirm matches the shown count, but the fresh list is smaller: stale.
    out = panel.send_wingman_email("never_generated", "S", "<p>x</p>",
                                   expect=99, confirm="99")
    assert out["ok"] is False and out.get("code") == "stale"
    assert called["sent"] is False


def test_send_requires_a_matching_confirmation(monkeypatch):
    monkeypatch.setattr(panel, "get_secret", lambda n, d="": "hi@locodev.dev")
    monkeypatch.setattr(panel, "_email_audience",
                        lambda seg: (["a@x.dev", "b@x.dev"], ""))
    monkeypatch.setattr(panel, "_email_log", lambda *a, **k: True)
    monkeypatch.setattr(panel.time, "sleep", lambda *_: None)
    sent = {"n": 0}

    def fake(*a, **k):
        sent["n"] += 1
        return ("ok", _ids(2))
    monkeypatch.setattr(panel, "_resend_request", fake)

    def send(expect, confirm):
        return panel.send_wingman_email("never_generated", "S", "<p>x</p>",
                                        expect=expect, confirm=confirm)

    assert send(2, "").get("code") == "unconfirmed"        # missing
    assert send(2, "3").get("code") == "unconfirmed"       # wrong number
    assert send(2, "02").get("code") == "unconfirmed"      # leading zero, no int-parse
    assert send(-1, "2").get("code") == "stale"            # the expect<0 bypass is closed
    assert sent["n"] == 0                                  # nothing left the door
    ok = send(2, "2")                                      # exact match sends
    assert ok["ok"] is True and ok["sent"] == 2
