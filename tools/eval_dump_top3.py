"""
tools/eval_dump_top3.py
=======================
Step 1 of the recommender baseline evaluation: dump the REAL top-3 that the
system returns for every query in data/eval/test_set_draft_v1.json.

    python tools/eval_dump_top3.py

Reads   data/eval/test_set_draft_v1.json   (the `preview_top3` field is ignored:
                                            it came from an external simulation)
Writes  data/eval/baseline_top3.json       (deterministic: rerun = identical file)

No LLM, no network, no API key. Only recommender.recommend() runs.

HOW THE CALL MIRRORS POST /recommend (api/app.py:428-450)
----------------------------------------------------------
    recommend(ingredients=used.ingredients, health_tags=used.health_tags,
              excluded=used.exclude, top_k=body.top_n, seasonings=used.seasonings)

  - top_k      = 3   (frontend asks top_n = logic.topNForPage(0) = 3)
  - seasonings = []  (nothing ticked; sess.seasonings defaults to an empty LIST,
                      not None, and /recommend passes list(sess.seasonings))
  - excluded   = the query's `excluded`
  - health_tags= the query's `health_tags`, de-duplicated in order (state.py:102)
  - ingredients= SessionState.ingredients (state.py:63-68): the query's ingredients
                 de-duplicated in order, minus anything in `excluded`. The raw list
                 is kept next to it in the output as `ingredients`; the list the
                 system actually received is `used_ingredients`.

recommend() prints one "[recommend] ..." line per call; stdout is swallowed here so
the script's own output stays readable.
"""

import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from recommender.recommend import load_recipes, recommend

TEST_SET_PATH = ROOT / "data" / "eval" / "test_set_draft_v1.json"
INGREDIENTS_PATH = ROOT / "data" / "ingredients.json"
HEALTH_TERMS_PATH = ROOT / "data" / "health_terms.json"
OUT_PATH = ROOT / "data" / "eval" / "baseline_top3.json"

TOP_K = 3
SEASONINGS_TICKED: list[str] = []   # "no seasonings ticked", as an empty list like SessionState


def _load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _names(keys: list[str], ingredients: dict) -> list[str | None]:
    """Thai name per key, from ingredients.json's `name_th`. None if the key is unknown."""
    return [ingredients.get(key, {}).get("name_th") for key in keys]


def _session_view(query: dict) -> dict:
    """What SessionState hands to recommend(): dedup in order, excluded removed (state.py:63-68, 101-102)."""
    excluded = set(query["excluded"])
    return {
        "ingredients": [k for k in dict.fromkeys(query["ingredients"]) if k not in excluded],
        "health_tags": list(dict.fromkeys(query["health_tags"])),
        "excluded": list(query["excluded"]),
    }


def _dictionary_issues(query: dict, ingredients: dict, health_tags: set[str]) -> dict:
    """Things in the query the dictionary does not know, or that the system will silently ignore."""
    return {
        "unknown_ingredients": [k for k in query["ingredients"] if k not in ingredients],
        "unknown_excluded": [k for k in query["excluded"] if k not in ingredients],
        "unknown_health_tags": [t for t in query["health_tags"] if t not in health_tags],
        # recommend() strips seasoning keys from the user's list before scoring (recommend.py:224-226)
        "seasoning_keys_in_ingredients": [
            k for k in query["ingredients"] if ingredients.get(k, {}).get("is_seasoning")
        ],
        # SessionState.ingredients drops an ingredient that is also excluded (state.py:63-68)
        "ingredients_also_excluded": [k for k in query["ingredients"] if k in query["excluded"]],
    }


def _result_row(rank: int, dish: dict, recipe: dict, ingredients: dict) -> dict:
    main, optional, seasonings = (
        recipe["main_ingredients"], recipe["optional_ingredients"], recipe["seasonings"],
    )
    return {
        "rank": rank,
        "id": dish["id"],
        "name_th": dish["name_th"],
        "category": recipe["category"],
        "main_ingredients": main,
        "main_ingredients_th": _names(main, ingredients),
        "optional_ingredients": optional,
        "optional_ingredients_th": _names(optional, ingredients),
        "seasonings": seasonings,
        "seasonings_th": _names(seasonings, ingredients),
        "health_tags": recipe["health_tags"],
        "excluded_for": recipe["excluded_for"],
        "score": dish["score"],
        "have": dish["have"],
        "missing": dish["missing"],
    }


def build() -> dict:
    test_set = _load_json(TEST_SET_PATH)
    ingredients = _load_json(INGREDIENTS_PATH)
    health_terms = {k for k in _load_json(HEALTH_TERMS_PATH) if not k.startswith("_")}
    recipes = load_recipes()
    by_id = {r["id"]: r for r in recipes}

    queries = []
    for query in test_set:
        view = _session_view(query)
        with contextlib.redirect_stdout(io.StringIO()):     # swallow recommend()'s log line
            dishes = recommend(
                ingredients=view["ingredients"],
                health_tags=view["health_tags"],
                excluded=view["excluded"],
                top_k=TOP_K,
                seasonings=list(SEASONINGS_TICKED),
            )
        results = [_result_row(i, d, by_id[d["id"]], ingredients) for i, d in enumerate(dishes, start=1)]
        queries.append({
            "id": query["id"],
            "group": query["id"][0],
            "text_th": query["text_th"],
            "ingredients": query["ingredients"],
            "health_tags": query["health_tags"],
            "excluded": query["excluded"],
            "used_ingredients": view["ingredients"],
            "n_returned": len(results),
            # kept, never hidden: fewer than 3 (or none) returned
            "short": len(results) < TOP_K,
            "empty": len(results) == 0,
            "dictionary_issues": _dictionary_issues(query, ingredients, health_terms),
            "results": results,
        })

    return {
        "meta": {
            "source": "data/eval/test_set_draft_v1.json (preview_top3 ignored)",
            "top_k": TOP_K,
            "seasonings_ticked": SEASONINGS_TICKED,
            "catalog_size": len(recipes),
            "n_queries": len(queries),
            "call": "recommend(ingredients=used_ingredients, health_tags, excluded, top_k=3, seasonings=[])",
        },
        "queries": queries,
    }


def main() -> None:
    if not TEST_SET_PATH.exists():
        sys.exit(f"missing input: {TEST_SET_PATH}")
    data = build()
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    short = [q["id"] for q in data["queries"] if q["short"]]
    print(f"wrote {OUT_PATH.relative_to(ROOT)}: {len(data['queries'])} queries, "
          f"{len(short)} with fewer than {TOP_K} results {short}")


if __name__ == "__main__":
    main()
