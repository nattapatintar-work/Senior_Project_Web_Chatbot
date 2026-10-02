"""
tools/eval_extra_metrics.py
===========================
Deterministic, offline metrics for the extra test set (data/eval/test_set_extra_v1.json):
group F (seasonings ticked) and group G (category picker). No LLM, no network.

    python tools/eval_extra_metrics.py

Reads   data/eval/test_set_extra_v1.json       the 14 extra queries (and their "notes")
        data/eval/post_rubric_v2_top3.json     stored top-3 of the paired existing A/B/E queries
        data/eval/test_set_draft_v1.json       only to re-check the paired queries against a fresh call
Writes  data/eval/extra_v1_top3.json           top-3 of the extra queries (tools/eval_dump_top3.dump)
        data/eval/extra_v1_metrics.json
        data/eval/extra_v1_metrics.md

The metric functions are pure (plain dicts in, plain dicts out) so tests need no recommender. The
recommender is imported lazily, only by count_available() and verify_pairs_against_recommender().

WHAT THE F METRICS MEAN
-----------------------
Each F query re-uses the ingredients of an existing A/B query and ticks 1-3 seasonings, and was
chosen BECAUSE the ticked seasonings change that query's top-3. "N of N pairs changed" therefore
measures how sensitive the ranking is to the seasoning weight (SEASONING_WEIGHT), not how often
ticking seasonings changes results in real use.

Seasoning overlap is defined exactly as recommender/recommend.py:306-313 computes it:
    overlap = |ticked & recipe.seasonings| / |recipe.seasonings|      (0 when the recipe has none)
The bonus added to the score is SEASONING_WEIGHT * overlap. Here the overlap of a top-3 list is
measured against the query's ticked seasonings, for the list WITH the seasonings ticked and for the
paired list WITHOUT them.

The rule rubric (tools/eval_rule_score.py, default RUBRIC_VERSION) scores ingredient overlap only,
so it cannot see the seasoning bonus directly; it is reported to show whether quality under that
rubric moved. For dessert-mode G queries only the uncapped variant is reported: the dessert cap
(DESSERT_TOTAL_CAP = 2) is below the pass lines (3 and 4), so a capped variant can never pass a
dessert.
"""

import json
import sys
from itertools import zip_longest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import eval_rule_score as ers

EVAL = ROOT / "data" / "eval"
EXTRA_SET_PATH = EVAL / "test_set_extra_v1.json"
DRAFT_SET_PATH = EVAL / "test_set_draft_v1.json"
PAIRED_TOP3_PATH = EVAL / "post_rubric_v2_top3.json"
RECIPES_PATH = ROOT / "data" / "recipes.json"
OUT_TOP3 = EVAL / "extra_v1_top3.json"
OUT_JSON = EVAL / "extra_v1_metrics.json"
OUT_MD = EVAL / "extra_v1_metrics.md"

F_CAVEAT = (
    "The F set was selected so that every pair changes its top-3, so \"N of N changed\" measures how sensitive "
    "the ranking is to the seasoning weight (SEASONING_WEIGHT), not how often ticking seasonings changes results "
    "in real use."
)
G_CAVEAT = (
    "For dessert-mode queries only the uncapped variant is reported: DESSERT_TOTAL_CAP (2) is below both pass "
    "lines (3 and 4), so a capped variant can never pass a dessert."
)
RUBRIC_CAVEAT = (
    "The rule rubric scores ingredient overlap only (A/B/C), so it cannot see the seasoning bonus; its totals are "
    "shown only to check whether quality under that rubric moved."
)


