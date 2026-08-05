"""
tests/test_session.py
=====================
Tests for the session buffer and debounce logic in api/session.py.

These need no LINE account, no .env and no internet. That is the payoff for
keeping api/session.py free of imports from api/config.py — the tricky part of
Week 2 is testable in isolation, in milliseconds.

Debounce is timing-based, so these tests use a very short window (0.05s) via
session.configure() and sleep just past it. Real usage is 2.5s.

Run with:
    pytest tests/test_session.py -v
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api import session

# Debounce window used throughout. Long enough to be reliable on a slow
# machine, short enough that the whole file finishes in under a second.
TEST_DEBOUNCE = 0.05

# How long to wait for a flush. Comfortably past the window, so a slightly
# late timer does not cause a flaky failure.
WAIT = TEST_DEBOUNCE * 4


@pytest.fixture(autouse=True)
def clean_session_state():
    """
    Reset module state before and after every test.

    autouse=True applies it to every test in the file automatically.

    api/session.py keeps its buffers in module-level variables, which persist
    between tests in the same process. Without this fixture, one test's
    leftover session would leak into the next and cause failures that depend on
    test ordering — the worst kind to debug.
    """
    session.reset()
    session.configure(debounce_seconds=TEST_DEBOUNCE, max_images=5)
    yield
    session.reset()


def collect_flushes() -> list:
    """
    Install a flush handler that records sessions instead of replying.

    Returns the list it appends to, so a test can assert on what was flushed.
    This is the seam that makes the module testable: the real handler in
    main.py sends LINE messages, but session.py neither knows nor cares.
    """
    flushed = []
    session.set_flush_handler(flushed.append)
    return flushed


# ---------------------------------------------------------------------------
# Buffering
# ---------------------------------------------------------------------------

def test_single_text_flushes_after_the_window():
    flushed = collect_flushes()

    session.add_text("U1", "มีไก่", "token_1")

    # Nothing yet — the window has not closed.
    assert flushed == []

    time.sleep(WAIT)

    assert len(flushed) == 1
    assert flushed[0].texts == ["มีไก่"]


def test_two_texts_merge_into_one_flush():
    """
    The whole point of debouncing: two quick messages produce ONE reply.

    Without this, a user typing two lines gets two separate recommendations,
    neither aware of the other.
    """
    flushed = collect_flushes()

    session.add_text("U1", "มีไก่กับไข่", "token_1")
    session.add_text("U1", "อยากกินคลีน", "token_2")

    time.sleep(WAIT)

    assert len(flushed) == 1, "two quick messages should produce one flush"
    assert flushed[0].texts == ["มีไก่กับไข่", "อยากกินคลีน"]


def test_text_and_image_merge_into_one_flush():
    """A photo plus a caption is one request, not two."""
    flushed = collect_flushes()

    session.add_image("U1", "img_1", "token_1")
    session.add_text("U1", "อยากกินคลีน", "token_2")

    time.sleep(WAIT)

    assert len(flushed) == 1
    assert flushed[0].image_ids == ["img_1"]
    assert flushed[0].texts == ["อยากกินคลีน"]


def test_each_message_extends_the_window():
    """
    Debounce means "quiet for N seconds", not "N seconds after the first".

    Messages arriving steadily should keep pushing the deadline out, so the
    flush happens only once the user actually stops.
    """
    flushed = collect_flushes()

    for i in range(4):
        session.add_text("U1", f"msg{i}", f"token_{i}")
        # Sleep less than the window, so each message arrives before the
        # previous timer can fire.
        time.sleep(TEST_DEBOUNCE * 0.4)

    assert flushed == [], "should not have flushed while still receiving"

    time.sleep(WAIT)

    assert len(flushed) == 1
    assert len(flushed[0].texts) == 4


# ---------------------------------------------------------------------------
# Reply tokens
# ---------------------------------------------------------------------------

def test_newest_reply_token_wins():
    """
    Merged sessions must keep the most recent reply token.

    Tokens are single-use and expire in ~30s. Only one reply is sent, so the
    freshest token is the one with the most life left when the timer fires.
    Keeping the oldest risks replying with an already-expired token.
    """
    flushed = collect_flushes()

    session.add_text("U1", "first", "token_OLD")
    session.add_text("U1", "second", "token_NEW")

    time.sleep(WAIT)

    assert flushed[0].reply_token == "token_NEW"


# ---------------------------------------------------------------------------
# Image cap
# ---------------------------------------------------------------------------

def test_image_cap_holds_at_five():
    """
    At most 5 images per session, extras counted not silently dropped.

    Each image costs a download now and a YOLO pass from Week 8, so an
    unbounded burst could stall a reply past its token lifetime.
    """
    flushed = collect_flushes()

    for i in range(8):
        session.add_image("U1", f"img_{i}", f"token_{i}")

    time.sleep(WAIT)

    assert len(flushed[0].image_ids) == 5, "should keep only the first 5"
    assert flushed[0].dropped_images == 3, "should count the 3 it dropped"
    assert flushed[0].image_ids == [f"img_{i}" for i in range(5)]


def test_cap_is_configurable():
    session.configure(max_images=2)
    flushed = collect_flushes()

    for i in range(5):
        session.add_image("U1", f"img_{i}", "token")

    time.sleep(WAIT)

    assert len(flushed[0].image_ids) == 2
    assert flushed[0].dropped_images == 3


# ---------------------------------------------------------------------------
# Multiple users
# ---------------------------------------------------------------------------

def test_users_do_not_interfere():
    """
    Two people messaging at once must get separate sessions.

    Sessions are keyed by user_id. If that keying were wrong, one user's
    ingredients would leak into another's recommendation — and with a shared
    dict, their reply token too, so the wrong person would get the reply.
    """
    flushed = collect_flushes()

    session.add_text("U1", "ไก่", "token_u1")
    session.add_text("U2", "ไข่", "token_u2")

    time.sleep(WAIT)

    assert len(flushed) == 2

    by_user = {s.user_id: s for s in flushed}
    assert by_user["U1"].texts == ["ไก่"]
    assert by_user["U2"].texts == ["ไข่"]
    assert by_user["U1"].reply_token == "token_u1"
    assert by_user["U2"].reply_token == "token_u2"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def test_session_is_removed_after_flushing():
    """
    Flushed sessions must leave the dict, or it grows forever.

    Sessions are held in memory, so a leak here is a slow memory leak that only
    shows up after the bot has been running for a long time.
    """
    collect_flushes()

    session.add_text("U1", "ไก่", "token")
    assert session.active_count() == 1

    time.sleep(WAIT)

    assert session.active_count() == 0


def test_new_message_after_flush_starts_a_fresh_session():
    """A second conversation must not inherit the first one's contents."""
    flushed = collect_flushes()

    session.add_text("U1", "first conversation", "token_1")
    time.sleep(WAIT)

    session.add_text("U1", "second conversation", "token_2")
    time.sleep(WAIT)

    assert len(flushed) == 2
    assert flushed[0].texts == ["first conversation"]
    assert flushed[1].texts == ["second conversation"], "should not carry over"


def test_reset_cancels_pending_timers():
    """reset() must stop scheduled work, not just clear the dict."""
    flushed = collect_flushes()

    session.add_text("U1", "ไก่", "token")
    session.reset()

    time.sleep(WAIT)

    assert flushed == [], "a reset session should never flush"
    assert session.active_count() == 0


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def test_a_failing_handler_does_not_break_later_sessions():
    """
    An exception in the flush handler must be contained.

    It runs on a timer thread, where an uncaught exception would disappear
    silently and could leave the module in a broken state. One bad message
    should not stop the bot from answering the next one.
    """
    def explode(_sess):
        raise ValueError("simulated failure")

    session.set_flush_handler(explode)
    session.add_text("U1", "boom", "token")
    time.sleep(WAIT)

    # The module must still work afterwards.
    flushed = collect_flushes()
    session.add_text("U2", "still working", "token")
    time.sleep(WAIT)

    assert len(flushed) == 1
    assert flushed[0].texts == ["still working"]
