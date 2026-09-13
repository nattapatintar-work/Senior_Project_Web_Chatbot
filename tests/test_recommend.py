"""
tests/test_recommend.py
========================
Correctness tests for recommender/recommend.py -- the real Week 7 logic, not
the shape checks in tests/test_contract.py.

Same split as tests/test_extract.py vs tests/test_contract.py: contract tests
pin the interface everyone else builds against, this file pins the behaviour.

Run with:
    pytest tests/test_recommend.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from recommender.recommend import load_recipes, recommend


def _ids(results: list[dict]) -> set[str]:
    return {dish["id"] for dish in results}


# ---------------------------------------------------------------------------
# Seasonings never influence matching (Claude.md:427)
# ---------------------------------------------------------------------------

def test_seasoning_only_input_returns_nothing():
    """
    Once seasonings are stripped from the user's own ingredients, a
    seasoning-only request has nothing left to score against.
    """
    assert recommend(["fish_sauce"]) == []
    assert recommend(["sugar", "salt"]) == []


def test_typing_a_seasoning_does_not_change_the_ranking():
    """
    Adding a seasoning the user already has (fish_sauce is in almost every
    seasonings list) must not move a dish up or down -- it's stripped before
    the vector is built.
    """
    without = recommend(["chicken", "garlic"])
    with_seasoning = recommend(["chicken", "garlic", "fish_sauce"])
    assert [d["id"] for d in without] == [d["id"] for d in with_seasoning]
    assert [d["score"] for d in without] == [d["score"] for d in with_seasoning]


def test_no_seasoning_ever_appears_in_have_or_missing():
    """have/missing describe main+optional ingredients only."""
    known = {r["id"]: r for r in load_recipes()}
    seasonings = {
        s for r in load_recipes() for s in r["seasonings"]
    }
    for dish in recommend(["chicken", "garlic", "fish_sauce", "sugar"]):
        assert not (set(dish["have"]) & seasonings)
        assert not (set(dish["missing"]) & seasonings)


# ---------------------------------------------------------------------------
# Excluded-ingredient scope: main/seasoning drops the dish, optional does not
# ---------------------------------------------------------------------------

def test_excluding_a_main_ingredient_drops_every_dish_that_needs_it():
    known = {r["id"]: r for r in load_recipes()}
    pork_dishes = {r["id"] for r in load_recipes() if "pork" in r["main_ingredients"]}
    assert pork_dishes, "fixture assumption: at least one recipe has pork as a main"

    results = recommend(["pork", "eggplant"], excluded=["pork"])
    assert not (_ids(results) & pork_dishes)


def test_excluding_an_optional_ingredient_keeps_the_dish():
    """
    th_001 (ไข่เจียว) has green_onion only as optional_ingredients. Excluding
    it must not remove the dish from consideration -- it's omittable.

    top_k is set high on purpose: the dessert expansion added several other
    pure egg+sugar dishes (th_096, th_108) that legitimately tie th_001's
    score for a bare "egg" query, so th_001 can fall outside a small top_k
    on ranking alone -- that's the recommender working correctly, not a
    bug. This test only cares whether th_001 stays in the result set and
    whether its "have" is computed correctly once it's there.
    """
    results = recommend(["egg"], excluded=["green_onion"], top_k=len(load_recipes()))
    assert "th_001" in _ids(results)
    # And green_onion, which the user doesn't have anyway, is not falsely
    # reported as something they have.
    dish = next(d for d in results if d["id"] == "th_001")
    assert "green_onion" not in dish["have"]


# ---------------------------------------------------------------------------
# Health-tag filter: AND across tags, opposite-of excluded_for
# ---------------------------------------------------------------------------

def test_health_tags_are_ANDed_not_ORed():
    """
    A recipe must satisfy every requested tag, not just one of them.

    th_004 (มันฝรั่งทอด) is tagged vegan but not keto -- potato is a starch
    staple, which HEALTH_TAGS.md's keto rule disqualifies regardless of the
    carb arithmetic. Requesting vegan alone must surface it; requesting
    vegan+keto together must not. If the filter were OR instead of AND,
    it would wrongly survive the second query too.
    """
    recipe = next(r for r in load_recipes() if r["id"] == "th_004")
    assert "vegan" in recipe["health_tags"] and "keto" not in recipe["health_tags"], (
        "fixture assumption: th_004 is vegan but not keto"
    )

    vegan_only = recommend(recipe["main_ingredients"], health_tags=["vegan"])
    assert "th_004" in _ids(vegan_only)

    vegan_and_keto = recommend(recipe["main_ingredients"], health_tags=["vegan", "keto"])
    assert "th_004" not in _ids(vegan_and_keto)


def test_vegan_filter_excludes_animal_product_seasonings():
    """
    The HEALTH_TAGS.md trap: fish sauce is an animal product. A dish
    containing it must never be returned under a vegan filter, even if the
    user's own ingredient list also mentions fish_sauce (which gets stripped
    as a seasoning before scoring, so it can't accidentally boost anything).
    """
    known = {r["id"]: r for r in load_recipes()}
    fish_sauce_dishes = {
        r["id"] for r in load_recipes() if "fish_sauce" in r["seasonings"]
    }
    results = recommend(["spinach", "garlic", "fish_sauce"], health_tags=["vegan"])
    assert not (_ids(results) & fish_sauce_dishes)


def test_excluded_for_blocks_a_recipe_from_its_own_excluded_tags():
    """
    Querying with a tag a recipe is excluded_for must never surface that
    recipe, even when the ingredients are an exact match for its own list.

    Restricted to recipes with a non-empty excluded_for -- querying with
    health_tags=[] applies no filter at all, so it would trivially pass for
    every recipe and prove nothing.
    """
    recipes_with_exclusion = [r for r in load_recipes() if r["excluded_for"]]
    assert recipes_with_exclusion, "fixture assumption: some recipe has excluded_for set"

    for recipe in recipes_with_exclusion:
        results = recommend(recipe["main_ingredients"], health_tags=recipe["excluded_for"])
        assert recipe["id"] not in _ids(results), (
            f"{recipe['id']} was returned under {recipe['excluded_for']}, "
            f"which it's excluded_for"
        )


# ---------------------------------------------------------------------------
# missing vs have
# ---------------------------------------------------------------------------

def test_missing_only_lists_main_ingredients_never_optional():
    """
    A missing OPTIONAL ingredient is not something the user needs to buy --
    it's flavour, not a requirement. Only main_ingredients belong in missing.
    """
    known_optionals = {
        (r["id"], o) for r in load_recipes() for o in r["optional_ingredients"]
    }
    for dish in recommend(["chicken"]):
        for missing_key in dish["missing"]:
            assert (dish["id"], missing_key) not in known_optionals


def test_have_is_the_intersection_of_user_ingredients_and_the_dish():
    """
    th_001 (ไข่เจียว) has no carrot at all, so "have" must exclude it.

    top_k is set high here on purpose: with 84 recipes now in the database,
    dishes that genuinely score higher for "egg, carrot" (e.g. ไข่ตุ๋น, which
    lists carrot as optional) legitimately outrank th_001 -- that is the
    recommender working correctly, not a bug. This test only cares whether
    the "have" field is computed as the right intersection once th_001 is in
    the result set, not whether it ranks in the top few.
    """
    recipe = next(r for r in load_recipes() if r["id"] == "th_001")  # ไข่เจียว
    results = recommend(["egg", "carrot"], top_k=len(load_recipes()))  # carrot isn't in th_001 at all
    dish = next(d for d in results if d["id"] == "th_001")
    assert dish["have"] == ["egg"]
    assert "carrot" not in dish["have"]


# ---------------------------------------------------------------------------
# General robustness -- mirrors test_contract.py's shape checks with real data
# ---------------------------------------------------------------------------

def test_empty_ingredients_returns_empty_list_not_an_error():
    assert recommend([]) == []


def test_unknown_ingredient_does_not_crash():
    """
    A key that isn't in ingredients.json at all (e.g. a future YOLO class not
    yet wired into the dictionary) must not blow up the vectorizer.
    """
    results = recommend(["chicken", "some_totally_unrecognised_key"])
    assert isinstance(results, list)


def test_scores_are_sorted_and_in_range():
    results = recommend(["chicken", "garlic", "egg", "onion"])
    scores = [d["score"] for d in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_health_tags_field_is_passed_through_for_week_8s_template():
    """
    C15 (concern.md): the keto/rice qualification is deferred to Week 8's
    format_reply(), which needs the recipe's health_tags to decide when to
    add "(ไม่รวมข้าว)". recommend() must not silently drop this field.
    """
    for dish in recommend(["chicken", "garlic"]):
        assert "health_tags" in dish
        assert isinstance(dish["health_tags"], list)


# ---------------------------------------------------------------------------
# End-to-end: extract() -> recommend(), pinning Claude.md:122's own example
# ---------------------------------------------------------------------------

def test_extract_then_recommend_end_to_end():
    from nlp.extract import extract

    parsed = extract("มีกุ้งกับไข่ อยากกินคลีน ไม่เอาหมู")
    assert parsed == {
        "ingredients": ["shrimp", "egg"],
        "health_tags": ["clean"],
        "excluded": ["pork"],
    }

    results = recommend(
        ingredients=parsed["ingredients"],
        health_tags=parsed["health_tags"],
        excluded=parsed["excluded"],
    )
    pork_dishes = {r["id"] for r in load_recipes() if "pork" in r["main_ingredients"]}
    assert not (_ids(results) & pork_dishes)
    assert isinstance(results, list)
