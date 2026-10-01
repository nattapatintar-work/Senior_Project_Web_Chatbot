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


# ---------------------------------------------------------------------------
# Seasoning bonus (Option A): ticked seasonings only ever ADD to a score
# ---------------------------------------------------------------------------

_USER = ["chicken", "garlic"]


def _top_dish_seasonings() -> tuple[dict, list[str]]:
    """The best plain-cosine dish for _USER, plus that recipe's own seasonings."""
    top = recommend(_USER, top_k=1)[0]
    recipe = next(r for r in load_recipes() if r["id"] == top["id"])
    return top, list(recipe["seasonings"])


def test_no_seasonings_argument_is_identical_to_before():
    plain = recommend(_USER, top_k=10)
    assert recommend(_USER, top_k=10, seasonings=None) == plain
    assert "seasonings_matched" not in plain[0]


def test_ticking_a_dishs_seasonings_never_lowers_its_score():
    top, seasonings = _top_dish_seasonings()
    assert seasonings, "test needs a top dish that lists seasonings"
    boosted = next(
        d for d in recommend(_USER, top_k=400, seasonings=seasonings) if d["id"] == top["id"]
    )
    assert boosted["score"] >= top["score"]
    assert boosted["seasonings_matched"] == sorted(seasonings)


def test_a_missing_ticked_seasoning_does_not_drop_the_dish():
    from recommender.recommend import _KNOWN_INGREDIENTS

    top, seasonings = _top_dish_seasonings()
    unused = next(
        key for key, e in _KNOWN_INGREDIENTS.items()
        if e.get("is_seasoning") and key not in seasonings
    )
    ids_with = _ids(recommend(_USER, top_k=400, seasonings=[unused]))
    assert top["id"] in ids_with
    assert ids_with == _ids(recommend(_USER, top_k=400))


def test_non_seasoning_keys_in_seasonings_are_ignored():
    plain = recommend(_USER, top_k=10)
    ignored = recommend(_USER, top_k=10, seasonings=["chicken", "not_a_real_key"])
    assert [(d["id"], d["score"]) for d in ignored] == [(d["id"], d["score"]) for d in plain]


def test_seasonings_alone_still_return_nothing():
    """The bonus never resurrects a dish with zero ingredient cosine."""
    assert recommend([], seasonings=["fish_sauce", "sugar"]) == []
    assert recommend(["fish_sauce"], seasonings=["fish_sauce"]) == []


def test_boosted_score_stays_within_zero_to_one():
    _, seasonings = _top_dish_seasonings()
    for dish in recommend(_USER, top_k=400, seasonings=seasonings):
        assert 0.0 <= dish["score"] <= 1.0


# ---------------------------------------------------------------------------
# Display fields for the web recipe cards (no effect on scoring)
# ---------------------------------------------------------------------------

def test_every_dish_carries_the_recipes_own_display_fields():
    by_id = {r["id"]: r for r in load_recipes()}
    results = recommend(_USER, top_k=50)
    assert results
    for dish in results:
        recipe = by_id[dish["id"]]
        assert dish["cook_time_min"] == recipe["cook_time_min"]
        assert dish["recipe_source_url"] == recipe["recipe_source_url"]
        assert dish["main_ingredients"] == recipe["main_ingredients"]
        assert dish["seasonings"] == recipe["seasonings"]


def test_display_fields_do_not_change_scores_or_ranking():
    plain = recommend(_USER, top_k=10)
    assert [(d["id"], d["score"]) for d in plain] == [
        (d["id"], d["score"]) for d in recommend(_USER, top_k=10, seasonings=None)
    ]


# ---------------------------------------------------------------------------
# Category filter: a condiment is never recommended (EXCLUDED_CATEGORIES)
# ---------------------------------------------------------------------------

import pytest

from recommender import recommend as rec_module

CONDIMENT_IDS = {"th_173", "th_174", "th_221", "th_263"}   # มะนาวดอง, หอมเจียว, น้ำจิ้มผักชี, อาจาด


def _category_by_id() -> dict[str, str]:
    return {recipe["id"]: recipe["category"] for recipe in load_recipes()}


def test_the_four_condiment_recipes_are_labelled_condiment():
    """Guards the data these tests rely on: if a label changes, the tests below stop proving anything."""
    categories = _category_by_id()
    assert {i for i, c in categories.items() if c == "condiment"} == CONDIMENT_IDS


def test_a_condiment_never_appears_even_as_a_perfect_ingredient_match(monkeypatch):
    # th_174 (หอมเจียว) has shallot as its only main ingredient: a perfect match for ["shallot"].
    assert "th_174" not in _ids(recommend(["shallot"], top_k=400))

    # every condiment, queried with exactly its own main ingredients, stays out of the results
    by_id = {recipe["id"]: recipe for recipe in load_recipes()}
    for condiment_id in CONDIMENT_IDS:
        results = recommend(by_id[condiment_id]["main_ingredients"], top_k=400)
        assert not (CONDIMENT_IDS & _ids(results)), condiment_id

    # ...and it is the filter that removes them: switched off, th_174 is returned for the same query
    monkeypatch.setattr(rec_module, "EXCLUDED_CATEGORIES", set())
    assert "th_174" in _ids(recommend(["shallot"], top_k=400))


