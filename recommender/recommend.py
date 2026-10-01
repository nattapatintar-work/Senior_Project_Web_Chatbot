"""
recommender/recommend.py
========================
Given the ingredients a user has, suggest the Top-3 dishes they could cook.

    ["chicken", "garlic", "chili"] + health=["clean"]
        |
        v
    [{"name_th": "ผัดกะเพราไก่", "score": 0.87,
      "have": ["chicken", "garlic", "chili"], "missing": ["holy_basil"], ...}]

Content-Based Filtering, per Claude.md:451-474:
    1. Turn each dish into a vector of the ingredients it uses (mains counted
       twice, optionals once -- see _recipe_document() for why).
    2. Weight those vectors with TF-IDF, so a rare ingredient (shrimp) counts
       for more than one that shows up in nearly every recipe (garlic).
    3. Score with cosine similarity (0.0 = nothing in common, 1.0 = identical).
    4. Drop dishes the health/excluded filters rule out *before* scoring, and
       keep the best top_k of what remains.

The doc is explicit that this is implementation, not research -- scikit-learn
already provides both TF-IDF and cosine similarity, so nothing here needs
inventing. No blend with a coverage term either: pure cosine is what the doc
asks for, and it is what the report can explain in one sentence.

One rule worth remembering: scoring is PARTIAL. A user is never required to
have every ingredient a dish calls for, because nobody has a full fridge.
Missing MAIN ingredients are reported in "missing" as a shopping list;
optional ingredients never block a dish and never show up as "missing" --
they show up in "have" only if the user happens to have them.

SEASONINGS ARE A BONUS, NEVER A REQUIREMENT (Option A, web track). Two rules:
    - a recipe's `seasonings` list is never part of its TF-IDF document, and a
      user's `ingredients` list still has seasonings stripped before it is
      vectorised -- so typing "fish_sauce" in free text cannot boost a score
    - seasonings the user explicitly ticked arrive through the separate
      `seasonings` argument and add a bonus AFTER the cosine score:
          score = min(1.0, cosine + SEASONING_WEIGHT * overlap)
          overlap = |ticked & recipe.seasonings| / |recipe.seasonings|
      A recipe missing a ticked seasoning is still returned, just scored lower
      than one that matches it. The bonus never resurrects a dish whose
      ingredient cosine is 0 ("nothing in common is not a recommendation").
      With seasonings=None the output is identical to the pre-Option-A code.

Excluded ingredients ("no pork") only drop a dish if that ingredient is in
main_ingredients or seasonings. An excluded ingredient in optional_ingredients
does not disqualify the dish -- an optional is omittable by definition, so
the dish is still cookable without it. It simply never appears in have/missing
for that recipe.
"""

import json
import sys
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Let this module find nlp/, whether it's imported from api/main.py (which
# already does this same insert for itself), collected by pytest (which does
# it per test file), or run directly as `python recommender/recommend.py`.
# Without it, Python only looks inside recommender/ and raises ImportError.
sys.path.insert(0, str(Path(__file__).parent.parent))

from nlp.extract import load_ingredients

# Where the recipe database lives. __file__ is this file's own path, so this
# works no matter which folder you run python from.
RECIPES_PATH = Path(__file__).parent.parent / "data" / "recipes.json"

# How much a fully matched seasoning list is worth, on the same 0-1 scale as the
# cosine score (a recipe whose every seasoning the user ticked gains this much).
# Not yet decided -- an open item in Claude.md; kept as one named constant so it
# can be tuned without touching the scoring logic.
SEASONING_WEIGHT = 0.3

# Recipe `category` values that recommend() never returns. A condiment (a sauce, a pickle, a
# crispy-shallot topping) is something served WITH a dish, not a dish a user asks for, so it is
# dropped before scoring however well its ingredients match. Always on, not a parameter.
# Recipes with no `category` field are never excluded.
EXCLUDED_CATEGORIES = {"condiment"}

# What recommend()'s `category` argument accepts. "all" (or None) applies no category filter, so
# snack and drink recipes are returned only then; "savory" / "dessert" keep only recipes whose
# `category` equals it. EXCLUDED_CATEGORIES applies in every mode.
CATEGORY_CHOICES = ("all", "savory", "dessert")


