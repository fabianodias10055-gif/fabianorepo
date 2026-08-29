"""Vault reorganisation resilience.

Videos moved from YouTube/Videos/<title>/ to YouTube/Videos/<category>/<title>/.
The video resolver must find a folder at any depth, and cached AI drafts must
be invalidated when the folder layout changes so a draft is never replayed
with sources that have since moved.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panel  # noqa: E402
import panel_ui  # noqa: E402


def test_video_title_strips_the_new_naming_suffix():
    assert panel_ui._video_title(
        "Cool Thing - YT Tutorial - 2025-01-01") == "Cool Thing"
    assert panel_ui._video_title(
        "Learn Blueprints #20- Nodes - YT Tutorial - 2025-07-22"
    ) == "Learn Blueprints #20- Nodes"
    assert panel_ui._video_title(
        "Advanced Ledge System - YT Live - 2025-08-26") == "Advanced Ledge System"


def test_video_title_still_strips_the_old_date_prefix():
    assert panel_ui._video_title(
        "2022-12-01 Enemy and Weather Test") == "Enemy and Weather Test"


def test_video_title_leaves_a_nonconforming_name_alone():
    assert panel_ui._video_title("Some Odd Name") == "Some Odd Name"


def test_name_date_finds_the_date_in_either_layout():
    assert panel._name_date("Cool Thing - YT Live - 2025-08-26") == "2025-08-26"
    assert panel._name_date("2022-12-01 Enemy Test") == "2022-12-01"


def _video(root, *parts, video_id="abc123"):
    folder = root.joinpath("YouTube", "Videos", *parts)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "00 - Overview.md").write_text(
        f"---\nvideo_id: {video_id}\n---\n# Overview\n", encoding="utf-8")
    return folder


def test_video_folder_resolves_when_nested_under_a_category(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "VAULT", tmp_path)
    folder = _video(tmp_path, "YT Tutorials", "Cool Weapon Video - 2025-01-01")
    assert panel._video_folder("Cool Weapon Video - 2025-01-01") == folder
    assert panel._video_id_for("Cool Weapon Video - 2025-01-01") == "abc123"


def test_video_folder_still_finds_the_old_flat_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "VAULT", tmp_path)
    folder = _video(tmp_path, "Flat Video - 2024-01-01")
    assert panel._video_folder("Flat Video - 2024-01-01") == folder


def test_video_folder_returns_none_for_an_unknown_video(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "VAULT", tmp_path)
    _video(tmp_path, "YT Shorts", "Real Video")
    assert panel._video_folder("no such video") is None


def test_video_folder_handles_glob_characters_in_the_title(tmp_path, monkeypatch):
    # Real titles carry '#', '[' and ']'; matched by exact name, not a glob.
    monkeypatch.setattr(panel, "VAULT", tmp_path)
    name = "Learn Blueprints #1- Variables [Part 1] - 2025-03-08"
    folder = _video(tmp_path, "YT Course", name)
    assert panel._video_folder(name) == folder


def test_moving_a_folder_changes_the_vault_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "VAULT", tmp_path)
    (tmp_path / "Systems" / "weapon").mkdir(parents=True)
    before = panel._vault_rev()
    # a rename/move changes the layout signature
    (tmp_path / "Systems" / "weapon").rename(tmp_path / "Systems" / "weapon-system")
    after = panel._vault_rev()
    assert before != after
    # an ordinary note edit (no folder change) does not
    (tmp_path / "Systems" / "weapon-system" / "note.md").write_text("x", encoding="utf-8")
    assert panel._vault_rev() == after


def test_cached_draft_invalidated_when_layout_moved(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "VAULT", tmp_path)
    (tmp_path / "Systems" / "weapon").mkdir(parents=True)
    q = {"id": "yt:1", "text": "how do I attach the gun?",
         "channel": "youtube", "date": "2026-08-28"}
    fresh = {"answer": "a", "qhash": panel._qhash(q), "rev": panel._vault_rev()}
    monkeypatch.setattr(panel, "load_ai_cache",
                        lambda: {panel._cache_key(q, "draft"): fresh})
    assert panel.cached_ai_result(q, "draft") is not None      # same layout: served
    (tmp_path / "Systems" / "weapon").rename(tmp_path / "Systems" / "gun")
    assert panel.cached_ai_result(q, "draft") is None          # moved: invalidated


def test_pre_reorg_entries_without_a_rev_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "VAULT", tmp_path)
    (tmp_path / "Systems").mkdir(parents=True)
    q = {"id": "yt:2", "text": "does it work in 5.4?",
         "channel": "youtube", "date": "2026-08-28"}
    old = {"answer": "a", "qhash": panel._qhash(q)}   # no 'rev' field
    monkeypatch.setattr(panel, "load_ai_cache",
                        lambda: {panel._cache_key(q, "draft"): old})
    assert panel.cached_ai_result(q, "draft") is None
    assert panel.valid_ai_cache([q]) == {}
