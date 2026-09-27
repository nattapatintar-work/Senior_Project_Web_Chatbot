"""
nlp/extract.py
==============
Turns a Thai sentence typed by the user into structured data the rest of the
system can work with.

    "มีกุ้งกับไข่ อยากกินคลีน ไม่เอาหมู"
        |
        v
    {"ingredients": ["shrimp", "egg"], "health_tags": ["clean"], "excluded": ["pork"]}

This function is Handoff #2 to Person 1 (due Week 5), so the signature is a
promise: the three keys and their types never change. Everything below this
line is free to change.

HOW IT WORKS
------------
1. Tokenize with pythainlp.word_tokenize(), using a CUSTOM DICTIONARY built
   from every ingredients.json/health_terms.json synonym plus PyThaiNLP's own
   word list. This step is more load-bearing than it looks -- see "THE
   TOKENIZER FINDING" below.
2. Walk the tokens. Each one is looked up against the synonym index first
   (exact match), then against rapidfuzz (typo tolerance) if that fails.
3. A negation cue ("ไม่เอา", "ไม่ใส่", "ไม่มี") flips everything matched until
   the next whitespace-delimited segment from "ingredients" to "excluded".
4. Anything landing in "excluded" is removed from "ingredients" -- a key is
   never allowed to be in both.

THE TOKENIZER FINDING (why this isn't "just call word_tokenize")
------------------------------------------------------------------
PyThaiNLP's *default* tokenizer does not know this project's ingredient
vocabulary, and it silently destroys exactly the compounds this system most
needs intact:

    word_tokenize("ไม่เอาน้ำมันหอย")   # no custom dict
        -> ['ไม่', 'เอา', 'น้ำมัน', 'หอย']

"น้ำมันหอย" (oyster sauce) is split into "น้ำมัน" (oil) + "หอย" (shellfish,
not a dictionary key on its own). A step-4 matcher would resolve "น้ำมัน" to
vegetable_oil and silently drop "หอย" -- the exact concern.md C4 bug
("a dish containing oyster sauce passes a vegan filter"), except produced by
tokenization, not by matching order. Sorting synonyms by length descending
(C4's original prescribed fix) cannot repair this, because the compound is
already gone by the time any synonym list gets consulted.

    word_tokenize("อยากกินคลีน")       # no custom dict
        -> ['อยาก', 'กิน', 'คลี', 'น']

The project's own canonical worked example (Claude.md:122) does not survive
default tokenization either -- "คลีน" becomes "คลี" + "น", neither of which
is a usable lookup key.

The fix, verified during Week 5 planning: pass a pythainlp.util.Trie built
from every synonym in both dictionaries as `custom_dict`. Confirmed live --
"น้ำมันหอย" and "คลีน" both survive as single tokens, without disturbing
compounds that were already correct ("พริกไทย", "กุ้งแห้ง", "น้ำปลา").

A KNOWN LIMITATION: THAI TYPO RECOVERY IS WEAK
------------------------------------------------
rapidfuzz recovers English typos reliably ("chiken" -> "chicken" scores 92%).
It does NOT reliably recover Thai typos, and this was verified, not assumed:
a misspelled Thai word is usually not in the custom dictionary, so newmm (the
underlying segmenter) shatters it into syllable-sized fragments instead of
keeping it as one unknown chunk --

    word_tokenize("มีมะเขือเทดด้วย")   # typo of มะเขือเทศ, tomato
        -> ['มี', 'มะเขือ', 'เท', 'ด', 'ด้วย']

By the time rapidfuzz sees "มะเขือ" (the largest surviving fragment), the
similarity to the full "มะเขือเทศ" is only 80% -- below the 85 cutoff this
module uses. Lowering the cutoff to catch fragments like this was tried
during planning and rejected: at 60%, unrelated short tokens started matching
real synonyms by accident ("กระ" -> "กระเพรา" at 60%). A cutoff that recovers
fragment typos also manufactures false positives on ordinary short words, and
false positives are worse than missed typos here, because they corrupt a
result silently instead of just failing to improve it. This is a genuine,
documented limitation, not an oversight -- see concern.md.
"""

