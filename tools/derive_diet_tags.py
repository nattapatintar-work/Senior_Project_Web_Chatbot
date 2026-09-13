# -*- coding: utf-8 -*-
"""
tools/derive_diet_tags.py
==========================
Mechanically derives the vegetarian/vegan excluded_for + health_tags entries
for every recipe in data/recipes.json, from is_animal_product in
data/ingredients.json -- the same logic tests/test_recipes.py checks, now
extracted into a reusable tool instead of living only inside test assertions.

Why this exists: three separate one-time recipe-build scripts (dessert
batches 1-3) each hand-typed a default excluded_for=["vegetarian","vegan"]
per dish instead of deriving it, and each time some dishes were wrong (fully
plant-based dishes wrongly excluded, or egg-only dishes wrongly excluded from
vegetarian). Caught manually every time, before it reached git -- this script
is the fix so it can't recur silently: run it after ANY script that adds or
edits recipes, before running pytest.

Usage:
    python tools/derive_diet_tags.py          # report-only, exits 1 if any recipe is wrong
    python tools/derive_diet_tags.py --fix     # rewrites data/recipes.json in place

Rule (matches HEALTH_TAGS.md + tests/test_recipes.py):
    VEGETARIAN_OK_ANIMAL = {"egg", "quail_egg", "milk", "butter", "mayonnaise", "egg_noodle"}
    flesh = every is_animal_product ingredient NOT in VEGETARIAN_OK_ANIMAL

    - any flesh ingredient present  -> excluded_for includes "vegetarian"
    - any is_animal_product ingredient present (flesh or not) -> excluded_for includes "vegan"
    - neither -> that tag is added to health_tags instead (never left implicit)

Only main_ingredients + optional_ingredients count (seasonings are handled
separately -- e.g. fish_sauce already flows through the vegan check because
fish_sauce is itself is_animal_product and can live in seasonings; this
script checks seasonings too, matching test_vegan_filter_excludes_animal_product_seasonings).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
VEGETARIAN_OK_ANIMAL = {"egg", "quail_egg", "milk", "butter", "mayonnaise", "egg_noodle"}


def load_ingredients():
    return json.load(open(ROOT / "data" / "ingredients.json", encoding="utf-8"))


def load_recipes():
    return json.load(open(ROOT / "data" / "recipes.json", encoding="utf-8"))


def all_ingredients_of(recipe):
    return (
        recipe["main_ingredients"]
        + recipe["optional_ingredients"]
        + recipe["seasonings"]
    )


def derive(recipe, known):
    ings = all_ingredients_of(recipe)
    animal = {k for k in ings if known.get(k, {}).get("is_animal_product")}
    flesh = animal - VEGETARIAN_OK_ANIMAL

    excluded_for = set(recipe["excluded_for"])
    health_tags = set(recipe["health_tags"])

    excluded_for.discard("vegetarian")
    excluded_for.discard("vegan")
    health_tags.discard("vegetarian")
    health_tags.discard("vegan")

    if flesh:
        excluded_for.add("vegetarian")
    else:
        health_tags.add("vegetarian")

    if animal:
        excluded_for.add("vegan")
    else:
        health_tags.add("vegan")

    return sorted(excluded_for), sorted(health_tags)


def main():
    fix = "--fix" in sys.argv
    known = load_ingredients()
    recipes = load_recipes()

    wrong = []
    for r in recipes:
        new_excluded, new_tags = derive(r, known)
        old_excluded_diet = sorted(t for t in r["excluded_for"] if t in ("vegetarian", "vegan"))
        old_tags_diet = sorted(t for t in r["health_tags"] if t in ("vegetarian", "vegan"))
        new_excluded_diet = sorted(t for t in new_excluded if t in ("vegetarian", "vegan"))
        new_tags_diet = sorted(t for t in new_tags if t in ("vegetarian", "vegan"))
        if old_excluded_diet != new_excluded_diet or old_tags_diet != new_tags_diet:
            wrong.append((r, new_excluded, new_tags, old_excluded_diet, old_tags_diet, new_excluded_diet, new_tags_diet))

    if not wrong:
        print(f"OK: all {len(recipes)} recipes already have correct vegetarian/vegan tags.")
        return 0

    print(f"{len(wrong)} recipe(s) have wrong vegetarian/vegan tags:")
    for r, new_excluded, new_tags, old_ex, old_tag, new_ex, new_tag in wrong:
        print(f"  {r['id']} {r['name_th']}: excluded_for {old_ex} -> {new_ex}, health_tags {old_tag} -> {new_tag}")

    if fix:
        for r, new_excluded, new_tags, *_ in wrong:
            r["excluded_for"] = new_excluded
            r["health_tags"] = new_tags
        json.dump(recipes, open(ROOT / "data" / "recipes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Fixed {len(wrong)} recipe(s) in data/recipes.json.")
        return 0

    print("Run with --fix to rewrite data/recipes.json.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