@pytest.mark.parametrize(
    "recipe_id, category, query",
    [
        ("th_001", "savory", ["egg"]),          # ไข่เจียว
        ("th_049", "dessert", ["banana"]),      # กล้วยบวชชี
        ("th_004", "snack", ["potato"]),        # มันฝรั่งทอด
        ("th_242", "drink", ["lime"]),          # น้ำมะนาว
    ],
)
def test_savory_dessert_snack_and_drink_recipes_still_appear(recipe_id, category, query):
    assert _category_by_id()[recipe_id] == category
    assert recipe_id in _ids(recommend(query, top_k=400))


def test_a_recipe_with_no_category_field_is_not_excluded(monkeypatch):
    recipe = next(r for r in rec_module._RECIPES if r["id"] == "th_174")       # currently a condiment
    assert "th_174" not in _ids(recommend(["shallot"], top_k=400))
    monkeypatch.delitem(recipe, "category")                                      # restored after the test
    assert "category" not in recipe
    assert "th_174" in _ids(recommend(["shallot"], top_k=400))


def test_category_filter_helper_and_constant():
    assert rec_module.EXCLUDED_CATEGORIES == {"condiment"}
    assert rec_module._passes_category_filter({"category": "condiment"}) is False
    for category in ("savory", "dessert", "snack", "drink", None):
        assert rec_module._passes_category_filter({"category": category}) is True
    assert rec_module._passes_category_filter({}) is True


# ---------------------------------------------------------------------------
# Category picker: recommend(category=...) is a hard filter applied before scoring
# ---------------------------------------------------------------------------

PICKER_QUERIES = (["egg"], ["pork"], ["banana"], ["chicken", "egg"], ["potato"], ["lime"], ["pineapple"])


def _categories_of(results: list[dict]) -> set[str]:
    by_id = _category_by_id()
    return {by_id[i] for i in _ids(results)}


def test_savory_mode_returns_only_savory_recipes():
    assert recommend(["pork"], top_k=400, category="savory")          # the filter does not empty a savory query
    for query in PICKER_QUERIES:
        assert _categories_of(recommend(query, top_k=400, category="savory")) <= {"savory"}, query


def test_dessert_mode_returns_only_dessert_recipes():
    assert recommend(["banana"], top_k=400, category="dessert")
    for query in PICKER_QUERIES:
        assert _categories_of(recommend(query, top_k=400, category="dessert")) <= {"dessert"}, query


def test_all_mode_can_return_savory_dessert_snack_and_drink():
    seen = set()
    for query in PICKER_QUERIES:
        seen |= _categories_of(recommend(query, top_k=400, category="all"))
    assert seen == {"savory", "dessert", "snack", "drink"}          # and never condiment


def test_snack_and_drink_recipes_appear_only_in_all_mode():
    assert "th_004" in _ids(recommend(["potato"], top_k=400, category="all"))        # snack
    assert "th_242" in _ids(recommend(["lime"], top_k=400, category="all"))          # drink
    for mode in ("savory", "dessert"):
        assert not ({"th_004", "th_242"} & _ids(recommend(["potato", "lime"], top_k=400, category=mode)))


def test_all_mode_is_the_union_of_savory_dessert_snack_and_drink_results():
    results = {mode: _ids(recommend(["banana"], top_k=400, category=mode)) for mode in ("all", "savory", "dessert")}
    assert results["savory"] | results["dessert"] <= results["all"]
    extra = results["all"] - results["savory"] - results["dessert"]
    assert extra and {_category_by_id()[i] for i in extra} <= {"snack", "drink"}


@pytest.mark.parametrize("category", [None, "all", "savory", "dessert"])
def test_a_condiment_never_appears_in_any_category_mode(category):
    by_id = {recipe["id"]: recipe for recipe in load_recipes()}
    for condiment_id in CONDIMENT_IDS:
        results = recommend(by_id[condiment_id]["main_ingredients"], top_k=400, category=category)
        assert not (CONDIMENT_IDS & _ids(results)), (category, condiment_id)


def test_the_default_is_identical_to_all_and_to_not_passing_the_argument():
    for query in PICKER_QUERIES:
        for top_k in (3, 10):
            base = recommend(query, top_k=top_k)
            assert recommend(query, top_k=top_k, category=None) == base
            assert recommend(query, top_k=top_k, category="all") == base


@pytest.mark.parametrize("bad", ["snack", "drink", "condiment", "SAVORY", " savory", "", "everything"])
def test_an_unknown_category_raises(bad):
    with pytest.raises(ValueError):
        recommend(["egg"], category=bad)


def test_a_recipe_without_a_category_key_matches_all_mode_only(monkeypatch):
    recipe = next(r for r in rec_module._RECIPES if r["id"] == "th_174")       # a condiment today
    monkeypatch.delitem(recipe, "category")
    assert "th_174" in _ids(recommend(["shallot"], top_k=400, category="all"))
    assert "th_174" in _ids(recommend(["shallot"], top_k=400))
    for mode in ("savory", "dessert"):
        assert "th_174" not in _ids(recommend(["shallot"], top_k=400, category=mode))


def test_the_category_filter_runs_before_scoring_so_it_cannot_change_scores():
    everything = {d["id"]: d["score"] for d in recommend(["egg"], top_k=400, category="all")}
    savory = {d["id"]: d["score"] for d in recommend(["egg"], top_k=400, category="savory")}
    assert savory and all(everything[i] == score for i, score in savory.items())
