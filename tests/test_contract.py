"""
tests/test_contract.py
======================
Contract tests.

A contract test does not ask "is this answer correct?" It asks "is this answer
the right SHAPE?" — does the dict have the agreed keys, is score really a
number between 0 and 1, is every field a list where a list was promised.

That distinction is why these tests are useful right now, while extract() and
recommend() are still returning hardcoded mock data. The mock values are
meaningless, but the shape is real, and the shape is what Person 1's code will
be written against. If someone later renames "health_tags" to "tags", these
tests fail immediately instead of the bug surfacing in Week 9 when the two
halves of the project are joined.

Run them with:
    pytest -v

pytest finds these automatically by looking for files named test_*.py and,
inside them, functions named test_*. There is nothing to register by hand.
"""

import json
import sys
from pathlib import Path

# Let the tests import from nlp/ and recommender/, which live one level up.
sys.path.insert(0, str(Path(__file__).parent.parent))

from nlp.extract import extract, load_ingredients
from recommender.recommend import recommend

# The 100 ingredients locked in with Person 1. Written out here on purpose:
# if anyone edits ingredients.json without the team agreeing, a test fails and
# says so. YOLO class IDs are baked into the trained model weights, so a
# silent renumbering after training would quietly corrupt every prediction.
#
# THE DICTIONARY HAS TWO TIERS (added Week 3, concern C1; re-locked at 100
# classes when Person 1 expanded the trained model, confirmed against their
# notebook)
# -------------------------------------------------------
# Tier 1 -- DETECTABLE: these 100, with yolo_class_id 0-99. This is the locked
#           agreement, and the tests below still pin it exactly.
# Tier 2 -- TEXT-ONLY: everything with yolo_class_id null. Ingredients a camera
#           will never usefully identify -- fish sauce in a bottle, rice in a
#           bowl, a curry paste in a jar -- but which recipes need and which
#           users type all the time. They reach the system through extract(),
#           never through YOLO.
#
# The second tier was added because the recipe database could not be written
# without it: the project's own worked example, "มีกุ้งกับไข่ อยากกินคลีน
# ไม่เอาหมู" (Claude.md:122), uses an ingredient (egg) that happens to be
# detectable, but health tags and negation always arrive through text only.
#
# Adding a tier does NOT reopen the lock. test_the_detectable_tier_is_still_
# the_agreed_hundred below proves the detectable tier's identity and order on
# every run -- which matters more to Person 1's training than the total count
# of entries in the file ever did.
EXPECTED_INGREDIENTS = [
    "chicken", "pork", "beef", "minced_meat", "sausage",
    "egg", "quail_egg", "shrimp", "fish", "squid",
    "clam", "mussel", "oyster", "crab", "tofu",
    "garlic", "shallot", "onion", "green_onion", "ginger",
    "galangal", "turmeric", "lemongrass", "kaffir_lime_leaf", "chili",
    "basil", "holy_basil", "maenglak", "clove_basil", "mint_leaves",
    "coriander", "chives", "pandan_leaf", "dill", "piper_lolot",
    "celery", "shiitake", "wood_ear", "enoki", "button",
    "king_oyster", "white_oyster", "straw_mushroom", "tomato", "bell_pepper",
    "cabbage", "napa_cabbage", "chinese_kale", "cauliflower", "broccoli",
    "lettuce", "cucumber", "eggplant", "thai_eggplant", "bitter_gourd",
    "bok_choy", "okra", "white_radish", "pumpkin", "chayote",
    "winter_melon", "bottle_gourd", "sponge_gourd", "carrot", "green_bean",
    "yardlong_bean", "winged_bean", "hyacinth_bean", "green_peas", "bamboo_shoots",
    "spinach", "malabar_spinach", "water_spinach", "amaranth", "ivy_gourd",
    "banana_flower", "jicama", "asparagus", "senna_siamea", "soybean_sprouts",
    "moringa", "corn", "potato", "sweet_potato", "cassava",
    "lime", "taro_root", "pineapple", "mango", "green_papaya",
    "tamarind", "banana", "coconut", "lychee", "durian",
    "pomelo", "jackfruit", "rambutan", "cashew", "peanuts",
]


# ---------------------------------------------------------------------------
# ingredients.json — the shared dictionary
# ---------------------------------------------------------------------------