def load_recipes() -> list[dict]:
    """
    Read data/recipes.json off disk and hand it back as a list of dicts.

    encoding="utf-8" is not optional -- the file is full of Thai dish names,
    and on Windows Python otherwise guesses a legacy encoding and raises
    UnicodeDecodeError. Same reasoning as nlp/extract.py's load_ingredients().
    """
    with open(RECIPES_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Built once at import time, not per call. recommend() runs on the LINE
# reply-token path (concern C11: the token lives ~30s), so re-fitting a
# TF-IDF matrix over 40 recipes on every message would be a wasteful place to
# lose time -- the same reasoning nlp/extract.py gives for building its Trie
# once at module load.
# ---------------------------------------------------------------------------

def _recipe_document(recipe: dict) -> list[str]:
    """
    Turn one recipe into the token list the vectorizer sees.

    main_ingredients appear TWICE, optional_ingredients ONCE. Repetition is
    how term frequency expresses "the mains matter more than the optionals"
    without inventing a separate weighting scheme on top of TF-IDF -- the
    vectorizer's own term-frequency count does the work.

    seasonings are never included. Claude.md:427: basic seasonings must not
    affect matching, since everyone already has them at home.
    """
    return recipe["main_ingredients"] * 2 + recipe["optional_ingredients"]


def _is_seasoning(key: str, known: dict) -> bool:
    return known.get(key, {}).get("is_seasoning", False)


_RECIPES = load_recipes()
_KNOWN_INGREDIENTS = load_ingredients()

# analyzer=lambda doc: doc -- documents are already lists of canonical keys
# (ASCII snake_case), not free text needing tokenization. Passing them straight
# through skips scikit-learn's default English-text preprocessing, which has
# no reason to run on keys like "green_onion".
_VECTORIZER = TfidfVectorizer(analyzer=lambda doc: doc)
_RECIPE_MATRIX = _VECTORIZER.fit_transform(
    [_recipe_document(recipe) for recipe in _RECIPES]
)


def _passes_health_filter(recipe: dict, health_tags: list[str]) -> bool:
    """
    Keep a recipe only if it actively suits every requested tag.

    Multiple requested tags are AND, not OR -- a user asking for both "vegan"
    and "keto" wants dishes that satisfy both simultaneously, not either one.
    health_tags and excluded_for are checked as opposites per
    data/HEALTH_TAGS.md, though in practice a recipe's health_tags is always
    disjoint from its own excluded_for (test_a_tag_is_never_both_claimed_and_
    excluded in tests/test_recipes.py), so checking health_tags alone is
    already correct here -- excluded_for is re-checked anyway as a second,
    redundant guard rather than trusting that invariant silently.
    """
    for tag in health_tags:
        if tag not in recipe["health_tags"]:
            return False
        if tag in recipe["excluded_for"]:
            return False
    return True


def _passes_excluded_filter(recipe: dict, excluded: list[str]) -> bool:
    """
    Drop a recipe only if an excluded ingredient is in main_ingredients or
    seasonings. An excluded ingredient sitting only in optional_ingredients
    does not disqualify the dish -- see the module docstring.
    """
    hard_ingredients = set(recipe["main_ingredients"]) | set(recipe["seasonings"])
    return not (hard_ingredients & set(excluded))


def _passes_category_filter(recipe: dict) -> bool:
    """False for a recipe whose category is in EXCLUDED_CATEGORIES (a missing category passes)."""
    return recipe.get("category") not in EXCLUDED_CATEGORIES


def _passes_category_choice(recipe: dict, category: str | None) -> bool:
    """
    The user's category choice as a hard filter. None / "all" keeps everything; "savory" /
    "dessert" keep only recipes whose `category` equals it (a recipe with no category key
    therefore does not match either).
    """
    if category is None or category == "all":
        return True
    return recipe.get("category") == category


def recommend(
    ingredients: list[str],
    health_tags: list[str] | None = None,
    excluded: list[str] | None = None,
    top_k: int = 3,
    seasonings: list[str] | None = None,
    category: str | None = None,
) -> list[dict]:
    """
    Score every dish against what the user has, return the best `top_k`.

    Args:
        ingredients: canonical keys the user has, e.g. ["chicken", "egg"].
                     These come from YOLO (photo), extract() (text), or both
                     merged together.
        health_tags: diets to filter for, e.g. ["clean"]. None means no filter.
        excluded:    ingredients to avoid, e.g. ["pork"]. A dish needing one of
                     these as a main ingredient or seasoning is dropped
                     entirely; as an optional ingredient it is kept.
        top_k:       how many dishes to return. Defaults to 3.
        seasonings:  seasoning keys the user ticked, e.g. ["fish_sauce"]. Bonus
                     only (see the module docstring); None or [] leaves every
                     score exactly as the plain cosine computes it. Non-seasoning
                     keys passed here are ignored.
        category:    the user's category choice, a hard filter applied before
                     scoring (see CATEGORY_CHOICES): None or "all" = no filter
                     (the only mode that returns snack and drink recipes),
                     "savory" / "dessert" = only recipes of that category.
                     Condiments are never returned. Any other value raises
                     ValueError. With the default, results are exactly what
                     they were before this argument existed.

    Returns:
        A list of at most `top_k` dicts, best score first (each also carries
        "seasonings_matched": [...] -- the ticked seasonings this dish uses --
        but only when the `seasonings` argument was passed; every dish also
        carries "cook_time_min", "recipe_source_url", "main_ingredients" and
        "seasonings" -- the recipe's own display data for the web cards):
            {
                "id":          "th_001",              # matches recipes.json
                "name_th":     "ผัดกะเพราไก่",
                "score":       0.87,                  # always between 0.0 and 1.0
                "have":        ["chicken", ...],      # user already has these
                "missing":     ["holy_basil"],         # MAIN ingredients to buy
                "nutrition":   {"kcal": 450, "protein": 32, "fat": 18, "carb": 35},
                "health_tags": ["clean"],              # passed through as-is;
                                                        # Week 8's format_reply()
                                                        # decides how to word it
                                                        # (see concern.md C15)
            }

        Empty list is a valid answer -- it means nothing matched (or every
        candidate was filtered out), and the bot should say so rather than
        crash.

    Why `health_tags: list[str] | None = None` and not `= []`:
        A mutable default like [] is created once and shared by every call to
        the function, so if anything ever appends to it the change leaks into
        later calls. It is a classic Python bug. Using None and converting
        inside the function avoids it.
    """
    if category is not None and category not in CATEGORY_CHOICES:
        raise ValueError(f"category must be None or one of {CATEGORY_CHOICES}, got {category!r}")
    health_tags = health_tags or []
    excluded = excluded or []

    # Seasonings typed into `ingredients` never influence matching -- strip
    # them from the user's own list before anything else touches it. Typing
    # "fish_sauce" must not itself boost any dish's score. Ticked seasonings
    # take the separate, explicit `seasonings` path below (bonus only).
    ticked_seasonings = {
        key for key in (seasonings or []) if _is_seasoning(key, _KNOWN_INGREDIENTS)
    }
    user_ingredients = [
        key for key in ingredients if not _is_seasoning(key, _KNOWN_INGREDIENTS)
    ]
    user_set = set(user_ingredients)

    # Filter first, then score -- keeps the vector maths off dishes that could
    # never be returned regardless of similarity.
    #
    # Split into two sequential stages (health, then excluded on the
    # survivors) instead of one combined `and`, specifically so the
    # health_tags stage has an observable before/after count -- the final
    # `candidates` result is identical to a combined filter either way (AND
    # is order-independent for two pure boolean predicates over the same
    # items), this only changes how it's computed, not what it produces.
    health_passed = [
        (i, recipe) for i, recipe in enumerate(_RECIPES) if _passes_health_filter(recipe, health_tags)
    ]
    print(
        f"[recommend] health_tags={health_tags} filtered {len(_RECIPES)} candidates -> "
        f"{len(health_passed)} passed",
        flush=True,
    )

    candidates = [
        (i, recipe)
        for i, recipe in health_passed
        if _passes_excluded_filter(recipe, excluded)
        and _passes_category_filter(recipe)
        and _passes_category_choice(recipe, category)
    ]
    if not candidates or not user_ingredients:
        return []

    indices = [i for i, _ in candidates]
    user_vector = _VECTORIZER.transform([user_ingredients])
    scores = cosine_similarity(user_vector, _RECIPE_MATRIX[indices])[0]

    scored = []
    for (_, recipe), raw_score in zip(candidates, scores):
        if raw_score <= 0:
            continue  # nothing in common is not a recommendation

        # Clamp + round: cosine similarity can return a float epsilon over
        # 1.0 (e.g. 1.0000000000000002) due to floating-point rounding in the
        # dot product, which would otherwise fail the 0.0-1.0 contract.
        matched_seasonings = sorted(set(recipe["seasonings"]) & ticked_seasonings)
        if recipe["seasonings"]:
            overlap = len(matched_seasonings) / len(recipe["seasonings"])
        else:
            overlap = 0.0
        score = round(
            min(1.0, max(0.0, float(raw_score) + SEASONING_WEIGHT * overlap)), 2
        )

        mains = set(recipe["main_ingredients"])
        optionals = set(recipe["optional_ingredients"])
        have = sorted((mains | optionals) & user_set)
        missing = sorted(mains - user_set)

        dish = {
            "id": recipe["id"],
            "name_th": recipe["name_th"],
            "score": score,
            "have": have,
            "missing": missing,
            "nutrition": dict(recipe["nutrition"]),
            "health_tags": list(recipe["health_tags"]),
            # Display data for the web recipe cards (no effect on scoring).
            "cook_time_min": recipe.get("cook_time_min"),
            "recipe_source_url": recipe.get("recipe_source_url"),
            "main_ingredients": list(recipe["main_ingredients"]),
            "seasonings": list(recipe["seasonings"]),
        }
        if seasonings is not None:
            dish["seasonings_matched"] = matched_seasonings
        scored.append(dish)

    scored.sort(key=lambda dish: dish["score"], reverse=True)
    return scored[:top_k]


if __name__ == "__main__":
    # A Thai-locale Windows console defaults to the cp874 codepage and prints
    # Thai text as garbage. Switching stdout to UTF-8 fixes the display. This
    # is a terminal quirk only -- the strings themselves are always fine.
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    results = recommend(["chicken", "garlic", "chili"], health_tags=["clean"])
    for i, dish in enumerate(results, start=1):
        print(f"{i}. {dish['name_th']}  (score {dish['score']})")
        print(f"   have   : {dish['have']}")
        print(f"   missing: {dish['missing']}")