def _load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def _f(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


# ---------------------------------------------------------------------------
# Pure metric functions
# ---------------------------------------------------------------------------

def seasoning_overlap(recipe_seasonings: list[str], ticked: list[str]) -> float:
    """|ticked & recipe seasonings| / |recipe seasonings|; 0 when the recipe has none (recommend.py:306-313)."""
    if not recipe_seasonings:
        return 0.0
    return len(set(recipe_seasonings) & set(ticked)) / len(recipe_seasonings)


def mean_overlap(items: list[dict], ticked: list[str]) -> float | None:
    return _mean([seasoning_overlap(item["seasonings"], ticked) for item in items])


def positions_changed(without: list[str], with_: list[str]) -> int:
    """Number of rank positions whose recipe id differs between the two lists."""
    return sum(1 for a, b in zip_longest(without, with_) if a != b)


def items_replaced(without: list[str], with_: list[str]) -> dict:
    """Items dropped from / added to the list (set difference)."""
    dropped = [i for i in without if i not in with_]
    added = [i for i in with_ if i not in without]
    return {"count": len(dropped), "dropped": dropped, "added": added}


def rank_changes(without: list[str], with_: list[str]) -> list[dict]:
    """For every item in both lists whose 1-based rank differs: its rank without and with."""
    out = []
    for i, rid in enumerate(without, start=1):
        if rid in with_ and with_.index(rid) + 1 != i:
            out.append({"id": rid, "rank_without": i, "rank_with": with_.index(rid) + 1})
    return out


def rubric_totals(items: list[dict], query: dict) -> dict:
    """A/B/C rubric totals of a list of result rows (existing scoring functions, default RUBRIC_VERSION)."""
    scored = [ers.score_recipe(item, query) for item in items]
    capped = [s["total_capped"] for s in scored]
    uncapped = [s["total_uncapped"] for s in scored]
    return {
        "totals_capped": capped,
        "totals_uncapped": uncapped,
        "mean_total_capped": _mean(capped),
        "mean_total_uncapped": _mean(uncapped),
    }


def _pass_share(totals: list[int], line: int) -> float | None:
    return round(sum(1 for t in totals if t >= line) / len(totals), 4) if totals else None


def f_pair_metrics(with_q: dict, without_q: dict) -> dict:
    """Metrics of one F query against its paired existing query (same ingredients, no seasonings)."""
    ticked = with_q["seasonings"]
    ids_with = [r["id"] for r in with_q["results"]]
    ids_without = [r["id"] for r in without_q["results"]]
    over_without = mean_overlap(without_q["results"], ticked)
    over_with = mean_overlap(with_q["results"], ticked)
    rub_without = rubric_totals(without_q["results"], with_q)
    rub_with = rubric_totals(with_q["results"], with_q)
    return {
        "id": with_q["id"],
        "paired_with": with_q.get("paired_with", without_q["id"]),
        "ingredients": with_q["ingredients"],
        "seasonings": ticked,
        "top3_without": ids_without,
        "top3_with": ids_with,
        "top3_changed": ids_without != ids_with,
        "positions_changed": positions_changed(ids_without, ids_with),
        "items_replaced": items_replaced(ids_without, ids_with),
        "rank_changes_of_surviving_items": rank_changes(ids_without, ids_with),
        "mean_overlap_without": over_without,
        "mean_overlap_with": over_with,
        "mean_overlap_delta": round(over_with - over_without, 4) if None not in (over_with, over_without) else None,
        "rubric_without": rub_without,
        "rubric_with": rub_with,
        "mean_total_uncapped_delta": round(rub_with["mean_total_uncapped"] - rub_without["mean_total_uncapped"], 4),
        "mean_total_capped_delta": round(rub_with["mean_total_capped"] - rub_without["mean_total_capped"], 4),
    }


def f_aggregate(rows: list[dict]) -> dict:
    return {
        "n_pairs": len(rows),
        "n_top3_changed": sum(1 for r in rows if r["top3_changed"]),
        "mean_positions_changed": _mean([r["positions_changed"] for r in rows]),
        "mean_items_replaced": _mean([r["items_replaced"]["count"] for r in rows]),
        "mean_overlap_without": _mean([r["mean_overlap_without"] for r in rows]),
        "mean_overlap_with": _mean([r["mean_overlap_with"] for r in rows]),
        "mean_overlap_delta": _mean([r["mean_overlap_delta"] for r in rows]),
        "mean_total_uncapped_without": _mean([r["rubric_without"]["mean_total_uncapped"] for r in rows]),
        "mean_total_uncapped_with": _mean([r["rubric_with"]["mean_total_uncapped"] for r in rows]),
        "mean_total_capped_without": _mean([r["rubric_without"]["mean_total_capped"] for r in rows]),
        "mean_total_capped_with": _mean([r["rubric_with"]["mean_total_capped"] for r in rows]),
        "caveat": F_CAVEAT,
    }


def g_query_metrics(query: dict, available: int | None, paired_all_top3: list[str] | None = None) -> dict:
    """Metrics of one G query: category leak, availability and rubric totals (uncapped only for dessert mode)."""
    category = query["category"]
    items = query["results"]
    leaked = [r["id"] for r in items if category in ("savory", "dessert") and r["category"] != category]
    rubric = rubric_totals(items, query)
    out = {
        "id": query["id"],
        "paired_with": query.get("paired_with"),
        "ingredients": query["ingredients"],
        "category": category,
        "top3": [r["id"] for r in items],
        "n_returned": len(items),
        "results_available": available,
        "zero_results": None if available is None else available == 0,
        "leaked_ids": leaked,
        "category_leak_rate": round(len(leaked) / len(items), 4) if items and category in ("savory", "dessert") else None,
        "totals_uncapped": rubric["totals_uncapped"],
        "mean_total_uncapped": rubric["mean_total_uncapped"],
        "lenient_share_uncapped": _pass_share(rubric["totals_uncapped"], ers.PASS_LENIENT),
        "strict_share_uncapped": _pass_share(rubric["totals_uncapped"], ers.PASS_STRICT),
    }
    if category == "dessert":
        out["capped_reported"] = False
        out["capped_note"] = G_CAVEAT
    else:
        out["capped_reported"] = True
        out["totals_capped"] = rubric["totals_capped"]
        out["mean_total_capped"] = rubric["mean_total_capped"]
    if paired_all_top3 is not None:
        out["top3_same_as_paired_all"] = out["top3"] == paired_all_top3
    return out


def build_metrics(extra_top3: dict, paired_top3: dict, extra_set: dict, available: dict, provenance: dict) -> dict:
    """All metrics for the extra set. `available` maps a G query id to its full result count."""
    paired_by_id = {q["id"]: q for q in paired_top3["queries"]}
    f_rows, g_rows = [], []
    for q in extra_top3["queries"]:
        paired = paired_by_id.get(q.get("paired_with"))
        if q["group"] == "F":
            if paired is None:
                raise KeyError(f"{q['id']}: paired query {q.get('paired_with')} not found in the stored top-3")
            f_rows.append(f_pair_metrics(q, paired))
        elif q["group"] == "G":
            g_rows.append(g_query_metrics(q, available.get(q["id"]),
                                          [r["id"] for r in paired["results"]] if paired else None))
    rule = ers.compute(extra_top3)
    return {
        "provenance": provenance,
        "caveats": {"F": F_CAVEAT, "G": G_CAVEAT, "rubric": RUBRIC_CAVEAT},
        "F": {"queries": f_rows, "aggregate": f_aggregate(f_rows)},
        "G": {
            "queries": g_rows,
            "mean_category_leak_rate": _mean([r["category_leak_rate"] for r in g_rows]),
            "n_zero_results": sum(1 for r in g_rows if r["zero_results"]),
        },
        "zero_result_note": extra_set.get("notes", {}).get("zero_or_thin_category_results"),
        "rule_rubric_groups": {g: rule["groups"][g] for g in ("F", "G") if g in rule["groups"]},
    }


# ---------------------------------------------------------------------------
# Provenance, markdown
# ---------------------------------------------------------------------------

def provenance(inputs: list[str]) -> dict:
    """git HEAD, recipe count, category counts, rubric version and input file names (no network)."""
    import subprocess
    try:
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=20, check=True).stdout.strip() or "UNVERIFIED"
    except (OSError, subprocess.SubprocessError):
        head = "UNVERIFIED"
    recipes = _load_json(RECIPES_PATH)
    cats: dict = {}
    for r in recipes:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    return {"git_head": head, "recipes": len(recipes), "categories": cats,
            "RUBRIC_VERSION": ers.RUBRIC_VERSION, "inputs": inputs}