def test_ingredients_file_loads():
    """The file must be valid JSON and must not be empty."""
    data = load_ingredients()
    assert isinstance(data, dict)
    # Not a fixed count: the text-only tier is free to grow as recipes need
    # it, and the detectable tier grew to 100 when Person 1 retrained. What
    # must not change is the detectable tier's identity, pinned two tests below.
    assert len(data) >= 100


def test_the_detectable_tier_is_still_the_agreed_hundred():
    """
    The 100 YOLO classes, in order, unchanged.

    This is the test that actually guards the lock with Person 1, and it is
    stricter than a count of the file's entries: it checks identity and order,
    so renaming "green_onion" or reordering the file fails here even though the
    total would still look right.
    """
    detectable = [k for k, v in load_ingredients().items() if v["yolo_class_id"] is not None]
    assert detectable == EXPECTED_INGREDIENTS


def test_every_ingredient_has_the_required_fields():
    """Each entry needs the five agreed fields, correctly typed."""
    for key, entry in load_ingredients().items():
        # The f-string message only prints when a check fails, and it names the
        # guilty ingredient — much faster to debug than a bare "assert failed".
        assert "name_th" in entry, f"{key} is missing name_th"
        assert "yolo_class_id" in entry, f"{key} is missing yolo_class_id"
        assert "synonyms" in entry, f"{key} is missing synonyms"
        assert "is_seasoning" in entry, f"{key} is missing is_seasoning"
        assert "is_animal_product" in entry, f"{key} is missing is_animal_product"

        assert isinstance(entry["name_th"], str) and entry["name_th"], f"{key}: bad name_th"
        # None is allowed now, and means "YOLO will never detect this one".
        assert entry["yolo_class_id"] is None or isinstance(entry["yolo_class_id"], int), (
            f"{key}: yolo_class_id must be an int or null"
        )
        assert isinstance(entry["synonyms"], list), f"{key}: synonyms must be a list"
        assert len(entry["synonyms"]) > 0, f"{key} has no synonyms"
        assert isinstance(entry["is_seasoning"], bool), f"{key}: is_seasoning must be true/false"
        assert isinstance(entry["is_animal_product"], bool), (
            f"{key}: is_animal_product must be true/false"
        )


def test_yolo_class_ids_are_sequential_from_zero():
    """
    The non-null IDs must be exactly 0-99, no gaps and no duplicates.

    YOLO identifies classes by number, not name. A gap or a repeat means the
    trained model and this dictionary disagree about what class 7 is, and every
    downstream lookup silently returns the wrong ingredient.

    Text-only ingredients are skipped rather than counted: they have no ID
    because they are never predicted, and including their nulls here would
    raise TypeError while sorting instead of reporting anything useful.
    """
    ids = [e["yolo_class_id"] for e in load_ingredients().values() if e["yolo_class_id"] is not None]
    assert sorted(ids) == list(range(100)), f"class IDs are wrong: {sorted(ids)}"


def test_seasonings_are_never_detectable():
    """
    No seasoning may carry a YOLO class ID.

    Two independent reasons, and both matter. Person 1 is not training on
    bottles of fish sauce, so an ID here would point at a class that does not
    exist in the weights. And Claude.md:427 says basic seasonings must not
    affect ingredient matching — everyone has them at home — so a seasoning
    arriving from the detector would skew every recommendation it touched.
    """
    for key, entry in load_ingredients().items():
        if entry["is_seasoning"]:
            assert entry["yolo_class_id"] is None, f"{key} is a seasoning but has a YOLO class ID"


def test_ingredient_names_use_snake_case():
    """Canonical keys must be lowercase ASCII with underscores, e.g. sweet_potato."""
    for key in load_ingredients():
        assert key.islower(), f"{key} is not lowercase"
        assert " " not in key, f"{key} contains a space — use an underscore"
        assert key.replace("_", "").isalpha(), f"{key} has unexpected characters"


def test_ingredient_includes_its_own_thai_name_as_a_synonym():
    """
    name_th must also appear in synonyms.

    Lookup only ever searches the synonym list, so a Thai name that lives only
    in name_th would never actually be matchable.
    """
    for key, entry in load_ingredients().items():
        assert entry["name_th"] in entry["synonyms"], (
            f"{key}: name_th '{entry['name_th']}' is missing from its own synonyms"
        )


