"""
tests/test_recipes.py
=====================
Validation for data/recipes.json, the 40-dish database.

WHAT THIS IS FOR
----------------
tests/test_contract.py checks that functions return the right SHAPE. This file
checks that the recipe data is internally CONSISTENT — which is a different and,
for hand-entered data, more valuable thing.

Forty recipes entered by hand over two weeks is exactly the situation where a
typo survives: "chiken" in one ingredient list, a vegan tag on a dish seasoned
with fish sauce, a nutrition block quietly left at zero. None of those crash.
They just make the recommender wrong in ways nobody notices until the
evaluation, when it is far too late to re-enter the data.

So the rule here is that every recipe must be checkable against something else:
against the dictionary, against the health tag definitions, or against the
recorded source. Nothing is taken on trust.

Run with:
    pytest tests/test_recipes.py -v
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nlp.extract import load_ingredients

RECIPES_PATH = Path(__file__).parent.parent / "data" / "recipes.json"

# The only four values allowed in health_tags and excluded_for.
# Defined in data/HEALTH_TAGS.md, which explains how each is decided.
VALID_TAGS = {"clean", "keto", "vegetarian", "vegan"}

# Fields every recipe must carry, with the type each must have.
REQUIRED_FIELDS = {
    "id": str,
    "name_th": str,
    "main_ingredients": list,
    "optional_ingredients": list,
    "seasonings": list,
    "health_tags": list,
    "excluded_for": list,
    "serving_g": (int, float),
    "nutrition": dict,
    "nutrition_source": str,
    "nutrition_method": str,
    "cook_time_min": (int, float),
    "recipe_source_url": str,
}

MACROS = ("kcal", "protein", "fat", "carb")

# The carbohydrate ceiling for a keto dish, per serving. See data/HEALTH_TAGS.md
# for why 10 g and not some other number.
KETO_CARB_LIMIT = 10

# Staples that disqualify a dish from keto regardless of the arithmetic.
STARCH_STAPLES = {
    "rice", "rice_noodle", "glass_noodle", "egg_noodle", "spaghetti",
    "potato", "sweet_potato",
}


def load_recipes() -> list[dict]:
    with open(RECIPES_PATH, encoding="utf-8") as f:
        return json.load(f)


def all_ingredients_of(recipe: dict) -> list[str]:
    """Every ingredient key a recipe references, across all three lists."""
    return [
        key
        for field in ("main_ingredients", "optional_ingredients", "seasonings")
        for key in recipe[field]
    ]


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_recipes_file_loads_as_utf8_json():
    """
    Must be valid JSON and readable as UTF-8.

    Same reasoning as the ingredients file: a Windows editor that saves as
    CP874 turns every Thai dish name into mojibake on a teammate's machine.
    """
    recipes = load_recipes()
    assert isinstance(recipes, list)


def test_there_are_at_least_seventy_recipes():
    """
    Floor of 70, not a fixed count.

    The original Claude.md target was 40, sized against a 20-class detectable
    tier. Once the dictionary grew to 127 ingredients, 40 recipes could no
    longer exercise it -- most of the new vocabulary would sit unused. The
    floor is a lower bound so the database can keep growing without breaking
    this test; it does not need tightening back to an exact number.
    """
    assert len(load_recipes()) >= 70


def test_recipe_ids_are_unique():
    """
    IDs are how a recommendation points back at a dish.

    A duplicate means two different dishes answer to the same id, and which one
    the user sees depends on iteration order.
    """
    ids = [r["id"] for r in load_recipes()]
    assert len(ids) == len(set(ids)), f"duplicate ids: {[i for i in ids if ids.count(i) > 1]}"


def test_every_recipe_has_the_required_fields():
    for recipe in load_recipes():
        for field, expected_type in REQUIRED_FIELDS.items():
            assert field in recipe, f"{recipe.get('id', '?')} is missing {field}"
            assert isinstance(recipe[field], expected_type), (
                f"{recipe['id']}: {field} should be {expected_type}"
            )


def test_every_recipe_has_a_name_and_at_least_one_main_ingredient():
    """A dish with no main ingredients can never be matched by anything."""
    for recipe in load_recipes():
        assert recipe["name_th"].strip(), f"{recipe['id']} has an empty name"
        assert recipe["main_ingredients"], f"{recipe['id']} has no main ingredients"


# ---------------------------------------------------------------------------
# Consistency with the ingredient dictionary — the most valuable check here
# ---------------------------------------------------------------------------

def test_every_ingredient_resolves_against_the_dictionary():
    """
    No free-text ingredient names, ever.

    This is the check that catches typos automatically. A recipe listing
    "chiken" or "holy basil" instead of "holy_basil" is invisible at a glance
    and silently unmatchable at runtime — the recommender simply never scores
    it. Exactly the failure that produced concern C1.
    """
    known = load_ingredients()
    for recipe in load_recipes():
        for key in all_ingredients_of(recipe):
            assert key in known, f"{recipe['id']}: '{key}' is not in ingredients.json"


def test_seasonings_are_flagged_as_seasonings():
    """
    The seasonings list holds only things marked is_seasoning.

    Claude.md:427 says basic seasonings must not count toward matching, because
    everyone has them at home. That only works if the split is honest — putting
    chicken in `seasonings` would quietly delete it from the matching.
    """
    known = load_ingredients()
    for recipe in load_recipes():
        for key in recipe["seasonings"]:
            assert known[key]["is_seasoning"], f"{recipe['id']}: '{key}' is not a seasoning"


def test_main_ingredients_are_never_seasonings():
    """The other half of the same rule, in the other direction."""
    known = load_ingredients()
    for recipe in load_recipes():
        for key in recipe["main_ingredients"]:
            assert not known[key]["is_seasoning"], (
                f"{recipe['id']}: '{key}' is a seasoning and cannot be a main ingredient"
            )


def test_no_ingredient_is_listed_twice_in_one_recipe():
    """
    An ingredient belongs in exactly one of the three lists.

    Listing it in both main and optional would double its weight in the TF-IDF
    vector in Week 7, quietly skewing that dish's score upward.
    """
    for recipe in load_recipes():
        keys = all_ingredients_of(recipe)
        assert len(keys) == len(set(keys)), (
            f"{recipe['id']}: repeated ingredient {[k for k in keys if keys.count(k) > 1]}"
        )


# ---------------------------------------------------------------------------
# Nutrition
# ---------------------------------------------------------------------------

def test_nutrition_has_all_four_macros_as_real_numbers():
    """
    All four present, numeric, non-negative, and kcal actually positive.

    A zero kcal dish means the value was never filled in. Because nothing
    crashes, it would sail through into the nutrition experiment.
    """
    for recipe in load_recipes():
        nutrition = recipe["nutrition"]
        for macro in MACROS:
            assert macro in nutrition, f"{recipe['id']}: nutrition missing {macro}"
            assert isinstance(nutrition[macro], (int, float)), (
                f"{recipe['id']}: {macro} must be numeric, not {type(nutrition[macro])}"
            )
            assert nutrition[macro] >= 0, f"{recipe['id']}: {macro} is negative"
        assert nutrition["kcal"] > 0, f"{recipe['id']}: kcal is 0 — was it ever filled in?"


def test_every_recipe_cites_its_source():
    """
    Claude.md:430 — estimated nutrition invalidates the nutrition experiment.

    An empty nutrition_source is the signature of a number someone made up, so
    it is worth failing loudly over.
    """
    for recipe in load_recipes():
        assert recipe["nutrition_source"].strip(), f"{recipe['id']} has no nutrition_source"
        assert "Thai FCD" in recipe["nutrition_source"], (
            f"{recipe['id']}: unexpected source '{recipe['nutrition_source']}'"
        )


def test_every_recipe_cites_where_its_ingredient_list_came_from():
    """
    recipe_source_url is separate from nutrition_source on purpose.

    nutrition_source answers "where did the macros come from" (always Thai
    FCD, or Thai FCD plus a declared exception like USDA for broccoli).
    recipe_source_url answers a different question: "where did the dish's
    ingredient list and method come from". Conflating the two would make it
    impossible to tell a nutrition citation from a recipe citation at a glance.
    """
    for recipe in load_recipes():
        url = recipe["recipe_source_url"].strip()
        assert url, f"{recipe['id']} has no recipe_source_url"
        assert url.startswith("http"), f"{recipe['id']}: recipe_source_url '{url}' is not a URL"


def test_every_recipe_has_a_valid_dessert_or_savory_category():
    """
    category distinguishes dessert dishes from savory ones -- added after a
    session where the only way to answer "how many desserts are there" was
    to hand-count recipe ID ranges from build logs, which isn't a real,
    checkable field and would silently go stale the next time a recipe is
    added without updating that manual tracking.
    """
    for recipe in load_recipes():
        assert "category" in recipe, f"{recipe['id']} has no category"
        assert recipe["category"] in ("dessert", "savory"), (
            f"{recipe['id']}: category '{recipe['category']}' is not 'dessert' or 'savory'"
        )


def test_nutrition_method_is_declared_and_computed_recipes_show_their_working():
    """
    Every recipe says how its numbers were derived, and computed ones prove it.

    'direct' means the database had the whole dish. 'computed' means it was
    summed from per-ingredient values using gram amounts chosen by us — an
    assumption, and one a reader is entitled to inspect. See
    data/NUTRITION_SOURCE.md.
    """
    known = load_ingredients()
    for recipe in load_recipes():
        method = recipe["nutrition_method"]
        assert method in ("direct", "computed"), f"{recipe['id']}: bad method '{method}'"

        if method == "computed":
            basis = recipe.get("nutrition_basis")
            assert isinstance(basis, dict) and basis, (
                f"{recipe['id']} is computed but has no nutrition_basis"
            )
            for key, grams in basis.items():
                assert key in known, f"{recipe['id']}: nutrition_basis has unknown '{key}'"
                assert isinstance(grams, (int, float)) and grams > 0, (
                    f"{recipe['id']}: nutrition_basis['{key}'] must be a positive weight"
                )


def test_serving_size_is_plausible():
    """
    A serving between 50 g and 800 g.

    Nutrition is stored per serving but sourced per 100 g, so serving_g is the
    multiplier. A wrong one scales all four macros together, which makes the
    error hard to spot by eye — every number stays in a believable ratio.
    """
    for recipe in load_recipes():
        assert 50 <= recipe["serving_g"] <= 800, (
            f"{recipe['id']}: serving_g {recipe['serving_g']} looks wrong"
        )


# ---------------------------------------------------------------------------
# Health tags — see data/HEALTH_TAGS.md
# ---------------------------------------------------------------------------

def test_tags_come_from_the_agreed_four():
    for recipe in load_recipes():
        for field in ("health_tags", "excluded_for"):
            unknown = set(recipe[field]) - VALID_TAGS
            assert not unknown, f"{recipe['id']}: unknown {field} {unknown}"


def test_a_tag_is_never_both_claimed_and_excluded():
    """A dish cannot both suit a diet and be forbidden to it."""
    for recipe in load_recipes():
        both = set(recipe["health_tags"]) & set(recipe["excluded_for"])
        assert not both, f"{recipe['id']}: {both} in both health_tags and excluded_for"


def test_animal_products_exclude_vegan():
    """
    THE trap Claude.md:429 warns about.

    Fish sauce, oyster sauce, and shrimp paste are animal products, and a
    vegetable stir-fry seasoned with น้ำปลา looks vegan at a glance — no meat
    appears anywhere in the ingredient list. Same for egg and dairy.

    Derived from is_animal_product in the dictionary rather than a list kept
    here, so the rule cannot drift away from the data.
    """
    known = load_ingredients()
    for recipe in load_recipes():
        offenders = [k for k in all_ingredients_of(recipe) if known[k]["is_animal_product"]]
        if offenders:
            assert "vegan" in recipe["excluded_for"], (
                f"{recipe['id']} contains animal products {offenders} "
                f"but is not excluded_for vegan"
            )


def test_no_animal_products_means_vegan_is_not_excluded():
    """
    The reverse direction of test_animal_products_exclude_vegan.

    A dish with zero animal-derived ingredients has no reason to exclude
    vegan, and excluding it anyway is a real bug -- it happened twice during
    the dessert expansion (a build script's default excluded_for list was
    copy-pasted onto fully plant-based recipes without checking each one).
    Neither existing vegan/vegetarian test caught it: the forward tests only
    assert "has animal ingredients -> must exclude", never "has none ->
    must not exclude", and a bare exclusion with no matching health_tags
    claim doesn't trip test_a_tag_is_never_both_claimed_and_excluded either.
    This closes that gap. (Not tagging vegan when eligible is fine --
    HEALTH_TAGS.md says most dishes claim neither tag -- only wrongly
    excluding it is the bug this guards against.)
    """
    known = load_ingredients()
    for recipe in load_recipes():
        offenders = [k for k in all_ingredients_of(recipe) if known[k]["is_animal_product"]]
        if not offenders:
            assert "vegan" not in recipe["excluded_for"], (
                f"{recipe['id']} has no animal-derived ingredients but excludes vegan anyway"
            )


def test_meat_and_seafood_exclude_vegetarian():
    """
    Vegetarian allows egg and dairy, so this cannot reuse is_animal_product.

    The distinction is meat, fish, and seafood — including the seasonings made
    from them, which is where fish sauce and shrimp paste catch people out.
    """
    known = load_ingredients()
    # Derived from is_animal_product rather than hand-listed: a hardcoded set
    # goes stale the moment the dictionary changes (this is exactly what broke
    # when the 127-entry rebuild added clam/mussel/oyster/crab/sausage/the
    # curry pastes as is_animal_product:true, and dropped dried_shrimp
    # entirely). Eggs and dairy are vegetarian-safe per HEALTH_TAGS.md, so they
    # are the only animal products carved back out.
    VEGETARIAN_OK_ANIMAL = {"egg", "quail_egg", "milk", "butter", "mayonnaise", "egg_noodle"}
    flesh = {k for k, v in known.items() if v["is_animal_product"]} - VEGETARIAN_OK_ANIMAL

    for recipe in load_recipes():
        offenders = [k for k in all_ingredients_of(recipe) if k in flesh]
        if offenders:
            assert "vegetarian" in recipe["excluded_for"], (
                f"{recipe['id']} contains {offenders} but is not excluded_for vegetarian"
            )


def test_no_flesh_means_vegetarian_is_not_excluded():
    """
    The reverse direction of test_meat_and_seafood_exclude_vegetarian --
    same rationale as test_no_animal_products_means_vegan_is_not_excluded
    above, applied to the vegetarian tag instead of vegan.
    """
    known = load_ingredients()
    VEGETARIAN_OK_ANIMAL = {"egg", "quail_egg", "milk", "butter", "mayonnaise", "egg_noodle"}
    flesh = {k for k, v in known.items() if v["is_animal_product"]} - VEGETARIAN_OK_ANIMAL

    for recipe in load_recipes():
        offenders = [k for k in all_ingredients_of(recipe) if k in flesh]
        if not offenders:
            assert "vegetarian" not in recipe["excluded_for"], (
                f"{recipe['id']} has no meat/fish/seafood ingredients but excludes vegetarian anyway"
            )


def test_vegetarian_exclusion_implies_vegan_exclusion():
    """Anything unfit for vegetarians is necessarily unfit for vegans."""
    for recipe in load_recipes():
        if "vegetarian" in recipe["excluded_for"]:
            assert "vegan" in recipe["excluded_for"], (
                f"{recipe['id']} excludes vegetarian but not vegan"
            )


def test_keto_dishes_are_actually_low_carb():
    """Both halves of the keto rule, checked against the recipe's own data."""
    for recipe in load_recipes():
        if "keto" not in recipe["health_tags"]:
            continue
        assert recipe["nutrition"]["carb"] <= KETO_CARB_LIMIT, (
            f"{recipe['id']} is tagged keto but has {recipe['nutrition']['carb']} g carb"
        )
        staples = set(recipe["main_ingredients"]) & STARCH_STAPLES
        assert not staples, f"{recipe['id']} is tagged keto but is built on {staples}"