import json
from pathlib import Path

from pythainlp import word_tokenize
from pythainlp.corpus.common import thai_words
from pythainlp.util import Trie
from rapidfuzz import fuzz, process

# Where the shared dictionaries live. __file__ is this file's own path, so
# this works no matter which folder you run python from.
INGREDIENTS_PATH = Path(__file__).parent.parent / "data" / "ingredients.json"
HEALTH_TERMS_PATH = Path(__file__).parent.parent / "data" / "health_terms.json"

# Negation cues. The tokenizer splits "ไม่เอา" into ['ไม่', 'เอา'] even with
# the custom dict (confirmed during planning), so negation is detected as a
# TWO-TOKEN SEQUENCE ("ไม่" followed by one of these), not a single token.
NEGATION_VERBS = {"เอา", "ใส่", "มี"}

# A token shorter than this never goes through fuzzy matching. Short Thai
# tokens are common function words ("มี", "กับ", "ใส่") and short synonyms
# ("นม", "เนย") that a loose fuzzy cutoff would false-positive on constantly
# -- verified during planning: "กระ" matches "กระเพรา" at 60% similarity,
# which is exactly the kind of accidental match this guards against.
MIN_FUZZY_TOKEN_LENGTH = 4

# Below this rapidfuzz ratio, a candidate is not trusted. Chosen so that
# "chiken" -> "chicken" (92%) passes and "กระ" -> "กระเพรา" (60%) does not.
FUZZY_SCORE_CUTOFF = 85


