"""
api/confirmation.py
====================
Remembers, per user, that they have been asked "anything else?" after a
debounce window closed — and what was already gathered — so the NEXT incoming
message from that user can be told apart from a brand-new request.

THE PROBLEM THIS SOLVES
------------------------
api/session.py's _flush() pops and discards its Session the moment a debounce
window closes (see session.py's own docstring for why: it hands the timer
thread sole ownership of the session and prevents a race with a message that
arrives at the same instant). That is correct for what session.py is for, but
it means nothing remembers a user was mid-conversation once process_session()
has run once. Whatever that user sends next — including a tap on the
"anything else?" Quick Reply button — creates a brand-new Session and goes
through the exact same debounce -> flush path from scratch, with no way to
tell "this is answering the confirmation" from "this is an unrelated new
request."

This module is that second, independent piece of state. It survives past
session.py's Session being popped, and it is looked up at the start of the
NEXT flush for the same user.

WHY A SEPARATE MODULE, NOT MORE FIELDS ON session.Session
------------------------------------------------------------
Debounce ("has the user stopped typing") and confirmation ("did the user say
they are done") are two different questions with two different lifetimes — a
Session lives ~2.5s; a PendingConfirmation lives up to CONFIRM_TIMEOUT_SECONDS
(60s) and is only created once per completed debounce round, not per message.
Keeping them apart keeps each module's single job legible.

Same dependency-injection pattern as session.py, for the same reasons:
this file imports nothing from the rest of the project (api/config.py
deliberately crashes without a .env file, and api/main.py already imports
session.py, so importing main.py back here would be circular). api/main.py
wires in the timeout callback via set_timeout_handler(), exactly like it
wires session.py's flush handler via session.set_flush_handler().
"""

import threading
import time
from dataclasses import dataclass, field

# How long to wait for the user to respond before auto-proceeding with
# whatever was gathered so far.
#
# Deliberately generous. Firing this timer means pushing the final
# recommendation with no reply token available (this path is triggered by our
# own timer, not by an incoming webhook), and Push COSTS LINE quota on the
# Thai free OA plan, which has no top-up (see concern.md's C11 / push-vs-reply
# discussion, and api/main.py's send_reply() docstring). 60s is well past the
# ~30s a LINE reply token would live anyway — this timer is answering a
# different question ("did the user come back at all?") than the debounce
# timer does ("did the user stop typing for a moment?"), so there is no
# tension with reply-token timing. The goal is for this to fire only for
# users who have genuinely walked away, not ones who paused to think.
CONFIRM_TIMEOUT_SECONDS = 60.0

# How many "anything else?" prompts to send before proceeding regardless of
# whether the user keeps adding more. 2 total: the first prompt (sent by
# start()) plus exactly one re-ask if the user adds something instead of
# confirming. A third addition proceeds straight to the recommendation rather
# than asking again, so the bot never feels like it is stalling. The debounce
# window already batches a quick burst of "also X, also Y" into a single
# round, so this caps genuinely repeated back-and-forth, not someone adding
# several things in one message.
MAX_CONFIRMATION_PROMPTS = 2

# The exact button text/label, and the phrase that counts as "no, I'm done."
# A single source of truth: api/main.py's Quick Reply button uses this same
# string as both its label and its message text, so tapping it always
# produces something is_confirmation_text() recognises. Additional phrases are
# accepted too, for a user who confirms by typing instead of tapping.
PRIMARY_CONFIRM_PHRASE = "ไม่มี, ยืนยัน"
CONFIRM_PHRASES = {PRIMARY_CONFIRM_PHRASE, "ไม่มี ยืนยัน", "ยืนยัน", "พอแล้ว"}


@dataclass
class PendingConfirmation:
    """Everything gathered for one user while they are mid-confirmation."""

    user_id: str

    # default_factory, not "= []" — see session.py's Session dataclass for why
    # a plain mutable default would be shared across every instance.
    ingredients: list[str] = field(default_factory=list)
    health_tags: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)

    # How many confirmation prompts have been sent so far. start() sets this
    # to 1 (the first prompt). Compared against MAX_CONFIRMATION_PROMPTS by
    # the caller (api/main.py) to decide whether to ask again or proceed —
    # this module tracks the count, the caller owns the policy.
    prompts_sent: int = 1

    timer: threading.Timer | None = None
    created: float = field(default_factory=time.monotonic)


# --- Module state ------------------------------------------------------------
# Same shape as session.py's _sessions/_lock: in-memory only (acceptable here
# too — a pending confirmation lives at most 60s, so a restart mid-window
# costs one user one repeated prompt), guarded by one lock.

_pending: dict[str, PendingConfirmation] = {}
_lock = threading.Lock()

# api/main.py supplies this: called with the popped PendingConfirmation when
# the confirmation window elapses with no response. None means "not wired up
# yet," the normal state during tests.
_timeout_handler = None


def configure(timeout_seconds: float | None = None, max_prompts: int | None = None) -> None:
    """
    Override CONFIRM_TIMEOUT_SECONDS / MAX_CONFIRMATION_PROMPTS. Called by
    tests to use a short timeout instead of waiting a real 60s.

    Reassigns the public module constants directly (same names api/main.py
    already reads, e.g. `confirmation.MAX_CONFIRMATION_PROMPTS`), rather than
    keeping a separate shadow copy — so a caller that read the constant
    before configure() and one that reads it after always see the same
    single source of truth, matching how every other value in this module is
    read.
    """
    global CONFIRM_TIMEOUT_SECONDS, MAX_CONFIRMATION_PROMPTS
    if timeout_seconds is not None:
        CONFIRM_TIMEOUT_SECONDS = timeout_seconds
    if max_prompts is not None:
        MAX_CONFIRMATION_PROMPTS = max_prompts


