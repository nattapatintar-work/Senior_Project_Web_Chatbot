"""
tests/test_eval_intent_cases.py
===============================
Pins what /confirm does for each intent label, using the harness in
tools/eval_intent_cases.py (real handler, real extract(), stubbed LLM client).

Several of these describe CURRENT behaviour that may be worth changing (marked
"current behaviour"); if one is changed on purpose, update the test with it.

TWO TESTS CHANGED ON PURPOSE (they used to pin the opposite):
  - a removal at /confirm used to be added to `exclude` (banning every dish with the
    ingredient, unlike the /correct checklist); it now only takes the ingredient out
    of the list -- api/app.py passes ban_excluded=False to apply_text_result().
  - an LLM label=reject that came with add/remove phrases used to become `unclear`
    with nothing applied; it is now treated as confirm+correction when at least one
    phrase resolves to a dictionary key (api/intent.py _parse_response). Rejects whose
    phrases resolve to nothing, and plain rejects, are unchanged.

Run with:
    pytest tests/test_eval_intent_cases.py -v
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from fastapi.testclient import TestClient

import eval_exclude_check as exclude_check
import eval_intent_cases as cases
from api import app as app_module
from api import state


@pytest.fixture
def http():
    with mock.patch.object(app_module, "_load_detector", lambda: None):
        with TestClient(app_module.app) as c:
            yield c
    state.store.clear()
    app_module.limiter.reset()


def test_confirm_correction_applies_add_and_remove_and_asks_again(http):
    snap = cases.run_mocked(http, "x", "confirm+correction", ["หมู"], ["ไก่"])
    assert snap["intent"] == "confirm+correction"
    assert snap["ingredients"] == ["egg", "pork"]
    assert snap["stage"] == "awaiting_confirm"
    assert snap["reject_count"] == 0
    assert snap["llm_calls"] == 1


def test_a_removal_through_confirm_does_not_ban_dishes(http):
    """Changed on purpose (was: the removed key went into `exclude`). Same as the /correct checklist."""
    snap = cases.run_mocked(http, "x", "confirm+correction", [], ["ไข่"])
    assert snap["ingredients"] == ["chicken"]
    assert snap["exclude"] == []


def test_plain_reject_shows_the_checklist_stage_and_counts(http):
    snap = cases.run_mocked(http, "x", "reject", [], [])
    assert snap["intent"] == "reject"
    assert snap["stage"] == "awaiting_correction"
    assert snap["reject_count"] == 1
    assert snap["ingredients"] == cases.START_INGREDIENTS


SENTENCE = "ไม่ใช่ไก่ แต่เป็นหมู"     # "it isn't chicken, it's pork" (Thai test data)


def test_a_confirm_correction_replaces_chicken_with_pork_and_bans_nothing(http):
    snap = cases.run_mocked(http, SENTENCE, "confirm+correction", ["หมู"], ["ไก่"])
    assert snap["intent"] == "confirm+correction"
    assert snap["ingredients"] == ["egg", "pork"]
    assert snap["exclude"] == []
    assert snap["stage"] == "awaiting_confirm"
    assert snap["reject_count"] == 0


def test_b_reject_with_phrases_gives_the_same_result_as_confirm_correction(http):
    """Changed on purpose (was: unclear, nothing applied)."""
    a = cases.run_mocked(http, SENTENCE, "confirm+correction", ["หมู"], ["ไก่"])
    b = cases.run_mocked(http, SENTENCE, "reject", ["หมู"], ["ไก่"])
    for field in ("intent", "ingredients", "exclude", "stage", "reject_count", "corrections"):
        assert b[field] == a[field], field
    assert b["ingredients"] == ["egg", "pork"]
    assert b["reject_count"] == 0                          # a reinterpreted reject is not counted as a reject


def test_c_reject_without_phrases_shows_the_checklist_and_counts(http):
    snap = cases.run_mocked(http, SENTENCE, "reject", [], [])
    assert snap["intent"] == "reject"
    assert snap["stage"] == "awaiting_correction"
    assert snap["reject_count"] == 1
    assert snap["ingredients"] == cases.START_INGREDIENTS


def test_d_an_item_excluded_by_the_first_message_stays_excluded_after_a_removal(http):
    scenario = exclude_check.scenario_b(http)              # first message "no pork", then remove pork at /confirm
    assert scenario["before"]["exclude"] == ["pork"]
    assert scenario["intent"] == "confirm+correction"
    assert scenario["exclude"] == ["pork"]
    assert scenario["ingredients"] == ["egg", "chicken"]


def test_e_a_correction_whose_phrases_resolve_to_nothing_is_unclear(http):
    for label in ("confirm+correction", "reject"):
        snap = cases.run_mocked(http, "x", label, ["มังคุด"], [])       # not in the dictionary
        assert snap["intent"] == "unclear", label
        assert snap["ingredients"] == cases.START_INGREDIENTS
        assert snap["exclude"] == []
        assert snap["stage"] == "awaiting_confirm"
        assert snap["reject_count"] == 0


def test_unclear_changes_nothing_and_has_no_counter(http):
    snap = cases.run_mocked(http, "x", "unclear", [], [])
    assert snap["intent"] == "unclear"
    assert snap["stage"] == "awaiting_confirm"
    assert snap["ingredients"] == cases.START_INGREDIENTS
    assert snap["reject_count"] == 0
    assert snap["corrections"] == {"add": [], "remove": []}


def test_confirm_moves_to_confirmed(http):
    snap = cases.run_mocked(http, "x", "confirm", [], [])
    assert snap["stage"] == "confirmed"


def test_current_behaviour_an_unknown_word_is_silently_dropped_by_a_correction(http):
    snap = cases.run_mocked(http, "x", "confirm+correction", ["มังคุด"], ["ไก่"])
    assert snap["ingredients"] == ["egg"]
    assert snap["corrections"]["add"] == []          # nothing tells the user "มังคุด" was not understood


def test_current_behaviour_the_fallback_discards_the_edit_in_a_rejection_sentence(http):
    snap = cases.run_fallback(http, "ไม่ใช่ไก่ แต่เป็นหมู")
    assert snap["intent"] == "reject"
    assert snap["ingredients"] == cases.START_INGREDIENTS       # neither the removal nor the addition was applied
    assert snap["classifier"]["add"] == [] and snap["classifier"]["remove"] == []


def test_the_fallback_confirms_and_applies_an_add(http):
    assert cases.run_fallback(http, "ใช่ครับ")["stage"] == "confirmed"
    snap = cases.run_fallback(http, "ใช่ แต่เพิ่มหมูด้วย")
    assert snap["intent"] == "confirm+correction"
    assert snap["ingredients"] == ["chicken", "egg", "pork"]


def test_the_whole_table_runs_and_every_stub_was_called_once():
    rows = cases.run_all()      # builds its own TestClient; conftest forbids any real Anthropic client
    assert [r["n"] for r in rows] == list(range(1, 10))
    assert all(r["b_reject_with_phrases"]["llm_calls"] == 1 for r in rows)