def load_ingredients() -> dict:
    """
    Read data/ingredients.json off disk and hand it back as a Python dict.

    encoding="utf-8" is not optional here. The file is full of Thai text, and
    on Windows Python otherwise guesses a legacy encoding and throws
    UnicodeDecodeError.
    """
    with open(INGREDIENTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_health_terms() -> dict:
    """
    Read data/health_terms.json, the Thai/English vocabulary for the four
    diet tags. Separate from ingredients.json on purpose -- see that file's
    own header for why a user-utterance vocabulary can't live inside the
    ingredient dictionary.
    """
    with open(HEALTH_TERMS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Built once at import time, not per call. extract() runs on the LINE
# reply-token path (concern C11: the token lives ~30s), so rebuilding a Trie
# out of 300+ synonyms on every message would be a wasteful place to lose
# time.
# ---------------------------------------------------------------------------

def _build_synonym_index(ingredients: dict, health_terms: dict) -> dict:
    """
    Map every synonym string to the canonical key that owns it.

    Built by inserting LONGEST synonyms first. Exact-match lookup doesn't
    actually depend on insertion order (tests/test_contract.py's
    test_no_synonym_is_shared_by_two_ingredients guarantees no synonym is
    claimed twice), but this ordering is kept anyway as the belt-and-braces
    half of concern.md C4's prescribed fix, and so this function still does
    something sane if that uniqueness guarantee is ever relaxed.
    """
    pairs = [
        (syn, key)
        for key, entry in ingredients.items()
        for syn in entry["synonyms"]
    ] + [
        (syn, f"health:{tag}")
        for tag, entry in health_terms.items()
        if not tag.startswith("_")
        for syn in entry["synonyms"]
    ]
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return dict(pairs)  # later (shorter) duplicates lose; see docstring above


def _build_trie(synonym_index: dict) -> Trie:
    """
    A custom dictionary so the tokenizer keeps our compounds whole.

    See the module docstring's "THE TOKENIZER FINDING" section for why this
    step exists at all -- without it, "น้ำมันหอย" and "คลีน" both shatter
    before any matching logic runs.
    """
    return Trie(list(thai_words()) + list(synonym_index.keys()))


_INGREDIENTS = load_ingredients()
_HEALTH_TERMS = load_health_terms()
_SYNONYM_INDEX = _build_synonym_index(_INGREDIENTS, _HEALTH_TERMS)
_ALL_SYNONYMS = list(_SYNONYM_INDEX.keys())
_TRIE = _build_trie(_SYNONYM_INDEX)


def _resolve_token(token: str) -> str | None:
    """
    Look up one token. Exact match first, then a cautious fuzzy fallback.

    Returns a canonical ingredient key, "health:<tag>", or None if nothing
    matched. None is a normal, common outcome -- most tokens in a sentence
    are function words like "มี" or "กับ", not ingredients.
    """
    if token in _SYNONYM_INDEX:
        return _SYNONYM_INDEX[token]

    if len(token) < MIN_FUZZY_TOKEN_LENGTH:
        return None

    match = process.extractOne(token, _ALL_SYNONYMS, scorer=fuzz.ratio)
    if match is None:
        return None
    candidate, score, _ = match
    if score < FUZZY_SCORE_CUTOFF:
        return None
    return _SYNONYM_INDEX[candidate]


def resolve_token(token: str) -> str | None:
    """
    Public wrapper around _resolve_token, for other modules (e.g.
    nlp/extract_bert.py) that need to map a raw string to a canonical key
    without duplicating the synonym-index/fuzzy-match logic.
    """
    return _resolve_token(token)


def extract(text: str) -> dict:
    """
    Pull ingredients, health tags, and exclusions out of a Thai sentence.

    Args:
        text: whatever the user typed, e.g. "มีไก่กับไข่ ไม่เอาพริก"

    Returns:
        A dict with exactly these three keys, each one a list of strings:
            {
                "ingredients": [...],   # canonical keys, e.g. ["chicken", "egg"]
                "health_tags": [...],   # e.g. ["clean", "keto"]
                "excluded":    [...],   # things the user said NO to
            }

        "Canonical key" means the English snake_case name used as the
        top-level key in ingredients.json ("green_onion", not "ต้นหอม" and
        not "spring onion"). Everything downstream expects that form.
    """
    tokens = word_tokenize(text, custom_dict=_TRIE)

    ingredients: list[str] = []
    excluded: list[str] = []
    health_tags: list[str] = []
    negated = False

    i = 0
    n = len(tokens)
    while i < n:
        token = tokens[i]
        stripped = token.strip()

        # A blank/whitespace token marks the end of a clause -- negation
        # scope does not carry across it. Real segmentation of the
        # canonical example ("มีกุ้งกับไข่ อยากกินคลีน ไม่เอาหมู") only has
        # negation in its last clause, and this is what keeps it from
        # leaking backward onto "กุ้ง"/"ไข่".
        if not stripped:
            negated = False
            i += 1
            continue

        # "ไม่" followed by a negation verb is a two-token cue, not a single
        # token -- confirmed the tokenizer always splits it this way, even
        # with the custom dict. Neither token is itself a synonym of
        # anything, so consuming both here costs nothing.
        if stripped == "ไม่" and i + 1 < n and tokens[i + 1].strip() in NEGATION_VERBS:
            negated = True
            i += 2
            continue

        resolved = _resolve_token(stripped)
        if resolved is not None:
            if resolved.startswith("health:"):
                tag = resolved.removeprefix("health:")
                if tag not in health_tags:
                    health_tags.append(tag)
            elif negated:
                if resolved not in excluded:
                    excluded.append(resolved)
            else:
                if resolved not in ingredients:
                    ingredients.append(resolved)

        i += 1

    # A key must never be claimed by both lists at once -- excluded wins,
    # since "ไม่เอา X" is a stronger, more specific signal than an earlier,
    # unqualified mention of X in the same message.
    ingredients = [key for key in ingredients if key not in excluded]

    return {
        "ingredients": ingredients,
        "health_tags": health_tags,
        "excluded": excluded,
    }


# Running `python nlp/extract.py` directly executes this block, which is a
# quick way to eyeball the output. Importing the file does NOT run it.
if __name__ == "__main__":
    # A Thai-locale Windows console defaults to the cp874 codepage and prints
    # Thai text as garbage. Switching stdout to UTF-8 fixes the display. This
    # is a terminal quirk only -- the strings themselves are always fine.
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    sample = "มีไก่กับไข่ อยากกินคลีน ไม่เอาพริก"
    print(f"input : {sample}")
    print(f"output: {extract(sample)}")
