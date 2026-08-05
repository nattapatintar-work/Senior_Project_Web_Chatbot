"""
tools/compute_nutrition.py
==========================
Derives every recipe's `nutrition` block from its declared source, and checks
that what is stored in data/recipes.json still matches.

WHY THIS EXISTS
---------------
Forty recipes x four macros is 160 numbers. Typing them by hand means 160
chances to slip a decimal point, and a slipped decimal in a nutrition table
does not look wrong -- it looks like a slightly different dish. There is no
error, no crash, and no way to notice until someone checks by hand.

So no macro is ever typed. Each recipe declares *where its numbers come from*,
and this script does the arithmetic:

    nutrition_method "direct"    nutrition_ref -> data/thaifcd_cache.json
                                 macros x serving_g / 100

    nutrition_method "computed"  nutrition_basis {ingredient: grams}
                                 sum of (grams x macros / 100) per ingredient

Run it with --fill to write the numbers in, and with no arguments to verify
them. Verification is the useful mode: if someone edits a serving size or a
gram amount later and forgets to refresh the macros, this catches it.

USAGE
-----
    python tools/compute_nutrition.py           # verify, exit 1 on mismatch
    python tools/compute_nutrition.py --fill    # recompute and write back

A NOTE ON WHAT IS AND IS NOT SOURCED
------------------------------------
For "direct" recipes, the whole dish was analysed by INMU; only serving_g is
ours. For "computed" recipes the per-ingredient values are INMU's (or USDA's,
for broccoli) but **the gram amounts are this project's assumption** -- see
concern.md C14. Cooking losses and oil absorption are not modelled. The
arithmetic being automated does not make the inputs any more authoritative,
and the report should say so.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"
RECIPES = DATA / "recipes.json"

MACROS = ("kcal", "protein", "fat", "carb")

# How many decimal places each macro is stored with. kcal is a whole number
# because a tenth of a calorie is noise; the others keep one place because a
# tenth of a gram of fat is not.
PLACES = {"kcal": 0, "protein": 1, "fat": 1, "carb": 1}

# Values are compared with a tolerance rather than for exact equality, because
# rounding to the places above is lossy and a recomputation can land a hair off.
TOLERANCE = 0.05


def load_sources() -> dict:
    """Merge the Thai FCD cache and the external (USDA) table into one lookup."""
    table = json.loads((DATA / "thaifcd_cache.json").read_text(encoding="utf-8"))
    external = json.loads((DATA / "external_nutrition.json").read_text(encoding="utf-8"))
    # Keys beginning with _ are documentation, not food records.
    table.update({k: v for k, v in external.items() if not k.startswith("_")})
    return table


def scale(record: dict, grams: float) -> dict:
    """
    Scale a per-100 g record to `grams`.

    A macro the source never determined is stored as null, and is treated as a
    zero contribution here -- but the caller is told, so the recipe can say so
    in its notes. Silently zeroing it would turn "unknown" into "none", which
    is a different and much more confident claim.
    """
    out = {}
    for macro in MACROS:
        value = record.get(macro)
        out[macro] = 0.0 if value is None else value * grams / 100.0
    return out


def compute(recipe: dict, sources: dict) -> tuple[dict, list[str]]:
    """Return the recipe's derived macros, plus any gaps worth reporting."""
    totals = dict.fromkeys(MACROS, 0.0)
    gaps: list[str] = []

    if recipe["nutrition_method"] == "direct":
        key = recipe["nutrition_ref"]
        record = sources[key]
        for macro, value in scale(record, recipe["serving_g"]).items():
            totals[macro] += value
        gaps += [f"{record['food_code']}:{m}" for m in MACROS if record.get(m) is None]

    else:
        for ingredient, grams in recipe["nutrition_basis"].items():
            key = recipe["basis_refs"][ingredient]
            record = sources[key]
            for macro, value in scale(record, grams).items():
                totals[macro] += value
            gaps += [f"{ingredient}:{m}" for m in MACROS if record.get(m) is None]

    return {m: round(v, PLACES[m]) for m, v in totals.items()}, gaps


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    fill = "--fill" in sys.argv

    recipes = json.loads(RECIPES.read_text(encoding="utf-8"))
    sources = load_sources()
    mismatches = 0

    for recipe in recipes:
        derived, gaps = compute(recipe, sources)
        stored = recipe["nutrition"]

        differs = [
            m for m in MACROS if abs(float(stored.get(m, 0)) - derived[m]) > TOLERANCE
        ]

        if fill:
            recipe["nutrition"] = derived
        elif differs:
            mismatches += 1
            print(f"  MISMATCH {recipe['id']} {recipe['name_th']}")
            for m in differs:
                print(f"      {m}: stored {stored.get(m)} vs derived {derived[m]}")

        if gaps:
            print(f"  note  {recipe['id']} {recipe['name_th']}: source has no value for {', '.join(gaps)}")

        # A serving that is not the sum of its parts means a gram amount was
        # edited without updating serving_g, which would silently misreport the
        # portion while every macro still looked plausible.
        if recipe["nutrition_method"] == "computed":
            basis_total = sum(recipe["nutrition_basis"].values())
            if abs(basis_total - recipe["serving_g"]) > 0.5:
                print(
                    f"  WARN  {recipe['id']}: serving_g {recipe['serving_g']} "
                    f"but nutrition_basis sums to {basis_total}"
                )

    if fill:
        RECIPES.write_text(
            json.dumps(recipes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nfilled {len(recipes)} recipes")
        return 0

    print(f"\n{len(recipes)} recipes checked, {mismatches} mismatched")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
