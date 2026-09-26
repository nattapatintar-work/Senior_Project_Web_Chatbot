"""
api/session.py
==============
LEGACY (LINE OA track) -- the web backend has no debounce (processing starts
on Enter) and uses api/state.py instead. Kept until removal is approved; do
not extend.

Collects the messages one user sends in quick succession and processes them as
a single request.

THE PROBLEM THIS SOLVES
-----------------------
People do not send one tidy message. They send a photo, then two seconds later
a caption:

    11:04:01  [photo of chicken and egg]
    11:04:03  "อยากกินคลีน"

Without buffering, that is two separate webhooks, so the bot replies twice: once
knowing only the photo, once knowing only the text. Neither reply has the whole
picture, and the user gets spammed.

THE FIX: DEBOUNCE
-----------------
Do not act on a message immediately. Start a 2.5-second timer instead. If
another message arrives before it fires, cancel the timer and start a new one.
Work happens only after the user has been quiet for 2.5 seconds — by which time
everything they sent is sitting in one buffer.

    photo arrives  -> buffer it, start 2.5s timer
    text arrives   -> buffer it, CANCEL old timer, start a fresh 2.5s timer
    (silence)      -> timer fires -> process photo + text together, reply once

This is also what lets the webhook return HTTP 200 instantly. Buffering is a
dictionary write, so it takes microseconds; the slow work (downloading images,
running the recommender) happens later on the timer's own thread. LINE retries
any webhook that answers slowly, which would cause duplicate replies — so
answering fast is not just for speed, it prevents a real bug.

WHY THIS FILE IMPORTS NOTHING FROM THE PROJECT
----------------------------------------------
No import of api/config.py, and no import of api/main.py. Two reasons:

  * config.py deliberately crashes if .env is missing. If this file imported
    it, tests/test_session.py could not run without real LINE credentials.
  * main.py imports this file. If this file imported main.py back, Python
    would hit a circular import and fail to start.

Instead main.py pushes its settings in via configure() and its worker function
in via set_flush_handler(). This file stays pure Python and is fully testable
on its own.
"""

import threading
import time
import traceback
from dataclasses import dataclass, field


@dataclass
class Session:
    """Everything one user has sent during the current debounce window."""

    user_id: str

    # field(default_factory=list) rather than "= []".
    # A plain "= []" would be created ONCE and shared by every Session, so all
    # users would end up appending into the same list. default_factory makes a
    # fresh list per instance. This is a classic Python trap.
    texts: list[str] = field(default_factory=list)
    image_ids: list[str] = field(default_factory=list)

    # The reply token from the MOST RECENT message. See add_text() for why.
    reply_token: str = ""

    # Images beyond the cap, so the reply can mention them instead of silently
    # ignoring them.
    dropped_images: int = 0

    # The pending countdown. None means nothing is scheduled.
    timer: threading.Timer | None = None

    # time.monotonic() timestamps of this session's first and most recent
    # message. Wall-clock time.time() is deliberately not used — it can jump
    # (NTP sync, DST, manual clock changes), which would make an elapsed-time
    # measurement lie. first_seen lets main.py log how much of the ~30s reply
    # token lifetime is spent before the LINE reply call actually fires.
    first_seen: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)


# --- Module state ----------------------------------------------------------
# In memory only, so everything is lost when the server restarts. That is
# acceptable here: a session lives ~2.5 seconds, and losing one mid-restart
# costs the user one repeated message.

_sessions: dict[str, Session] = {}

# One lock guarding _sessions.
#
# Timers fire on their own threads, and Flask handles requests on more threads.
# Without a lock, two threads could modify the same dict at the same time and
# corrupt it. "with _lock:" means only one thread at a time may run that block.
#
# Keep locked blocks SHORT — never do network calls while holding it, or every
# other user waits.
_lock = threading.Lock()

# Settings, overridable via configure(). Defaults match the project doc.
_debounce_seconds: float = 2.5
_max_images: int = 5

# The function that does the real work once a window closes. main.py supplies
# it. None means "not wired up yet", which is the normal state during tests.
_flush_handler = None


def configure(debounce_seconds: float | None = None, max_images: int | None = None) -> None:
    """Override the defaults. Called by main.py at startup, and by tests."""
    global _debounce_seconds, _max_images
    if debounce_seconds is not None:
        _debounce_seconds = debounce_seconds
    if max_images is not None:
        _max_images = max_images


