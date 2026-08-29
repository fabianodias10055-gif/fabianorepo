"""New videos are filed into their category folder, not loose at the top of
YouTube/Videos/, matching how the vault is already sorted."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collect_youtube as cy  # noqa: E402


def test_iso_seconds_parses_youtube_durations():
    assert cy._iso_seconds("PT1M30S") == 90
    assert cy._iso_seconds("PT45S") == 45
    assert cy._iso_seconds("PT2H5M10S") == 7510
    assert cy._iso_seconds("") == 0
    assert cy._iso_seconds("garbage") == 0


def _v(title, desc="", published="2026-08-28"):
    return {"title": title, "description": desc, "published": published}


def test_learn_blueprints_series_goes_to_course():
    cat, tag = cy._video_category(
        _v("Learn Blueprints #21: Interfaces"), {"_live": "no", "_seconds": 800})
    assert (cat, tag) == ("YT Course", "Tutorial")


def test_streamed_video_goes_to_livestreams():
    cat, tag = cy._video_category(
        _v("Advanced Ledge System on UE5 Only Blueprints"),
        {"_live": "yes", "_seconds": 7200})
    assert (cat, tag) == ("YT Livestreams", "Live")


def test_short_by_duration_goes_to_shorts():
    cat, tag = cy._video_category(_v("Helicopter Bug Spin"),
                                  {"_live": "no", "_seconds": 42})
    assert (cat, tag) == ("YT Shorts", "Shorts")


def test_short_by_hashtag_goes_to_shorts_even_without_duration():
    cat, tag = cy._video_category(
        _v("Hang to Swing System #ue5 #shorts"), {"_live": "no", "_seconds": 0})
    assert (cat, tag) == ("YT Shorts", "Shorts")


def test_ordinary_tutorial_is_the_default():
    cat, tag = cy._video_category(
        _v("Advanced Combat Punch System Tutorial on UE5"),
        {"_live": "no", "_seconds": 900})
    assert (cat, tag) == ("YT Tutorials", "Tutorial")


def test_missing_stats_defaults_to_tutorials():
    cat, tag = cy._video_category(_v("Some New Video"), {})
    assert (cat, tag) == ("YT Tutorials", "Tutorial")


def test_folder_name_follows_the_convention():
    name = cy._video_folder_name(_v("8 Directional Movement on UE5"), "Tutorial")
    assert name == "8 Directional Movement on UE5 - YT Tutorial - 2026-08-28"


def test_folder_name_shortens_title_but_keeps_tag_and_date():
    long = "Learn Blueprints #1: Variables, Get & Set, Arrays and Enumerators and more"
    name = cy._video_folder_name(_v(long), "Tutorial")
    assert name.endswith(" - YT Tutorial - 2026-08-28")   # suffix survives
    assert "/" not in name and ":" not in name            # sanitised
    assert len(name.split(" - YT ")[0]) <= 58             # title capped