def test_clean_dishes_have_no_sugar_or_coconut_milk():
    """
    Two of the four clean rules, the ones checkable from the ingredient lists.

    "Not deep-fried" and "no processed meat" are not mechanically checkable
    from this schema — they stay a human judgement, applied per
    data/HEALTH_TAGS.md.
    """
    for recipe in load_recipes():
        if "clean" not in recipe["health_tags"]:
            continue
        for banned in ("sugar", "coconut_milk"):
            assert banned not in all_ingredients_of(recipe), (
                f"{recipe['id']} is tagged clean but contains {banned}"
            )


# ---------------------------------------------------------------------------
# Usability from a photo
# ---------------------------------------------------------------------------

def test_enough_recipes_are_reachable_from_a_photo_alone():
    """
    At least 20 dishes whose main ingredients YOLO can actually detect.

    Without this floor the system demos badly: a user photographs vegetables,
    and every dish that matches needs an ingredient the camera cannot see, so
    the recommendations are all "you are missing four things". It also matters
    for Week 7 — a recommender evaluated only on text input is not evaluating
    the multimodal system the project is about.
    """
    detectable = {k for k, v in load_ingredients().items() if v["yolo_class_id"] is not None}
    reachable = [
        r["id"] for r in load_recipes() if set(r["main_ingredients"]) <= detectable
    ]
    assert len(reachable) >= 20, (
        f"only {len(reachable)} of 40 recipes are reachable from a photo alone: {reachable}"
    )
