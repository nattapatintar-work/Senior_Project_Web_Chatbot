"""
api/state.py
============
In-memory session store for the web chatbot (api/app.py).

A plain dict of session_id -> SessionState inside the FastAPI process. No Redis,
no external store: this is a single-instance demo deployment. Consequences the
caller should know about:
    - state is lost on restart (the client gets 404 and starts a new session)
    - it does not work across multiple workers/instances
    - idle sessions are swept after web_config.SESSION_TTL_SECONDS so the dict
      cannot grow forever

Not to be confused with api/session.py, which is LEGACY (LINE debounce buffer).

WHERE THE CONVERSATION IS  (SessionState.stage)
------------------------------------------------
    new                -> nothing sent yet; seasonings may still be ticked
    awaiting_confirm   -> a combined list was shown; waiting for the user's reply
    awaiting_correction-> the user rejected the list; waiting for /correct
    confirmed          -> the user confirmed; /recommend is allowed
"""

import re
import threading
import time
import uuid
from dataclasses import dataclass, field

from api import web_config

STAGE_NEW = "new"
STAGE_AWAITING_CONFIRM = "awaiting_confirm"
STAGE_AWAITING_CORRECTION = "awaiting_correction"
STAGE_CONFIRMED = "confirmed"

SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class UnknownSession(KeyError):
    """The session_id is well-formed but not in the store (never existed or expired)."""


@dataclass
class SessionState:
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    # image-derived: canonical key -> highest confidence seen across all images
    detected: dict[str, float] = field(default_factory=dict)
    # text-derived includes, in the order the user mentioned them
    include: list[str] = field(default_factory=list)
    # "no X" from text: ingredients whose dishes must be dropped by the recommender
    exclude: list[str] = field(default_factory=list)
    health_tags: list[str] = field(default_factory=list)
    # ticked on the seasoning tab; bonus-only in the recommender
    seasonings: list[str] = field(default_factory=list)
    # the category picker's choice for the current round ("all" | "savory" | "dessert"); written
    # by /recommend, reset to "all" by start_new_round()
    category: str = "all"

    stage: str = STAGE_NEW
    reject_count: int = 0

    @property
    def ingredients(self) -> list[str]:
        """The combined list: image + text, deduped in order, minus anything excluded."""
        excluded = set(self.exclude)
        merged = list(dict.fromkeys([*self.detected, *self.include]))
        return [key for key in merged if key not in excluded]

    def add_detected(self, detections: dict[str, float]) -> None:
        for key, confidence in detections.items():
            self.detected[key] = max(confidence, self.detected.get(key, 0.0))

    def apply_text_result(self, parsed: dict, ban_excluded: bool = True) -> None:
        """
        Merge an nlp.extract.extract() result into the session.

        Same rule extract() uses inside one sentence, applied across sentences:
        a later "no X" beats an earlier "X", and a later "X" beats an earlier
        "no X".

        ban_excluded (default True: "no X" in typed text bans dishes with X):
        pass False for a REMOVAL that is a correction of the ingredient list, not
        a dietary "no" -- /confirm's confirm+correction ("it isn't chicken, it's
        pork"). Then parsed["excluded"] only takes the key out of the list, like
        remove_ingredients() / the /correct checklist, and `exclude` is left
        exactly as it was (a key already banned by an earlier "no X" stays banned).

        health_tags is a REPLACE, not a merge, unlike ingredients/exclude
        above. It represents "what the user currently wants," not everything
        ever mentioned: recommend()'s _passes_health_filter is a hard AND
        across every tag in the list, so accumulating "keto" then "vegan"
        across turns would require a dish match both at once, which is
        usually zero recipes. Saying "เปลี่ยนเป็นวีแกน" after "กินคีโต" must
        leave health_tags == ["vegan"], not ["keto", "vegan"]. A message that
        mentions no tag at all leaves the existing preference alone -- only
        replace when this parse actually found one or more tags.
        """
        for key in parsed["ingredients"]:
            if key in self.exclude:
                self.exclude.remove(key)
            if key not in self.include:
                self.include.append(key)
        for key in parsed["excluded"]:
            if ban_excluded and key not in self.exclude:
                self.exclude.append(key)
            self.remove_ingredients([key])
        if parsed["health_tags"]:
            self.health_tags = list(dict.fromkeys(parsed["health_tags"]))

    def start_new_round(self) -> None:
        """
        Clear everything about the CURRENT meal request so the next
        /extract, /extract_bert, or /detect starts a fresh list instead of
        merging onto an already-finished one. Called only when the session
        is sitting at STAGE_CONFIRMED -- i.e. the user already went through
        a full confirm (and, in the real UI, /recommend) cycle, so any new
        input from here on describes a new meal, not an addition to the
        old one.

        The category choice goes back to "all": like the ingredients and
        health tags it belongs to the meal request that just finished.

        seasonings is NOT cleared: it's ticked once per session on the
        seasoning tab and locked before the chat starts (Claude.md Section
        3.1), independent of any individual meal-request cycle.
        """
        self.detected.clear()
        self.include.clear()
        self.exclude.clear()
        self.health_tags.clear()
        self.category = "all"
        self.reject_count = 0

    def remove_ingredients(self, keys: list[str]) -> None:
        """
        Drop keys from the list without banning dishes that use them. Used for
        "that's a wrong detection" (checklist), as opposed to "no X" in text,
        which goes through apply_text_result() into `exclude`.
        """
        for key in keys:
            self.detected.pop(key, None)
            if key in self.include:
                self.include.remove(key)


class SessionStore:
    """Thread-safe dict of sessions with an idle-TTL sweep."""

    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.RLock()

    def _sweep(self, now: float) -> None:
        expired = [sid for sid, s in self._sessions.items() if now - s.last_seen > self._ttl]
        for sid in expired:
            del self._sessions[sid]

    def create(self) -> SessionState:
        with self._lock:
            self._sweep(time.time())
            state = SessionState(session_id=uuid.uuid4().hex)
            self._sessions[state.session_id] = state
            return state

    def get(self, session_id: str) -> SessionState:
        with self._lock:
            now = time.time()
            self._sweep(now)
            state = self._sessions.get(session_id)
            if state is None:
                raise UnknownSession(session_id)
            state.last_seen = now
            return state

    def get_or_create(self, session_id: str | None) -> SessionState:
        return self.create() if session_id is None else self.get(session_id)

    @property
    def lock(self) -> threading.RLock:
        """Endpoints hold this while they read-modify-write one session."""
        return self._lock

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)


store = SessionStore(ttl_seconds=web_config.SESSION_TTL_SECONDS)
