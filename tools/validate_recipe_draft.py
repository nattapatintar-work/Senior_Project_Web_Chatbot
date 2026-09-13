# -*- coding: utf-8 -*-
"""
tools/validate_recipe_draft.py
===============================
Checks recipe ingredient placement against what data/ingredients.json
actually says, for any ingredient -- not a hardcoded list of past mistakes.

Why this exists: tapioca_starch has been miscategorized into a recipe's
`seasonings` list three separate times across three different batches
(th_167, th_171, th_182, th_185), always in the same situation -- used as a
thickener/coating/batter, a role that *feels* seasoning-like. Each time, the
category was guessed from the ingredient's culinary role in that dish
instead of checked against its actual `is_seasoning` flag in
data/ingredients.json, and each time it was caught only by the full pytest
run, after the recipe was already written into the batch.

This script runs the same check tests/test_recipes.py runs, but standalone
and against a DRAFT file -- so it can catch the mistake in the authoring
script's own run, before the recipe ever reaches data/recipes.json, instead
of waiting for the next `pytest tests/`. The rule is general: it reads
`is_seasoning` straight from the dictionary for whatever key is present, so
it catches the same class of error for any ingredient (rice_flour, egg,
wheat_flour, a brand-new key added mid-batch, ...), not just tapioca_starch.

Usage:
    python tools/validate_recipe_draft.py                  # validate data/recipes.json (all of it)
    python tools/validate_recipe_draft.py path/to/draft.json  # validate just a draft: a JSON
                                                             # list of recipe dicts, same schema,
                                                             # not yet merged into recipes.json

Exits 1 and prints every violation if anything is wrong; exits 0 silently
(prints a one-line OK) otherwise. Meant to run inside a batch-authoring
script right after building the new-recipes list and before appending it to
data/recipes.json -- not a replacement for tests/test_recipes.py, which
still runs against the merged file as the final check.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load_ingredients():
    return json.load(open(ROOT / "data" / "ingredients.json", encoding="utf-8"))


def load_recipes(path: Path | None):
    if path is None:
        return json.load(open(ROOT / "data" / "recipes.json", encoding="utf-8"))
    return json.load(open(path, encoding="utf-8"))


# The rule, in full generality: a key's home is decided by is_seasoning in
# the dictionary, never by how it functions in a particular dish.
FIELD_RULES = {
    # field name -> expected is_seasoning value for every key in it
    "main_ingredients": False,
    "optional_ingredients": False,
    "seasonings": True,
}


def validate(recipes: list[dict], known: dict) -> list[str]:
    """Return a list of human-readable violation strings, empty if clean."""
    problems = []

    for recipe in recipes:
        rid = recipe.get("id", "?")
        seen = {}  # ingredient key -> field it was first seen in, for duplicate detection

        for field, expected_is_seasoning in FIELD_RULES.items():
            for key in recipe.get(field, []):
                if key not in known:
                    problems.append(
                        f"{rid}: '{key}' in {field} is not in ingredients.json at all "
                        f"(typo, or a new ingredient that was never added to the dictionary)"
                    )
                    continue

                actual = known[key]["is_seasoning"]
                if actual != expected_is_seasoning:
                    category = known[key]["category"]
                    problems.append(
                        f"{rid}: '{key}' is in {field}, but ingredients.json says "
                        f"is_seasoning={actual} (category='{category}') -- "
                        f"{field} requires is_seasoning={expected_is_seasoning}. "
                        f"Check the dictionary, not how the ingredient functions in this dish."
                    )

                if key in seen and seen[key] != field:
                    problems.append(
                        f"{rid}: '{key}' appears in both {seen[key]} and {field} -- "
                        f"an ingredient belongs in exactly one list"
                    )
                seen[key] = field

        if not recipe.get("main_ingredients"):
            problems.append(f"{rid}: has no main_ingredients at all")

    return problems


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    draft_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    known = load_ingredients()
    recipes = load_recipes(draft_path)

    problems = validate(recipes, known)

    label = str(draft_path) if draft_path else "data/recipes.json"
    if problems:
        print(f"{len(problems)} problem(s) in {label}:")
        for p in problems:
            print(f"  {p}")
        return 1

    print(f"OK: {len(recipes)} recipe(s) in {label} have consistent ingredient placement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
