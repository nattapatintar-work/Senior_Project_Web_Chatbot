"""
tools/eval_rule_score.py
========================
Steps 2-3 of the recommender baseline evaluation: the DETERMINISTIC half of the
rubric plus all metrics. Pure code: no LLM, no network, no recommender import.

    python tools/eval_rule_score.py

Reads   data/eval/baseline_top3.json         (written by tools/eval_dump_top3.py)
Writes  data/eval/baseline_rule_metrics.json
        data/eval/baseline_rule_metrics.md

Everything is computed from the recipe fields stored in baseline_top3.json and the
query; nothing is re-run through recommend().

RUBRIC (per recommended recipe)
-------------------------------
  violation_system_rule   requested health tag missing from the recipe's health_tags,
                          or that tag in excluded_for, or an excluded ingredient in
                          main + seasonings -- exactly what recommend.py:143-158 checks.
  violation_with_optional same, but an excluded ingredient in optional_ingredients
                          counts too.
  A  2 if any user ingredient is a MAIN ingredient; 1 if only an OPTIONAL one; else 0.
  B  share = (# main not in the user's ingredients) / (# main);
     2 if share == 0; 1 if share <= B_PARTIAL_SHARE; else 0.
  C  0 if category == "dessert", else 1.
  total_capped                   0 if violation_with_optional, else A+B+C, and
                                 min(total, DESSERT_TOTAL_CAP) when C == 0.
  total_uncapped                 0 if violation_with_optional, else A+B+C.
  total_system_violation_only    like total_capped, but with violation_system_rule.
"""

import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).parent.parent
IN_PATH = ROOT / "data" / "eval" / "baseline_top3.json"
OUT_JSON = ROOT / "data" / "eval" / "baseline_rule_metrics.json"
OUT_MD = ROOT / "data" / "eval" / "baseline_rule_metrics.md"

# ---------------------------------------------------------------------------
# DEFINITIONS WE CHOSE -- none of these is derived from data.
# ---------------------------------------------------------------------------
A_POINTS_MAIN = 2            # definition we chose: a user ingredient is a MAIN ingredient
A_POINTS_OPTIONAL_ONLY = 1   # definition we chose: a user ingredient matches only an OPTIONAL one
B_POINTS_ALL_HAVE = 2        # definition we chose: nothing missing from the main ingredients
B_POINTS_PARTIAL = 1         # definition we chose: some main ingredients missing, but not most
B_PARTIAL_SHARE = 0.5        # definition we chose: missing-main share at or below this = partial credit
C_POINTS_NON_DESSERT = 1     # definition we chose: non-dessert recipes get this point
C_POINTS_DESSERT = 0         # definition we chose: dessert recipes get this point
DESSERT_TOTAL_CAP = 2        # definition we chose: a dessert's total is capped at this in the capped variants
PASS_LENIENT = 3             # definition we chose: "lenient" pass line, total >= this
PASS_STRICT = 4              # definition we chose: "strict" pass line, total >= this
TOP_K = 3                    # definition we chose: list length evaluated (matches /recommend's first page)

VARIANTS = ("total_capped", "total_uncapped", "total_system_violation_only")
PASS_LINES = {"lenient": PASS_LENIENT, "strict": PASS_STRICT}
GROUPS = ("A", "B", "C", "D", "E")


# ---------------------------------------------------------------------------
# Per-recipe rubric
# ---------------------------------------------------------------------------

def violations(recipe: dict, query: dict) -> tuple[bool, bool]:
    """(violation_system_rule, violation_with_optional)."""
    tag_problem = any(
        tag not in recipe["health_tags"] or tag in recipe["excluded_for"]
        for tag in query["health_tags"]
    )
    excluded = set(query["excluded"])
    hard = set(recipe["main_ingredients"]) | set(recipe["seasonings"])
    system = tag_problem or bool(hard & excluded)
    with_optional = tag_problem or bool((hard | set(recipe["optional_ingredients"])) & excluded)
    return system, with_optional


def points_a(recipe: dict, query: dict) -> int:
    user = set(query["ingredients"])
    if user & set(recipe["main_ingredients"]):
        return A_POINTS_MAIN
    if user & set(recipe["optional_ingredients"]):
        return A_POINTS_OPTIONAL_ONLY
    return 0


def points_b(recipe: dict, query: dict) -> int:
    mains = recipe["main_ingredients"]
    if not mains:                       # cannot happen in recipes.json (checked); nothing matched -> no credit
        return 0
    share = sum(1 for m in mains if m not in set(query["ingredients"])) / len(mains)
    if share == 0:
        return B_POINTS_ALL_HAVE
    if share <= B_PARTIAL_SHARE:
        return B_POINTS_PARTIAL
    return 0


def points_c(recipe: dict) -> int:
    return C_POINTS_DESSERT if recipe["category"] == "dessert" else C_POINTS_NON_DESSERT


