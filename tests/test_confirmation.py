"""
tests/test_confirmation.py
===========================
Tests for the Week 8 "anything else?" confirmation state in
api/confirmation.py, in isolation from Flask/LINE — same reasoning
test_session.py gives for testing api/session.py standalone: keeping
confirmation.py free of project imports means the tricky part (state that
survives across two separate debounce flushes) is testable in milliseconds,
no LINE account or .env required.

Timeouts are timing-based, so these use a very short window (0.05s) via
confirmation.configure(), the same pattern test_session.py uses for
session.configure(). Real usage is 60s.

Run with:
    pytest tests/test_confirmation.py -v
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api import confirmation

TEST_TIMEOUT = 0.05
WAIT = TEST_TIMEOUT * 4


@pytest.fixture(autouse=True)
def clean_confirmation_state():
    """
    Reset module state before and after every test, and pin the timeout/
    prompt-cap defaults back to their real values afterward so a test that
    calls configure() cannot leak a short timeout into a later test.

    Same reasoning as test_session.py's clean_session_state fixture:
    confirmation.py keeps its state in module-level variables, which persist
    between tests in the same process otherwise.
    """
    confirmation.reset()
    confirmation.configure(timeout_seconds=TEST_TIMEOUT, max_prompts=2)
    yield
    confirmation.reset()
    confirmation.configure(timeout_seconds=60.0, max_prompts=2)


def collect_timeouts() -> list:
    """
    Install a timeout handler that records what timed out instead of pushing
    a real LINE message. Mirrors test_session.py's collect_flushes().
    """
    timed_out = []
    confirmation.set_timeout_handler(timed_out.append)
    return timed_out


# ---------------------------------------------------------------------------
# start() / get()
# ---------------------------------------------------------------------------

def test_start_creates_a_pending_confirmation():
    pending = confirmation.start("U1", ["chicken", "garlic"], ["keto"], ["pork"])

    assert pending.user_id == "U1"
    assert pending.ingredients == ["chicken", "garlic"]
    assert pending.health_tags == ["keto"]
    assert pending.excluded == ["pork"]
    assert pending.prompts_sent == 1
    assert confirmation.get("U1") is pending


def test_get_returns_none_when_nothing_pending():
    assert confirmation.get("nobody_waiting") is None


def test_start_deduplicates_ingredients():
    pending = confirmation.start("U1", ["egg", "egg", "chicken"], [], [])
    assert pending.ingredients == ["egg", "chicken"]


# ---------------------------------------------------------------------------
# is_confirmation_text()
# ---------------------------------------------------------------------------

def test_recognises_the_primary_confirm_phrase():
    assert confirmation.is_confirmation_text(confirmation.PRIMARY_CONFIRM_PHRASE)


def test_recognises_alternate_confirm_phrases():
    assert confirmation.is_confirmation_text("ยืนยัน")
    assert confirmation.is_confirmation_text("พอแล้ว")


def test_strips_whitespace_before_matching():
    assert confirmation.is_confirmation_text(f"  {confirmation.PRIMARY_CONFIRM_PHRASE}  ")


def test_does_not_fire_on_unrelated_text():
    """
    A sentence that merely contains a confirmation word as a coincidence must
    not be misread as confirming -- exact match only, no substring/fuzzy
    matching (mirrors nlp/extract.py's own preference for exact synonyms
    over fuzzy ones wherever a false positive is worse than a false negative).
    """
    assert not confirmation.is_confirmation_text("มีไก่กับกระเทียม")
    assert not confirmation.is_confirmation_text("")


# ---------------------------------------------------------------------------
# merge()
# ---------------------------------------------------------------------------

def test_merge_folds_new_ingredients_into_existing_pending():
    confirmation.start("U1", ["chicken"], ["keto"], [])
    merged = confirmation.merge("U1", ["egg"], [], ["pork"])

    assert merged.ingredients == ["chicken", "egg"]
    assert merged.health_tags == ["keto"]
    assert merged.excluded == ["pork"]


def test_merge_deduplicates():
    confirmation.start("U1", ["chicken", "garlic"], [], [])
    merged = confirmation.merge("U1", ["garlic", "egg"], [], [])
    assert merged.ingredients == ["chicken", "garlic", "egg"]


def test_merge_does_not_change_prompts_sent():
    """
    prompts_sent is bumped only by record_reprompt(), never as a side effect
    of merging data -- the two concerns must not drift out of sync (see
    merge()'s own docstring).
    """
    confirmation.start("U1", ["chicken"], [], [])
    merged = confirmation.merge("U1", ["egg"], [], [])
    assert merged.prompts_sent == 1


def test_merge_returns_none_when_nothing_pending():
    assert confirmation.merge("nobody_waiting", ["egg"], [], []) is None


# ---------------------------------------------------------------------------
# record_reprompt()
# ---------------------------------------------------------------------------

def test_record_reprompt_increments_the_counter():
    confirmation.start("U1", ["chicken"], [], [])
    confirmation.record_reprompt("U1")
    assert confirmation.get("U1").prompts_sent == 2


def test_record_reprompt_returns_none_when_nothing_pending():
    assert confirmation.record_reprompt("nobody_waiting") is None


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------

def test_resolve_pops_and_returns_the_pending_confirmation():
    confirmation.start("U1", ["chicken"], ["keto"], [])
    resolved = confirmation.resolve("U1")

    assert resolved.ingredients == ["chicken"]
    assert confirmation.get("U1") is None
    assert confirmation.active_count() == 0


def test_resolve_returns_none_when_nothing_pending():
    assert confirmation.resolve("nobody_waiting") is None


def test_resolve_cancels_the_pending_timeout():
    """A resolved confirmation must never also fire its timeout later."""
    timed_out = collect_timeouts()

    confirmation.start("U1", ["chicken"], [], [])
    confirmation.resolve("U1")

    time.sleep(WAIT)

    assert timed_out == [], "a resolved confirmation should never time out"


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

def test_timeout_fires_and_hands_the_handler_the_pending_state():
    timed_out = collect_timeouts()

    confirmation.start("U1", ["chicken", "egg"], ["keto"], [])

    assert timed_out == [], "should not fire before the window closes"

    time.sleep(WAIT)

    assert len(timed_out) == 1
    assert timed_out[0].user_id == "U1"
    assert timed_out[0].ingredients == ["chicken", "egg"]


def test_timeout_clears_the_pending_state():
    collect_timeouts()

    confirmation.start("U1", ["chicken"], [], [])
    time.sleep(WAIT)

    assert confirmation.get("U1") is None
    assert confirmation.active_count() == 0


def test_merge_restarts_the_timeout():
    """
    New activity from the user should push the deadline out, same reasoning
    as session.py's debounce timer -- see test_session.py's
    test_each_message_extends_the_window for the equivalent debounce test.
    """
    timed_out = collect_timeouts()

    confirmation.start("U1", ["chicken"], [], [])
    time.sleep(TEST_TIMEOUT * 0.6)
    confirmation.merge("U1", ["egg"], [], [])  # should restart the countdown
    time.sleep(TEST_TIMEOUT * 0.6)

    assert timed_out == [], "merging should have pushed the deadline out"

    time.sleep(WAIT)
    assert len(timed_out) == 1


def test_no_handler_registered_does_not_crash():
    """
    Mirrors session.py's own "no flush handler" safety net -- a timeout
    firing with nothing registered (the normal state in most tests) must not
    raise, just log and move on.
    """
    confirmation.set_timeout_handler(None)
    confirmation.start("U1", ["chicken"], [], [])
    time.sleep(WAIT)  # must not raise
    assert confirmation.get("U1") is None


def test_a_failing_handler_does_not_break_later_confirmations():
    """Same reasoning as test_session.py's equivalent: one bad callback must not poison the module."""
    def explode(_pending):
        raise ValueError("simulated failure")

    confirmation.set_timeout_handler(explode)
    confirmation.start("U1", ["chicken"], [], [])
    time.sleep(WAIT)

    timed_out = collect_timeouts()
    confirmation.start("U2", ["egg"], [], [])
    time.sleep(WAIT)

    assert len(timed_out) == 1
    assert timed_out[0].user_id == "U2"


# ---------------------------------------------------------------------------
# Multiple users
# ---------------------------------------------------------------------------

def test_users_do_not_interfere():
    confirmation.start("U1", ["chicken"], [], [])
    confirmation.start("U2", ["egg"], [], [])

    assert confirmation.get("U1").ingredients == ["chicken"]
    assert confirmation.get("U2").ingredients == ["egg"]

    confirmation.resolve("U1")

    assert confirmation.get("U1") is None
    assert confirmation.get("U2").ingredients == ["egg"], "resolving one user must not affect another"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def test_reset_cancels_pending_timers():
    """reset() must stop scheduled work, not just clear the dict -- same guarantee as session.reset()."""
    timed_out = collect_timeouts()

    confirmation.start("U1", ["chicken"], [], [])
    confirmation.reset()

    time.sleep(WAIT)

    assert timed_out == [], "a reset confirmation should never time out"
    assert confirmation.active_count() == 0
