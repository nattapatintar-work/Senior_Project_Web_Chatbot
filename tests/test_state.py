"""
tests/test_state.py
====================
Unit tests for api/state.py's SessionState, in particular
apply_text_result()'s health_tags REPLACE semantics (not accumulate) --
see the session-log rationale in that method's docstring.

Run with:
    pytest tests/test_state.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.state import SessionState


def _parsed(ingredients=(), excluded=(), health_tags=()):
    return {"ingredients": list(ingredients), "excluded": list(excluded), "health_tags": list(health_tags)}


def test_a_second_health_tag_replaces_the_first_not_accumulates():
    sess = SessionState(session_id="s1")
    sess.apply_text_result(_parsed(health_tags=["keto"]))
    assert sess.health_tags == ["keto"]

    sess.apply_text_result(_parsed(health_tags=["vegan"]))
    assert sess.health_tags == ["vegan"], "must replace, not accumulate to ['keto', 'vegan']"


def test_a_turn_with_no_health_tag_mention_leaves_the_preference_unchanged():
    sess = SessionState(session_id="s2")
    sess.apply_text_result(_parsed(ingredients=["chicken"], health_tags=["keto"]))
    assert sess.health_tags == ["keto"]

    sess.apply_text_result(_parsed(ingredients=["garlic"]))  # no health tag in this message
    assert sess.health_tags == ["keto"], "a turn that mentions no tag must not clear the existing preference"


def test_the_very_first_message_with_no_health_tag_leaves_it_empty():
    sess = SessionState(session_id="s3")
    sess.apply_text_result(_parsed(ingredients=["chicken"]))
    assert sess.health_tags == []


def test_multiple_tags_in_one_message_replace_together_and_are_deduped():
    sess = SessionState(session_id="s4")
    sess.apply_text_result(_parsed(health_tags=["keto"]))
    sess.apply_text_result(_parsed(health_tags=["clean", "vegan", "clean"]))
    assert sess.health_tags == ["clean", "vegan"]


def test_ingredient_include_exclude_merging_is_unaffected_by_the_health_tag_change():
    sess = SessionState(session_id="s5")
    sess.apply_text_result(_parsed(ingredients=["chicken"], health_tags=["keto"]))
    sess.apply_text_result(_parsed(ingredients=["garlic"], excluded=["pork"], health_tags=["vegan"]))
    assert sess.ingredients == ["chicken", "garlic"]
    assert sess.exclude == ["pork"]
    assert sess.health_tags == ["vegan"]


# ---------------------------------------------------------------------------
# start_new_round() -- resets a finished meal-request cycle, keeps seasonings
# ---------------------------------------------------------------------------

def test_start_new_round_clears_ingredients_exclusions_and_health_tags():
    sess = SessionState(session_id="s6")
    sess.detected["egg"] = 0.9
    sess.apply_text_result(_parsed(ingredients=["shrimp"], excluded=["pork"], health_tags=["clean"]))
    sess.reject_count = 2

    sess.start_new_round()

    assert sess.detected == {}
    assert sess.include == []
    assert sess.exclude == []
    assert sess.health_tags == []
    assert sess.reject_count == 0
    assert sess.ingredients == []


def test_start_new_round_does_not_touch_seasonings():
    sess = SessionState(session_id="s7")
    sess.seasonings = ["fish_sauce", "sugar"]
    sess.apply_text_result(_parsed(ingredients=["chicken"]))

    sess.start_new_round()

    assert sess.seasonings == ["fish_sauce", "sugar"]


# ---------------------------------------------------------------------------
# apply_text_result(ban_excluded=False) -- /confirm's removals fix the list, they do not ban dishes
# ---------------------------------------------------------------------------

def test_a_removal_with_ban_excluded_false_leaves_exclude_untouched():
    sess = SessionState(session_id="s8")
    sess.detected["chicken"] = 0.9
    sess.include.append("egg")

    sess.apply_text_result(_parsed(ingredients=["pork"], excluded=["chicken"]), ban_excluded=False)

    assert sess.ingredients == ["egg", "pork"]
    assert sess.exclude == []


def test_a_removal_with_ban_excluded_false_keeps_an_earlier_first_message_exclusion():
    sess = SessionState(session_id="s9")
    sess.apply_text_result(_parsed(ingredients=["egg"], excluded=["pork"]))          # "no pork" in the first message
    assert sess.exclude == ["pork"]

    sess.apply_text_result(_parsed(excluded=["pork"]), ban_excluded=False)

    assert sess.exclude == ["pork"]


def test_default_still_bans_and_other_fields_are_unaffected_by_the_flag():
    default = SessionState(session_id="s10")
    default.apply_text_result(_parsed(ingredients=["garlic"], excluded=["pork"], health_tags=["keto"]))
    assert default.exclude == ["pork"]

    flagged = SessionState(session_id="s11")
    flagged.apply_text_result(_parsed(ingredients=["garlic"], excluded=["pork"], health_tags=["keto"]), ban_excluded=False)
    assert flagged.ingredients == default.ingredients == ["garlic"]
    assert flagged.health_tags == default.health_tags == ["keto"]
    assert flagged.exclude == []