def set_flush_handler(handler) -> None:
    """
    Register the function to call when a debounce window closes.

    It receives one Session and is responsible for the real work: download the
    images, run NLP and the recommender, send the reply.

    Passing it in like this (instead of importing main.py) is what keeps this
    module free of circular imports and testable on its own.
    """
    global _flush_handler
    _flush_handler = handler


def add_text(user_id: str, text: str, reply_token: str) -> None:
    """Buffer a text message and restart this user's countdown."""
    with _lock:
        session = _get_or_create(user_id)
        session.texts.append(text)
        session.last_seen = time.monotonic()

        # Always overwrite with the NEWEST reply token.
        #
        # Every incoming message carries its own token. A token is single-use
        # and expires in roughly 30 seconds. When three messages merge into one
        # session we can only reply once, so we keep the freshest token — it
        # has the most life left when the timer finally fires.
        session.reply_token = reply_token

        _restart_timer(session)


def add_image(user_id: str, message_id: str, reply_token: str) -> None:
    """
    Buffer an image reference and restart this user's countdown.

    Only the message_id is stored, not the picture itself. Downloading is slow
    and this runs inside the webhook request — it happens later, in the flush
    handler, once the window closes.
    """
    with _lock:
        session = _get_or_create(user_id)
        session.last_seen = time.monotonic()

        if len(session.image_ids) < _max_images:
            session.image_ids.append(message_id)
        else:
            # Over the cap. Count it so the reply can say so; each extra image
            # costs a download and, from Week 8, a YOLO pass.
            session.dropped_images += 1

        session.reply_token = reply_token
        _restart_timer(session)


def _get_or_create(user_id: str) -> Session:
    """Fetch this user's session, creating one if needed. Caller holds _lock."""
    session = _sessions.get(user_id)
    if session is None:
        session = Session(user_id=user_id)
        _sessions[user_id] = session
    return session


def _restart_timer(session: Session) -> None:
    """
    Cancel any pending countdown and start a fresh one. Caller holds _lock.

    Cancel-then-restart IS the debounce. Each new message pushes the deadline
    further out, so the work only runs after the user stops sending.
    """
    if session.timer is not None:
        # Harmless if the timer already fired — cancel() on a finished timer
        # does nothing.
        session.timer.cancel()

    timer = threading.Timer(_debounce_seconds, _flush, args=(session.user_id,))

    # daemon=True lets Python exit even with timers pending. Without it,
    # Ctrl+C would hang until every countdown finished.
    timer.daemon = True
    timer.start()

    session.timer = timer


def _flush(user_id: str) -> None:
    """
    Runs on the timer's thread once the user has gone quiet.

    Note the two-step structure: take the session out of the dict while holding
    the lock, then do the slow work AFTER releasing it.

    Popping under the lock matters. It hands this thread sole ownership of the
    session, so a message arriving at the same moment starts a clean new one
    instead of mutating a session that is already being processed. Skipping
    this produces a bug that shows up once in a few hundred messages and is
    almost impossible to reproduce on purpose.

    Releasing the lock before the slow work matters just as much: downloading
    images takes seconds, and holding the lock that long would freeze every
    other user.
    """
    with _lock:
        session = _sessions.pop(user_id, None)

    # Already flushed, or cancelled. Nothing to do.
    if session is None:
        print(f"[session] flush skipped for {user_id}: already popped (no-op)", flush=True)
        return

    if _flush_handler is None:
        # No handler registered — normal in tests, but a silent bug in
        # production: it would mean main.py never called set_flush_handler(),
        # so every debounce window closes and nothing happens, with no error
        # anywhere. Logging it here is what makes that case distinguishable
        # from a handler that ran and simply produced no visible output.
        print(
            f"[session] flush skipped for {user_id}: no flush handler registered "
            f"(session.set_flush_handler() was never called)",
            flush=True,
        )
        return

    try:
        _flush_handler(session)
    except Exception:
        # An exception on a timer thread vanishes silently by default: there is
        # no request to return 500 to and no console output. The bot would just
        # stop replying with no clue why. Printing the traceback makes the
        # failure visible.
        # flush=True forces it out immediately. Without it, output redirected
        # to a file sits in a buffer and the error appears to have vanished.
        print(f"[session] flush failed for user {user_id}:", flush=True)
        traceback.print_exc()


def active_count() -> int:
    """How many users currently have an open window. For tests and debugging."""
    with _lock:
        return len(_sessions)


def reset() -> None:
    """
    Cancel every pending timer and drop all sessions.

    Used by tests so one test's leftover state cannot leak into the next.
    """
    with _lock:
        for session in _sessions.values():
            if session.timer is not None:
                session.timer.cancel()
        _sessions.clear()