def to_markdown(m: dict) -> str:
    p = m["provenance"]
    L = ["# Extra test set (groups F and G): metrics", ""]
    w = L.append
    w(f"- git HEAD: `{p['git_head']}` (the working tree may hold uncommitted changes)")
    w(f"- recipes: {p['recipes']}; categories: {p['categories']}")
    w(f"- RUBRIC_VERSION: {p['RUBRIC_VERSION']}")
    w("- inputs: " + ", ".join(f"`{n}`" for n in p["inputs"]))
    w("- generated by `tools/eval_extra_metrics.py`; deterministic, no LLM, no network")
    w("")
    w("## Group F: seasonings ticked, versus the paired query without seasonings")
    w("")
    w(f"> {F_CAVEAT}")
    w("")
    w("| id | paired | seasonings | positions changed | items replaced | mean overlap without -> with | mean total (uncapped) without -> with |")
    w("|---|---|---|---|---|---|---|")
    for r in m["F"]["queries"]:
        w(f"| {r['id']} | {r['paired_with']} | {', '.join(r['seasonings'])} | {r['positions_changed']} "
          f"| {r['items_replaced']['count']} | {_f(r['mean_overlap_without'])} -> {_f(r['mean_overlap_with'])} "
          f"| {_f(r['rubric_without']['mean_total_uncapped'])} -> {_f(r['rubric_with']['mean_total_uncapped'])} |")
    a = m["F"]["aggregate"]
    w("")
    w(f"Aggregate over {a['n_pairs']} pairs: top-3 changed in {a['n_top3_changed']}; mean positions changed "
      f"{_f(a['mean_positions_changed'])}; mean items replaced {_f(a['mean_items_replaced'])}; mean overlap "
      f"{_f(a['mean_overlap_without'])} -> {_f(a['mean_overlap_with'])}; mean total (uncapped) "
      f"{_f(a['mean_total_uncapped_without'])} -> {_f(a['mean_total_uncapped_with'])}; mean total (capped) "
      f"{_f(a['mean_total_capped_without'])} -> {_f(a['mean_total_capped_with'])}.")
    w("")
    w("Top-3 ids and rank changes of surviving items:")
    w("")
    w("| id | without | with | dropped | added | surviving items that moved |")
    w("|---|---|---|---|---|---|")
    for r in m["F"]["queries"]:
        moved = "; ".join(f"{c['id']} {c['rank_without']}->{c['rank_with']}" for c in r["rank_changes_of_surviving_items"]) or "-"
        w(f"| {r['id']} | {', '.join(r['top3_without'])} | {', '.join(r['top3_with'])} "
          f"| {', '.join(r['items_replaced']['dropped']) or '-'} | {', '.join(r['items_replaced']['added']) or '-'} | {moved} |")
    w("")
    w(f"> {RUBRIC_CAVEAT}")
    w("")
    w("## Group G: category picker")
    w("")
    w(f"> {G_CAVEAT}")
    w("")
    w("| id | paired | category | results available | zero results | category leak rate | uncapped totals | mean total (uncapped) | capped mean | top-3 same as paired 'all' |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in m["G"]["queries"]:
        capped = _f(r["mean_total_capped"]) if r["capped_reported"] else "not reported (dessert)"
        w(f"| {r['id']} | {r['paired_with']} | {r['category']} | {r['results_available']} | {r['zero_results']} "
          f"| {_f(r['category_leak_rate'])} | {r['totals_uncapped']} | {_f(r['mean_total_uncapped'])} | {capped} "
          f"| {r.get('top3_same_as_paired_all')} |")
    w("")
    w(f"Mean category leak rate: {_f(m['G']['mean_category_leak_rate'])}; queries with zero results: {m['G']['n_zero_results']}.")
    w("")
    w("### Zero-result note (from the extra set)")
    w("")
    w(m["zero_result_note"] or "none")
    w("")
    w("## Rule-rubric group aggregates (F and G)")
    w("")
    w("These come from `tools/eval_rule_score.compute()` and are in `extra_v1_metrics.json` under `rule_rubric_groups`. "
      + RUBRIC_CAVEAT + " " + G_CAVEAT)
    w("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Helpers that call the recommender (lazy import, offline)
# ---------------------------------------------------------------------------

def count_available(queries: list[dict]) -> dict:
    """Full result count (not just the top 3) for each query, with the query's own seasonings and category."""
    import contextlib
    import io
    from recommender.recommend import load_recipes, recommend
    size = len(load_recipes())
    out = {}
    for q in queries:
        with contextlib.redirect_stdout(io.StringIO()):
            out[q["id"]] = len(recommend(
                ingredients=q["used_ingredients"], health_tags=q["health_tags"], excluded=q["excluded"],
                top_k=size, seasonings=q.get("seasonings") or None, category=q.get("category") or None))
    return out


def verify_pairs_against_recommender(paired_ids: list[str], draft_set: list[dict], stored_top3: dict) -> list[dict]:
    """Fresh recommender call for each paired existing query vs its stored top-3; returns the mismatches."""
    import contextlib
    import io
    from recommender.recommend import recommend
    stored = {q["id"]: q for q in stored_top3["queries"]}
    draft = {q["id"]: q for q in draft_set}
    mismatches = []
    for pid in paired_ids:
        used = stored[pid]["used_ingredients"]
        with contextlib.redirect_stdout(io.StringIO()):
            fresh = recommend(ingredients=used, health_tags=draft[pid]["health_tags"],
                              excluded=draft[pid]["excluded"], top_k=3, seasonings=[])
        fresh_ids = [d["id"] for d in fresh]
        stored_ids = [r["id"] for r in stored[pid]["results"]]
        stored_scores = [r["score"] for r in stored[pid]["results"]]
        fresh_scores = [d["score"] for d in fresh]
        if fresh_ids != stored_ids or fresh_scores != stored_scores:
            mismatches.append({"paired_id": pid, "stored": list(zip(stored_ids, stored_scores)),
                               "fresh": list(zip(fresh_ids, fresh_scores))})
    return mismatches


def main() -> None:
    import eval_dump_top3 as dump
    extra_set = _load_json(EXTRA_SET_PATH)
    extra_top3 = dump.dump(EXTRA_SET_PATH, OUT_TOP3)
    paired_top3 = _load_json(PAIRED_TOP3_PATH)
    paired_ids = sorted({q["paired_with"] for q in extra_top3["queries"]})
    mismatches = verify_pairs_against_recommender(paired_ids, _load_json(DRAFT_SET_PATH), paired_top3)
    if mismatches:
        print("WARNING: stored paired top-3 differ from a fresh recommender call:", mismatches)
    g = [q for q in extra_top3["queries"] if q["group"] == "G"]
    metrics = build_metrics(extra_top3, paired_top3, extra_set, count_available(g),
                            provenance([EXTRA_SET_PATH.name, PAIRED_TOP3_PATH.name, DRAFT_SET_PATH.name]))
    metrics["paired_consistency_mismatches"] = mismatches
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(to_markdown(metrics))
    print(f"wrote {OUT_TOP3.name}, {OUT_JSON.name}, {OUT_MD.name}")


if __name__ == "__main__":
    main()