def score_recipe(recipe: dict, query: dict) -> dict:
    """Every deterministic rubric component for one recommended recipe."""
    v_system, v_optional = violations(recipe, query)
    a, b, c = points_a(recipe, query), points_b(recipe, query), points_c(recipe)
    raw = a + b + c
    capped = min(raw, DESSERT_TOTAL_CAP) if c == C_POINTS_DESSERT else raw
    return {
        "violation_system_rule": v_system,
        "violation_with_optional": v_optional,
        "A": a,
        "B": b,
        "C": c,
        "total_capped": 0 if v_optional else capped,
        "total_uncapped": 0 if v_optional else raw,
        "total_system_violation_only": 0 if v_system else capped,
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def jaccard_distance(a: set, b: set) -> float:
    union = a | b
    return 1.0 - (len(a & b) / len(union)) if union else 0.0


def diversity(results: list[dict]) -> float | None:
    """Mean pairwise Jaccard distance of main+optional key sets. None with fewer than 2 items."""
    if len(results) < 2:
        return None
    sets = [set(r["main_ingredients"]) | set(r["optional_ingredients"]) for r in results]
    return round(sum(jaccard_distance(x, y) for x, y in combinations(sets, 2)) / (len(sets) * (len(sets) - 1) / 2), 4)


def query_metrics(query: dict) -> dict:
    """Per-query scores and metrics. Precision is over the items actually returned."""
    scored = []
    for result in query["results"]:
        scored.append({"rank": result["rank"], "id": result["id"], "name_th": result["name_th"],
                       "category": result["category"], **score_recipe(result, query)})

    n = len(scored)
    per_variant = {}
    for variant in VARIANTS:
        totals = [s[variant] for s in scored]
        entry = {"totals": totals, "mean_total": _mean(totals)}
        for line_name, line in PASS_LINES.items():
            passing = sum(1 for t in totals if t >= line)
            entry[line_name] = {
                "passing": passing,
                "precision_at_3": round(passing / n, 4) if n else None,   # divided by # returned; None if none
                "hit_at_3": 1 if passing else 0,                          # an empty result is a miss
            }
        per_variant[variant] = entry

    return {
        "id": query["id"],
        "group": query["group"],
        "n_returned": n,
        "short": n < TOP_K,
        "empty": n == 0,
        "variants": per_variant,
        "mean_system_score": _mean([r["score"] for r in query["results"]]),
        "dessert_share": round(sum(1 for r in query["results"] if r["category"] == "dessert") / n, 4) if n else None,
        "diversity": diversity(query["results"]),
        "items": scored,
    }


def aggregate(rows: list[dict], all_results: list[dict], catalog_size: int) -> dict:
    """
    Macro mean over the given per-query rows. Precision/diversity/dessert share skip queries where
    they are undefined (nothing returned / fewer than 2 items); Hit@3 counts every query.
    """
    out = {
        "n_queries": len(rows),
        "n_queries_short": sum(1 for r in rows if r["short"]),
        "n_queries_empty": sum(1 for r in rows if r["empty"]),
        "n_queries_in_precision_mean": sum(1 for r in rows if r["n_returned"]),
        "variants": {},
    }
    for variant in VARIANTS:
        entry = {"mean_total": _mean([r["variants"][variant]["mean_total"] for r in rows])}
        for line_name in PASS_LINES:
            entry[line_name] = {
                "precision_at_3": _mean([r["variants"][variant][line_name]["precision_at_3"] for r in rows]),
                "hit_at_3": _mean([r["variants"][variant][line_name]["hit_at_3"] for r in rows]),
            }
        out["variants"][variant] = entry

    ids = {r["id"] for r in all_results}
    dessert_items = sum(1 for r in all_results if r["category"] == "dessert")
    out["independent"] = {
        "distinct_recipes": len(ids),
        "catalog_size": catalog_size,
        "catalog_coverage": round(len(ids) / catalog_size, 4),
        "dessert_items": dessert_items,
        "total_items": len(all_results),
        "dessert_share_pooled": round(dessert_items / len(all_results), 4) if all_results else None,
        "dessert_share_mean_per_query": _mean([r["dessert_share"] for r in rows]),
        "intra_list_diversity_mean": _mean([r["diversity"] for r in rows]),
        "mean_system_score": _mean([r["mean_system_score"] for r in rows]),
    }
    return out


def differing_violations(rows: list[dict]) -> list[dict]:
    """Recipes where the system's own rule and the with-optional rule disagree."""
    out = []
    for row in rows:
        for item in row["items"]:
            if item["violation_system_rule"] != item["violation_with_optional"]:
                out.append({"query": row["id"], "rank": item["rank"], "recipe_id": item["id"],
                            "name_th": item["name_th"],
                            "violation_system_rule": item["violation_system_rule"],
                            "violation_with_optional": item["violation_with_optional"]})
    return out


def compute(baseline: dict) -> dict:
    catalog = baseline["meta"]["catalog_size"]
    rows = [query_metrics(q) for q in baseline["queries"]]
    results_by_group = {g: [] for g in GROUPS}
    for q in baseline["queries"]:
        results_by_group.setdefault(q["group"], []).extend(q["results"])

    groups = {g: aggregate([r for r in rows if r["group"] == g], results_by_group[g], catalog)
              for g in GROUPS if any(r["group"] == g for r in rows)}
    overall = aggregate(rows, [r for q in baseline["queries"] for r in q["results"]], catalog)

    return {
        "constants": {
            "A_POINTS_MAIN": A_POINTS_MAIN, "A_POINTS_OPTIONAL_ONLY": A_POINTS_OPTIONAL_ONLY,
            "B_POINTS_ALL_HAVE": B_POINTS_ALL_HAVE, "B_POINTS_PARTIAL": B_POINTS_PARTIAL,
            "B_PARTIAL_SHARE": B_PARTIAL_SHARE, "C_POINTS_NON_DESSERT": C_POINTS_NON_DESSERT,
            "C_POINTS_DESSERT": C_POINTS_DESSERT, "DESSERT_TOTAL_CAP": DESSERT_TOTAL_CAP,
            "PASS_LENIENT": PASS_LENIENT, "PASS_STRICT": PASS_STRICT, "TOP_K": TOP_K,
            "note": "every value above is a definition we chose, not derived from data",
        },
        "overall": overall,
        "groups": groups,
        "differing_violations": differing_violations(rows),
        "system_rule_violations_in_returned_items": sum(
            1 for r in rows for i in r["items"] if i["violation_system_rule"]),
        "queries": rows,
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def _f(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _table(agg: dict) -> list[str]:
    lines = ["| variant | pass line | Precision@3 | Hit@3 | mean total |", "|---|---|---|---|---|"]
    for variant in VARIANTS:
        entry = agg["variants"][variant]
        for line_name, line in PASS_LINES.items():
            lines.append(
                f"| {variant} | {line_name} (>={line}) | {_f(entry[line_name]['precision_at_3'])} | "
                f"{_f(entry[line_name]['hit_at_3'])} | {_f(entry['mean_total'])} |"
            )
    ind = agg["independent"]
    lines += [
        "",
        f"- queries: {agg['n_queries']} | with fewer than 3 results: {agg['n_queries_short']} "
        f"| with none: {agg['n_queries_empty']} | in Precision mean: {agg['n_queries_in_precision_mean']}",
        f"- catalog coverage: {ind['distinct_recipes']}/{ind['catalog_size']} = {_f(ind['catalog_coverage'])}",
        f"- dessert share: pooled {ind['dessert_items']}/{ind['total_items']} = {_f(ind['dessert_share_pooled'])}"
        f" | mean per query {_f(ind['dessert_share_mean_per_query'])}",
        f"- intra-list diversity (mean pairwise Jaccard distance): {_f(ind['intra_list_diversity_mean'])}",
        f"- mean system score of the returned items: {_f(ind['mean_system_score'])}",
        "",
    ]
    return lines


def to_markdown(result: dict) -> str:
    c = result["constants"]
    lines = [
        "# Baseline rule-based metrics",
        "",
        "Generated by `tools/eval_rule_score.py` from `data/eval/baseline_top3.json`. Deterministic; no LLM.",
        "",
        f"Definitions we chose (not derived from data): B partial share <= {c['B_PARTIAL_SHARE']}, "
        f"dessert total cap {c['DESSERT_TOTAL_CAP']}, pass lines lenient >= {c['PASS_LENIENT']} / strict >= {c['PASS_STRICT']}.",
        "Means are macro means over queries. Precision@3 divides by the number of results returned and skips "
        "queries with none; Hit@3 counts every query (an empty result is a miss).",
        "",
        "## Overall",
        "",
        *_table(result["overall"]),
    ]
    for group, agg in result["groups"].items():
        lines += [f"## Group {group}", "", *_table(agg)]

    lines += ["## Per query", "",
              "| query | returned | capped | uncapped | system-violation-only | violation (system / with optional) |",
              "|---|---|---|---|---|---|"]
    for row in result["queries"]:
        v = row["variants"]
        flags = ", ".join(f"{i['violation_system_rule']:d}/{i['violation_with_optional']:d}" for i in row["items"])
        lines.append(f"| {row['id']} | {row['n_returned']} | {v['total_capped']['totals']} | "
                     f"{v['total_uncapped']['totals']} | {v['total_system_violation_only']['totals']} | {flags or '-'} |")

    lines += ["", "## Queries where violation_system_rule and violation_with_optional differ", ""]
    if result["differing_violations"]:
        lines += ["| query | rank | recipe | name_th |", "|---|---|---|---|"]
        lines += [f"| {d['query']} | {d['rank']} | {d['recipe_id']} | {d['name_th']} |"
                  for d in result["differing_violations"]]
    else:
        lines.append("None.")
    lines += ["", f"violation_system_rule true for {result['system_rule_violations_in_returned_items']} "
                  "returned item(s).", ""]
    return "\n".join(lines)


def main() -> None:
    if not IN_PATH.exists():
        sys.exit(f"missing input: {IN_PATH} (run tools/eval_dump_top3.py first)")
    with open(IN_PATH, encoding="utf-8") as f:
        baseline = json.load(f)
    result = compute(baseline)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(to_markdown(result))
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
