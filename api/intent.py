"""
api/intent.py
=============
Confirm / reject intent classifier for POST /confirm.

STATUS: KEYWORD PLACEHOLDER.
    # TODO: pending the LLM provider decision (Claude.md, Open Items #1).
    # The spec calls for an LLM here because keyword matching cannot handle
    # mixed sentences reliably. Until the provider, model and prompt are
    # chosen, this file keeps the endpoint working with simple keyword rules.
    # Only classify_intent() should change when the LLM lands -- api/app.py
    # depends on its signature and on IntentResult, nothing else.
    # The Anthropic key, when used, comes from api/web_config.py
    # (ANTHROPIC_API_KEY); never log it, use web_config.mask_secret().

Four possible intents (the fourth exists because an ambiguous reply must never
be guessed into a state change):
    confirm             "yes", "looks right"
    reject              "no, that's wrong"
    confirm+correction  "yeah that's right, but also add garlic"
    unclear             none of the above -> the UI re-asks
"""

import re
from dataclasses import dataclass, field

from nlp.extract import extract

CONFIRM = "confirm"
REJECT = "reject"
CONFIRM_AND_CORRECT = "confirm+correction"
UNCLEAR = "unclear"

# ASCII words are matched on word boundaries ("ok" must not fire inside "okra").
# Thai has no spaces, so Thai phrases are matched as substrings.
_CONFIRM_EN = re.compile(
    r"\b(yes|yeah|yep|yup|ok|okay|correct|right|sure|confirm|confirmed|good|perfect)\b", re.I
)
_CONFIRM_TH = ("ใช่", "ถูก", "โอเค", "ตกลง", "ได้เลย", "ถูกต้อง")

_REJECT_EN = re.compile(
    r"\b(wrong|incorrect|nope|nah|not right|not correct|that'?s not|isn'?t right)\b", re.I
)
_REJECT_TH = ("ไม่ใช่", "ผิด", "ไม่ถูก")
# A bare leading "no" is a rejection ("no, that's wrong") but "no pork" is an
# exclusion, so it only counts when no ingredient was found in the reply.
_BARE_NO = re.compile(r"^\s*no\b", re.I)


@dataclass
class IntentResult:
    intent: str
    add: list[str] = field(default_factory=list)      # ingredients to add
    remove: list[str] = field(default_factory=list)   # ingredients the user said "no" to


def classify_intent(reply: str, current_ingredients: list[str]) -> IntentResult:
    """
    Classify a free-text reply to "is this ingredient list right?".

    Args:
        reply:               what the user typed.
        current_ingredients: the list that was shown (unused by the keyword
                             stub; an LLM prompt would include it).

    Correction items come from the same extract() used everywhere else:
    ingredients it finds are additions, its "excluded" are removals.
    """
    parsed = extract(reply)
    add = [key for key in parsed["ingredients"] if key not in current_ingredients]
    remove = list(parsed["excluded"])
    found_items = bool(parsed["ingredients"] or parsed["excluded"])

    reject_hit = bool(
        _REJECT_EN.search(reply)
        or any(phrase in reply for phrase in _REJECT_TH)
        or (_BARE_NO.match(reply) and not found_items)
    )
    # "ไม่ใช่" contains "ใช่"; a rejection phrase always wins over a confirm word.
    confirm_hit = not reject_hit and bool(
        _CONFIRM_EN.search(reply) or any(word in reply for word in _CONFIRM_TH)
    )

    if reject_hit:
        return IntentResult(REJECT)
    if confirm_hit and (add or remove):
        return IntentResult(CONFIRM_AND_CORRECT, add=add, remove=remove)
    if confirm_hit:
        return IntentResult(CONFIRM)
    return IntentResult(UNCLEAR)