def test_no_synonym_is_shared_by_two_ingredients():
    """
    A given synonym may only point at one ingredient.

    If "พริก" mapped to both chili and bell_pepper, which one wins would depend
    on dictionary ordering — the kind of bug that works on your machine and
    fails on your teammate's.
    """
    seen: dict[str, str] = {}  # synonym -> the ingredient that claimed it
    for key, entry in load_ingredients().items():
        for synonym in entry["synonyms"]:
            assert synonym not in seen, (
                f"'{synonym}' is claimed by both '{seen[synonym]}' and '{key}'"
            )
            seen[synonym] = key


def test_file_is_saved_as_utf8():
    """
    The file must be readable as UTF-8.

    Some Windows editors save as TIS-620 or CP874 instead, which turns every
    Thai character into mojibake the moment a teammate on another machine
    opens it.
    """
    path = Path(__file__).parent.parent / "data" / "ingredients.json"
    with open(path, encoding="utf-8") as f:
        json.load(f)  # raises if the encoding or the JSON is wrong


# ---------------------------------------------------------------------------
# extract() — Handoff #2 to Person 1
# ---------------------------------------------------------------------------

def test_extract_returns_the_three_agreed_keys():
    result = extract("มีไก่กับไข่")
    assert isinstance(result, dict)
    assert set(result.keys()) == {"ingredients", "health_tags", "excluded"}


def test_extract_values_are_all_lists_of_strings():
    result = extract("มีไก่กับไข่")
    for key, value in result.items():
        assert isinstance(value, list), f"{key} should be a list"
        assert all(isinstance(item, str) for item in value), f"{key} must hold strings"


def test_extract_survives_empty_and_junk_input():
    """
    Must not crash on rubbish.

    Real users send stickers, single emoji, and blank messages. Returning empty
    lists is a fine answer; raising an exception kills the whole reply.
    """
    for junk in ["", "   ", "?????", "12345", "😀"]:
        result = extract(junk)
        assert set(result.keys()) == {"ingredients", "health_tags", "excluded"}


# ---------------------------------------------------------------------------
# recommend() — the final deliverable of Person 2's side
# ---------------------------------------------------------------------------

def test_recommend_returns_a_list():
    assert isinstance(recommend(["chicken", "egg"]), list)


def test_recommend_respects_top_k():
    """Never return more dishes than asked for. LINE replies must stay short."""
    assert len(recommend(["chicken"], top_k=3)) <= 3
    assert len(recommend(["chicken"], top_k=1)) <= 1


def test_each_recommendation_has_the_required_keys():
    required = {"id", "name_th", "score", "have", "missing", "nutrition"}
    for dish in recommend(["chicken", "garlic"]):
        assert required.issubset(dish.keys()), f"missing keys: {required - dish.keys()}"


def test_score_is_a_number_between_zero_and_one():
    """
    Cosine similarity is defined on 0.0-1.0.

    A score outside that range means the maths is wrong, and since results are
    sorted by score it would also scramble the ranking.
    """
    for dish in recommend(["chicken", "garlic"]):
        score = dish["score"]
        assert isinstance(score, (int, float)), "score must be numeric"
        assert 0.0 <= score <= 1.0, f"score {score} is outside 0.0-1.0"


def test_have_and_missing_are_lists_of_strings():
    for dish in recommend(["chicken", "garlic"]):
        for field in ("have", "missing"):
            assert isinstance(dish[field], list), f"{field} must be a list"
            assert all(isinstance(x, str) for x in dish[field])


def test_nutrition_has_all_four_macros():
    """kcal, protein, fat, carb — all four, all numeric."""
    for dish in recommend(["chicken"]):
        nutrition = dish["nutrition"]
        for macro in ("kcal", "protein", "fat", "carb"):
            assert macro in nutrition, f"nutrition is missing {macro}"
            assert isinstance(nutrition[macro], (int, float)), f"{macro} must be numeric"


def test_results_are_sorted_best_first():
    """The user reads top to bottom, so rank 1 must be the strongest match."""
    scores = [dish["score"] for dish in recommend(["chicken", "garlic", "egg"])]
    assert scores == sorted(scores, reverse=True), f"not sorted: {scores}"


def test_recommend_handles_empty_ingredients():
    """
    An empty ingredient list must return a list, not raise.

    This happens for real whenever YOLO detects nothing in a photo and the user
    sent no text alongside it.
    """
    assert isinstance(recommend([]), list)
