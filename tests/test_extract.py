"""
tests/test_extract.py
======================
Correctness tests for nlp/extract.py's real implementation.

WHAT THIS IS FOR
----------------
tests/test_contract.py checks that extract() returns the right SHAPE — three
keys, all lists of strings, survives junk input. It does not, and should not,
check whether the *content* is right, because until Week 5 the content was a
hardcoded mock. This file is where content correctness lives.

Kept separate from test_contract.py on purpose: that file is the shared
shape-contract Person 1 codes against (Handoff #2, Claude.md:520-528), and
mixing "does the shape match" with "is the Thai NLP actually correct" would
make it harder to tell, from a failure alone, whether the interface broke or
the matching logic did.

WHY THE COLLISION TESTS COME FIRST
-----------------------------------
concern.md's C4 documents Thai prefix collisions: "พริกหวาน" (bell pepper)
contains "พริก" (chili) as a prefix, so a naive first-match-wins loop over
synonym lists reads it as chili. The fix agreed in concern.md is to sort
synonym candidates by length descending before matching.

But a longer-standing discovery changed *where* that fix has to live.
PyThaiNLP's default tokenizer splits "น้ำมันหอย" (oyster sauce) into
['น้ำมัน', 'หอย'] before any matching logic ever runs — the compound is
destroyed at the tokenization step, not the matching step, so no amount of
sorting synonyms afterward can recover it. The real fix is a custom
pythainlp.util.Trie built from every dictionary synonym, passed as
custom_dict to word_tokenize(), so compounds survive as single tokens. This
file tests the *outcome* (correct ingredient resolved), not the mechanism,
so it stays valid regardless of which internal approach extract.py uses.

Two families of test case, and they are different bugs:

  1. COLLISIONS — one real synonym is a substring of another real synonym
     belonging to a *different* key. Longest-match-first (or, more
     fundamentally, correct tokenization) resolves these deterministically.
  2. SIBLING NON-COLLISIONS — two synonyms that merely *look* similar and
     share a character prefix, but neither is a substring of the other
     (e.g. "มันฝรั่ง" potato / "มันเทศ" sweet potato — both start with "มัน"
     but "มัน" alone is not itself a synonym of either). These are not
     fixable by longest-match; they are a risk for *fuzzy* matching only,
     where a bad similarity threshold could conflate them. concern.md's
     original C4 table listed four of these as if they were collisions —
     they are not, and they need their own test category to prove the
     fuzzy matcher doesn't do the wrong thing either.

Run with:
    pytest tests/test_extract.py -v
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nlp.extract import extract, load_ingredients

DEV_SET_PATH = Path(__file__).parent.parent / "data" / "nlp_dev_set.json"


def load_dev_set() -> list[dict]:
    with open(DEV_SET_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Collisions (C4) — one synonym is a substring of another, different key
# ---------------------------------------------------------------------------
# Each case: (text, ingredient that MUST appear, ingredient that must NOT).
# The "must not" side is the actual bug — it is what a naive matcher gets
# wrong, so a test that only checked the positive side could pass by
# accident (e.g. by matching both "chili" and "bell_pepper").

COLLISION_CASES = [
    # The two cases named explicitly in the Week 5 task.
    ("มีพริกไทยด้วย", "pepper", "chili"),
    ("มีน้ำมันหอยด้วย", "oyster_sauce", "vegetable_oil"),
    # Further pairs from concern.md's C4 tables (Thai).
    # NOTE: the กุ้ง/กุ้งแห้ง (shrimp/dried_shrimp) pair that used to live here
    # was removed -- dried_shrimp was dropped from the 127-entry
    # ingredients.json rebuild, so the collision it tested no longer exists.
    ("มีพริกหวานด้วย", "bell_pepper", "chili"),
    ("มีกะหล่ำดอกด้วย", "cauliflower", "cabbage"),
    ("มีซีอิ๊วดำด้วย", "dark_soy_sauce", "soy_sauce"),
    ("มีข้าวคั่วด้วย", "roasted_rice_powder", "rice"),
    # INFIX collisions: the short synonym sits inside the longer one, not at
    # its start. A pure "prefix" check would miss these.
    ("มีน้ำปลาด้วย", "fish_sauce", "fish"),
    ("มีไข่ไก่ด้วย", "egg", "chicken"),
    # English pairs — concern.md's C4 tables never covered these, but they
    # are the same shape of bug.
    ("I have some eggplant", "eggplant", "egg"),
    ("I have fish sauce", "fish_sauce", "fish"),
    ("I have a rice noodle dish", "rice_noodle", "rice"),
]


def test_collision_pairs_resolve_to_the_longer_correct_ingredient():
    for text, must_have, must_not_have in COLLISION_CASES:
        result = extract(text)
        assert must_have in result["ingredients"], (
            f"{text!r}: expected {must_have!r} in {result['ingredients']}"
        )
        assert must_not_have not in result["ingredients"], (
            f"{text!r}: {must_not_have!r} should not appear "
            f"(this is the collision C4 warns about) — got {result['ingredients']}"
        )


# ---------------------------------------------------------------------------
# The one C4 case that is a correctness trap, not just a ranking bug
# ---------------------------------------------------------------------------

def test_oyster_sauce_never_falls_back_to_plain_oil():
    """
    concern.md is explicit that this pair is the one that actually hurts:
    a dish seasoned with oyster sauce is not vegan, but if the matcher
    records plain vegetable_oil instead, a vegan filter downstream would
    wrongly let it through. This is a correctness bug wearing a ranking
    bug's clothes, so it gets its own named test in addition to living in
    COLLISION_CASES above.
    """
    result = extract("ใส่น้ำมันหอยด้วย")
    assert "oyster_sauce" in result["ingredients"]
    assert "vegetable_oil" not in result["ingredients"]


# ---------------------------------------------------------------------------
# Sibling non-collisions — similar-looking synonyms that are NOT substrings
# of each other. Longest-match cannot break these; only a loose fuzzy
# threshold could.
# ---------------------------------------------------------------------------

SIBLING_CASES = [
    ("มีมันเทศด้วย", "sweet_potato", "potato"),
    ("มีมันฝรั่งด้วย", "potato", "sweet_potato"),
    ("มีต้นหอมด้วย", "green_onion", "onion"),
    ("มีหอมใหญ่ด้วย", "onion", "green_onion"),
    ("มีมะเขือเทศด้วย", "tomato", "eggplant"),
    ("มีมะเขือยาวด้วย", "eggplant", "tomato"),
    ("มีถั่วลิสงด้วย", "peanuts", "soybean_sprouts"),
    ("มีถั่วงอกหัวโตด้วย", "soybean_sprouts", "peanuts"),
]


def test_similar_looking_siblings_do_not_get_confused():
    for text, must_have, must_not_have in SIBLING_CASES:
        result = extract(text)
        assert must_have in result["ingredients"], (
            f"{text!r}: expected {must_have!r} in {result['ingredients']}"
        )
        assert must_not_have not in result["ingredients"], (
            f"{text!r}: {must_not_have!r} should not appear — these are "
            f"look-alike siblings, not real collisions, per concern.md C4"
        )


# ---------------------------------------------------------------------------
# Negation
# ---------------------------------------------------------------------------

def test_negation_moves_an_ingredient_to_excluded():
    result = extract("มีกุ้งกับไข่ อยากกินคลีน ไม่เอาหมู")
    assert "pork" in result["excluded"]
    assert "pork" not in result["ingredients"]


def test_negated_ingredient_never_appears_in_both_lists():
    """
    A key must never be in both ingredients and excluded at once — that
    would be a contradiction the recommender has no sane way to apply.
    """
    for text in ["ไม่เอาหมู", "มีกุ้งกับไข่ ไม่เอาพริก", "ไม่ใส่น้ำมันหอย"]:
        result = extract(text)
        overlap = set(result["ingredients"]) & set(result["excluded"])
        assert not overlap, f"{text!r}: {overlap} appears in both lists"


def test_multiple_negation_phrasings_are_recognised():
    """ไม่เอา / ไม่ใส่ / ไม่มี — three ways Thai speakers say "leave it out"."""
    assert "pork" in extract("ไม่เอาหมู")["excluded"]
    assert "oyster_sauce" in extract("ไม่ใส่น้ำมันหอย")["excluded"]
    assert "shrimp" in extract("ไม่มีกุ้ง")["excluded"]


# ---------------------------------------------------------------------------
# Health tags
# ---------------------------------------------------------------------------

def test_clean_tag_is_detected_despite_the_tokenizer_splitting_it_by_default():
    """
    PyThaiNLP's default tokenizer splits "คลีน" into ['คลี', 'น'] — confirmed
    by direct testing during planning. The project's own canonical worked
    example ("...อยากกินคลีน...", Claude.md:122) would silently fail to
    detect its own health tag under the default tokenizer. This is the
    single most load-bearing test in this file for that reason.
    """
    result = extract("อยากกินคลีน")
    assert "clean" in result["health_tags"]


def test_keto_and_vegan_tags_are_detected():
    assert "keto" in extract("อยากกินคีโต")["health_tags"]
    assert "vegan" in extract("อยากกินวีแกน")["health_tags"]


def test_vegetarian_tag_is_detected():
    assert "vegetarian" in extract("กินมังสวิรัติ")["health_tags"]


def test_je_maps_to_vegan_only_inside_the_real_phrase():
    """
    Per project decision: เจ (Thai Buddhist vegan-adjacent fasting diet)
    maps to our 'vegan' tag, since it excludes all animal products
    including fish sauce, same as our definition. It must only fire inside
    "กินเจ" / "อาหารเจ" — "เจ" alone is a substring of "เจอ" ("to meet/find")
    and "เจ็ด" ("seven"), and firing on those would be a false positive on
    ordinary sentences that have nothing to do with diet.
    """
    assert "vegan" in extract("กินเจ")["health_tags"]
    assert "vegan" in extract("อยากกินอาหารเจ")["health_tags"]
    # Must NOT fire on unrelated words containing "เจ" as a substring.
    result = extract("เจอกันพรุ่งนี้")  # "see you tomorrow" — no food content
    assert "vegan" not in result["health_tags"]


# ---------------------------------------------------------------------------
# Fuzzy matching — typo tolerance, and its documented limit
# ---------------------------------------------------------------------------

def test_an_english_typo_still_resolves():
    """
    rapidfuzz exists for this: "chiken" scores 92% against "chicken" and
    should resolve, not be dropped. Verified during planning that this
    works reliably for English typos specifically — see the next test for
    why the equivalent Thai case is a documented limitation, not a bug.
    """
    result = extract("I have chiken and egg")
    assert "chicken" in result["ingredients"]
    assert "egg" in result["ingredients"]


def test_thai_typo_recovery_is_a_known_gap_not_a_silent_wrong_answer():
    """
    A misspelled Thai ingredient is usually not in the custom dictionary, so
    the tokenizer shatters it into syllable fragments before rapidfuzz ever
    sees it — confirmed during planning: "มะเขือเทดด้วย" (typo of
    มะเขือเทศ, tomato) tokenizes to ['มี', 'มะเขือ', 'เท', 'ด', 'ด้วย'], and
    the surviving "มะเขือ" fragment scores only 80% against "มะเขือเทศ" —
    below this module's 85 cutoff.

    The point of this test is not that the typo goes unrecovered — it's
    that failing to recover it must never mean silently returning the
    WRONG ingredient instead of no ingredient. A lower cutoff was tried
    during planning and rejected for exactly this reason: at 60%, "กระ"
    starts matching "กระเพรา" by accident. Missing a typo is an acceptable,
    documented gap (nlp/extract.py's module docstring); inventing a wrong
    ingredient from an unrelated short token is not.
    """
    result = extract("มีมะเขือเทดด้วย")
    assert "tomato" not in result["ingredients"], (
        "a fuzzy cutoff loose enough to recover this typo would also "
        "start matching unrelated short tokens — see the module docstring"
    )
    assert result["ingredients"] == []


# ---------------------------------------------------------------------------
# Frozen shape (belt-and-braces alongside test_contract.py)
# ---------------------------------------------------------------------------

def test_extract_still_returns_only_the_three_agreed_keys():
    result = extract("มีไก่กับไข่ อยากกินคลีน ไม่เอาหมู")
    assert set(result.keys()) == {"ingredients", "health_tags", "excluded"}


def test_extract_survives_input_with_no_recognisable_ingredients():
    for junk in ["", "   ", "?????", "12345", "😀", "asdkjhaskjdh"]:
        result = extract(junk)
        assert result["ingredients"] == []
        assert result["health_tags"] == []
        assert result["excluded"] == []


def test_every_returned_ingredient_key_is_a_real_dictionary_key():
    """
    extract() must only ever emit canonical keys that exist in
    ingredients.json — never a raw Thai/English string. This is the
    guarantee the recommender depends on.
    """
    known = set(load_ingredients())
    for text in ["มีไก่กับไข่", "มีกุ้งกับไข่ อยากกินคลีน ไม่เอาหมู", "มีพริกไทยกับกุ้งแห้ง"]:
        result = extract(text)
        for key in result["ingredients"] + result["excluded"]:
            assert key in known, f"{text!r}: {key!r} is not a real ingredients.json key"


# ---------------------------------------------------------------------------
# Dev set — measured accuracy floor
# ---------------------------------------------------------------------------
# This is MY dev set (Claude.md:444: "no need to send this to anyone yet,
# tune freely"). Person 1's test set is never touched here.

def test_dev_set_meets_the_accuracy_floor():
    """
    Every dev-set sentence must resolve exactly right: same ingredients,
    same health tags, same exclusions, order-independent. The floor is
    100% because the dev set was written to be solvable — every sentence
    in it targets one specific, already-diagnosed behaviour (a collision
    pair, a negation phrasing, a health tag, a typo). A miss here means a
    real regression, not an unreasonably strict bar.
    """
    dev_set = load_dev_set()
    assert len(dev_set) >= 20, f"dev set has only {len(dev_set)} sentences, want >= 20"

    failures = []
    for case in dev_set:
        result = extract(case["text"])
        for field in ("ingredients", "health_tags", "excluded"):
            if set(result[field]) != set(case[field]):
                failures.append(
                    f"{case['text']!r} [{case.get('why', '?')}]: "
                    f"{field} expected {case[field]}, got {result[field]}"
                )

    assert not failures, "dev set failures:\n" + "\n".join(failures)