def set_timeout_handler(handler) -> None:
    """Register the function to call when a user's confirmation window times out."""
    global _timeout_handler
    _timeout_handler = handler


def is_confirmation_text(text: str) -> bool:
    """
    True if `text` is (exactly, after stripping whitespace) one of the
    recognised confirmation phrases.

    Deliberately an exact match, not a substring/fuzzy check — a user typing
    a sentence that happens to contain "ยืนยัน" as part of something else
    (rare, but possible) must not be misread as confirming. This mirrors
    nlp/extract.py's own preference for exact synonym matches over fuzzy ones
    wherever a false positive would be worse than a false negative.
    """
    return text.strip() in CONFIRM_PHRASES


def start(
    user_id: str,
    ingredients: list[str],
    health_tags: list[str],
    excluded: list[str],
) -> PendingConfirmation:
    """
    Begin waiting for this user's confirmation after a completed debounce
    round. Overwrites any existing pending state for them — callers should
    check get() first if that would be surprising (in practice api/main.py
    only calls start() when get() already returned None).
    """
    with _lock:
        pending = PendingConfirmation(
            user_id=user_id,
            ingredients=list(dict.fromkeys(ingredients)),
            health_tags=list(dict.fromkeys(health_tags)),
            excluded=list(dict.fromkeys(excluded)),
        )
        _pending[user_id] = pending
        _restart_timer(pending)
        return pending


def get(user_id: str) -> PendingConfirmation | None:
    """Look up this user's pending confirmation, if any. Does not resolve it."""
    with _lock:
        return _pending.get(user_id)


def merge(
    user_id: str,
    ingredients: list[str],
    health_tags: list[str],
    excluded: list[str],
) -> PendingConfirmation | None:
    """
    Fold newly-gathered ingredients/tags into an existing pending
    confirmation and restart its timeout (new activity from the user).

    Does NOT change prompts_sent — that is bumped separately by
    record_reprompt(), only when the caller actually decides to send another
    prompt, so the two concerns (what data we have vs. how many times we have
    asked) cannot drift out of sync with each other.

    Returns None if there was no pending state for this user — the caller
    should treat that as "not actually mid-confirmation" rather than crash.
    """
    with _lock:
        pending = _pending.get(user_id)
        if pending is None:
            return None
        pending.ingredients = list(dict.fromkeys(pending.ingredients + ingredients))
        pending.health_tags = list(dict.fromkeys(pending.health_tags + health_tags))
        pending.excluded = list(dict.fromkeys(pending.excluded + excluded))
        _restart_timer(pending)
        return pending


def record_reprompt(user_id: str) -> PendingConfirmation | None:
    """Bump prompts_sent by 1 — call this exactly when sending another 'anything else?' prompt."""
    with _lock:
        pending = _pending.get(user_id)
        if pending is None:
            return None
        pending.prompts_sent += 1
        return pending


def resolve(user_id: str) -> PendingConfirmation | None:
    """
    Pop and return a user's pending confirmation — they have confirmed, hit
    the prompt cap, or a timeout is firing. Cancels its timer. None if there
    was not one (e.g. the timeout and the user's own confirmation raced; only
    one of them gets a non-None result, the other sees it already resolved).
    """
    with _lock:
        pending = _pending.pop(user_id, None)
    if pending is not None and pending.timer is not None:
        pending.timer.cancel()
    return pending


def _restart_timer(pending: PendingConfirmation) -> None:
    """Cancel any pending countdown and start a fresh one. Caller holds _lock."""
    if pending.timer is not None:
        pending.timer.cancel()

    timer = threading.Timer(CONFIRM_TIMEOUT_SECONDS, _on_timeout, args=(pending.user_id,))
    timer.daemon = True  # same reasoning as session.py's timers: let Python exit cleanly
    timer.start()
    pending.timer = timer


def _on_timeout(user_id: str) -> None:
    """Runs on the timer's own thread. Resolves the pending state and hands it to the registered handler."""
    pending = resolve(user_id)
    if pending is None:
        # Already resolved by the user's own confirmation in the meantime —
        # the race mentioned in resolve()'s docstring. Nothing to do.
        return

    if _timeout_handler is None:
        print(
            f"[confirmation] timeout fired for {user_id} but no handler is "
            f"registered (set_timeout_handler() was never called)",
            flush=True,
        )
        return

    try:
        _timeout_handler(pending)
    except Exception:
        # Same reasoning as session.py's _flush(): an exception on a timer
        # thread otherwise vanishes silently.
        import traceback

        print(f"[confirmation] timeout handler failed for {user_id}:", flush=True)
        traceback.print_exc()


def active_count() -> int:
    """How many users currently have a pending confirmation. For tests and debugging."""
    with _lock:
        return len(_pending)


def reset() -> None:
    """Cancel every pending timer and clear all state. Used by tests so one test's leftover state cannot leak into the next."""
    with _lock:
        for pending in _pending.values():
            if pending.timer is not None:
                pending.timer.cancel()
        _pending.clear()
