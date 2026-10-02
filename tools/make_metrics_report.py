"""
tools/make_metrics_report.py
============================
Writes data/eval/METRICS_REPORT.md: the rule-based recommender metrics in the capped AND
uncapped variants, with a plain explanation of what each one measures.

    python tools/make_metrics_report.py

Deterministic and offline. Nothing is recomputed: every number is read from files that
tools/eval_rule_score.py and tools/eval_dump_top3.py already wrote. No recommend() call, no
network, no LLM. Reads (never writes):
    data/eval/post_relabel_rule_metrics.json   new column
    data/eval/baseline_rule_metrics.json       old column (commit db8c153)
    data/eval/post_relabel_rule_metrics.md     header: git HEAD and recipe/category counts of that run
    data/eval/post_relabel_top3.json           what was actually returned (categories, call used)
    data/eval/test_set_draft_v1.json           the queries (only facts derived from them are reported)
Writes  data/eval/METRICS_REPORT.md

The report date is the commit date of the HEAD recorded in the stored run (via local `git show`),
not today's date, so the output does not change from run to run.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
EVAL = ROOT / "data" / "eval"
NEW_PATH = EVAL / "post_relabel_rule_metrics.json"
OLD_PATH = EVAL / "baseline_rule_metrics.json"
NEW_MD_PATH = EVAL / "post_relabel_rule_metrics.md"
TOP3_PATH = EVAL / "post_relabel_top3.json"
TEST_SET_PATH = EVAL / "test_set_draft_v1.json"
OUT_PATH = EVAL / "METRICS_REPORT.md"

OLD_COMMIT = "db8c153"
VARIANTS = ("total_capped", "total_uncapped", "total_system_violation_only")
PASS_LINES = (("lenient", ">= 3"), ("strict", ">= 4"))
GROUPS = ("A", "B", "C", "D", "E")
RULE_FILE = "tools/eval_rule_score.py"


def _load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _f(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


# ---------------------------------------------------------------------------
# Provenance of the stored run
# ---------------------------------------------------------------------------

def read_run_header(md_path: Path = NEW_MD_PATH) -> dict:
    """HEAD, recipe count and category counts, as recorded in the stored post-relabel .md header."""
    out = {"head": "UNVERIFIED", "recipes": "UNVERIFIED", "categories": "UNVERIFIED"}
    if not md_path.exists():
        return out
    text = md_path.read_text(encoding="utf-8")
    m = re.search(r"git HEAD: `([0-9a-f]+)`", text)
    if m:
        out["head"] = m.group(1)
    m = re.search(r"recipes: (\d+); categories: (\{.*?\})", text)
    if m:
        out["recipes"] = int(m.group(1))
        try:
            out["categories"] = ast.literal_eval(m.group(2))
        except (ValueError, SyntaxError):
            pass
    return out


def commit_date(head: str) -> str:
    """Commit date of `head` from the local repo; UNVERIFIED if git or the commit is unavailable."""
    if head == "UNVERIFIED":
        return "UNVERIFIED"
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "show", "-s", "--format=%cd", "--date=short", head],
                             capture_output=True, text=True, timeout=20, check=True)
        return out.stdout.strip() or "UNVERIFIED"
    except (OSError, subprocess.SubprocessError):
        return "UNVERIFIED"


# ---------------------------------------------------------------------------
# Facts derived from the stored query and result files
# ---------------------------------------------------------------------------

def group_facts(test_set: list[dict], top3: dict) -> dict:
    """Per group: query ids and plain counts taken from the test set and the stored top-3."""
    facts = {}
    returned = {q["id"]: q["results"] for q in top3["queries"]}
    for g in GROUPS:
        qs = [q for q in test_set if q["id"].startswith(g)]
        if not qs:
            continue
        sizes = [len(q["ingredients"]) for q in qs]
        items = [r for q in qs for r in returned.get(q["id"], [])]
        facts[g] = {
            "ids": [q["id"] for q in qs],
            "min_ing": min(sizes), "max_ing": max(sizes),
            "with_tags": sum(1 for q in qs if q["health_tags"]),
            "with_excluded": sum(1 for q in qs if q["excluded"]),
            "returned": len(items),
            "returned_dessert": sum(1 for r in items if r["category"] == "dessert"),
        }
    return facts


def returned_categories(top3: dict) -> dict:
    counts: dict = {}
    for q in top3["queries"]:
        for r in q["results"]:
            counts[r["category"]] = counts.get(r["category"], 0) + 1
    return dict(sorted(counts.items()))


def identical(new: dict, old: dict) -> bool:
    """True if the overall and per-group variant numbers match to the stored precision."""
    if new["overall"] != old["overall"]:
        return False
    return all(new["groups"][g]["variants"] == old["groups"][g]["variants"] for g in new["groups"])


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _headline_rows(new: dict, old: dict) -> list[str]:
    lines = ["| variant | pass line | P@3 old | P@3 new | Hit@3 old | Hit@3 new | mean total old | mean total new |",
             "|---|---|---|---|---|---|---|---|"]
    for v in VARIANTS:
        o, n = old["overall"]["variants"][v], new["overall"]["variants"][v]
        for name, rule in PASS_LINES:
            lines.append(
                f"| {v} | {name} ({rule[:2]} {rule[3:]}) | {_f(o[name]['precision_at_3'])} | {_f(n[name]['precision_at_3'])} "
                f"| {_f(o[name]['hit_at_3'])} | {_f(n[name]['hit_at_3'])} | {_f(o['mean_total'])} | {_f(n['mean_total'])} |")
    return lines


def _group_rows(new: dict, old: dict, variant: str) -> list[str]:
    lines = ["| group | queries | lenient P@3 old | new | lenient Hit@3 old | new "
             "| strict P@3 old | new | strict Hit@3 old | new |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for g in GROUPS:
        if g not in new["groups"]:
            continue
        o, n = old["groups"][g]["variants"][variant], new["groups"][g]["variants"][variant]
        lines.append(
            f"| {g} | {new['groups'][g]['n_queries']} "
            f"| {_f(o['lenient']['precision_at_3'])} | {_f(n['lenient']['precision_at_3'])} "
            f"| {_f(o['lenient']['hit_at_3'])} | {_f(n['lenient']['hit_at_3'])} "
            f"| {_f(o['strict']['precision_at_3'])} | {_f(n['strict']['precision_at_3'])} "
            f"| {_f(o['strict']['hit_at_3'])} | {_f(n['strict']['hit_at_3'])} |")
    return lines


def build_report(new: dict, old: dict, header: dict, date: str, test_set: list[dict], top3: dict) -> str:
    c = new["constants"]
    facts = group_facts(test_set, top3)
    cats_returned = returned_categories(top3)
    ind, old_ind = new["overall"]["independent"], old["overall"]["independent"]
    same = identical(new, old)
    ge_cap = new["groups"]["E"]["variants"]["total_capped"]
    ge_unc = new["groups"]["E"]["variants"]["total_uncapped"]
    sizes = ", ".join(f"{g}={len(facts[g]['ids'])}" for g in GROUPS if g in facts)
    mismatches = new["differing_violations"]
    nonsav = {k: v for k, v in cats_returned.items() if k not in ("savory", "dessert")}

    L: list[str] = []
    w = L.append

    w("# Recommender rule-based metrics: capped and uncapped")
    w("")
    w(f"- git HEAD of the stored run: `{header['head']}` (commit date {date})")
    w(f"- recipes: {header['recipes']}; categories: {header['categories']}")
    w(f"- test set: `data/eval/test_set_draft_v1.json`, {new['overall']['n_queries']} queries, groups A-E ({sizes}); "
      f"{ind['total_items']} items returned in total")
    w("- generated by `tools/make_metrics_report.py` from the stored JSON; nothing is recomputed and `recommend()` is not run")
    w("")

    w("## 1. How to read these numbers")
    w("")
    w("Definitions come from `tools/eval_rule_score.py` (line numbers are for that file).")
    w("")
    w("| term | meaning | where |")
    w("|---|---|---|")
    w("| item total | A + B + C for one returned recipe | `score_recipe` `:105-120` |")
    w(f"| A | {c['A_POINTS_MAIN']} if a user ingredient is a MAIN ingredient, {c['A_POINTS_OPTIONAL_ONLY']} if only an OPTIONAL one, else 0 | `points_a` `:80-86` |")
    w(f"| B | {c['B_POINTS_ALL_HAVE']} if no main ingredient is missing, {c['B_POINTS_PARTIAL']} if the missing share of mains is <= {c['B_PARTIAL_SHARE']}, else 0 | `points_b` `:89-98` |")
    w(f"| C | {c['C_POINTS_DESSERT']} if `category == \"dessert\"`, else {c['C_POINTS_NON_DESSERT']} (snack, drink, condiment and savory all get {c['C_POINTS_NON_DESSERT']}) | `points_c` `:101-102` |")
    w(f"| lenient / strict | an item passes if its total is >= {c['PASS_LENIENT']} / >= {c['PASS_STRICT']} | `:54-55` |")
    w("| P@3 | passing items / items returned, per query, then the mean over queries. Queries that returned nothing are skipped | `query_metrics` `:161`, `aggregate` `:196` |")
    w("| Hit@3 | 1 if at least one item passes, else 0. Every query counts; an empty result is a miss | `query_metrics` `:162`, `aggregate` `:197` |")
    w("| mean total | mean of the item totals of the chosen variant, per query, then over queries | `query_metrics` `:156`, `aggregate` `:193` |")
    w("| coverage | distinct recipes returned / catalog size | `aggregate` `:206` |")
    w("| dessert share | dessert items / returned items (pooled, and mean per query) | `query_metrics` `:174`, `aggregate` `:209-210` |")
    w("| diversity | mean pairwise Jaccard distance of main + optional ingredient sets within one top-3 | `diversity` `:137-142` |")
    w("| system violations | returned items whose health tag or hard-excluded ingredient breaks the system's own filter | `violations` `:67-77`, count at `:253` |")
    w("")
    w("### The three variants")
    w("")
    w("Each variant is the same A + B + C total with a different cap or violation rule (`score_recipe` `:105-120`).")
    w("")
    w("| variant | what it does |")
    w("|---|---|")
    w(f"| `total_capped` | 0 if `violation_with_optional` (an excluded ingredient anywhere, optional included, or a tag problem); otherwise A+B+C, and a dessert's total is capped at {c['DESSERT_TOTAL_CAP']} |")
    w("| `total_uncapped` | 0 if `violation_with_optional`; otherwise A+B+C, never capped |")
    w(f"| `total_system_violation_only` | like `total_capped`, but zeroed only by `violation_system_rule` (excluded ingredient in main or seasonings, or a tag problem), which is what `recommend()` itself enforces (`recommender/recommend.py:162-169`) |")
    w("")
    w("### What capped and uncapped answer")
    w("")
    w(f"- **Capped** answers: *are the returned items non-dessert, and do they match the user's ingredients?* It applies to every returned dessert whatever the query was about: `points_c` takes no query input, so a dessert-oriented query is penalised the same way.")
    w("- **Uncapped** answers: *how well do the returned items overlap the user's ingredients (A, B), with one point less for a dessert (C)?* It is the better available proxy for ingredient match, but it is not pure match quality: C still costs a dessert one point and a violation still zeroes an item.")
    w(f"- **Why a capped dessert can never pass:** `DESSERT_TOTAL_CAP = {c['DESSERT_TOTAL_CAP']}` is below both pass lines (lenient >= {c['PASS_LENIENT']}, strict >= {c['PASS_STRICT']}). Any dessert has C = 0 and its total is cut to at most {c['DESSERT_TOTAL_CAP']}, so it fails capped lenient and capped strict whatever its ingredient match. Uncapped, a dessert can reach 4 (A 2 + B 2 + C 0), so it can pass both lines.")
    w("- Consequence: a low capped number for a dessert-heavy group describes the rubric's cap, not the recommender's matching.")
    w("")

    w("## 2. Headline: all three variants, old vs post-relabel")
    w("")
    w(f"Old = commit `{OLD_COMMIT}` (2-value category, `data/eval/baseline_rule_metrics.json`). New = the stored post-relabel run at `{header['head']}`.")
    w("")
    L.extend(_headline_rows(new, old))
    w("")
    if same:
        w("**Old and new are identical** in every variant and group. `data/eval/post_relabel_comparison.md` records why: the top-3 ids did not change for any of the 30 queries, and none of the 25 recipes whose category changed was returned.")
    else:
        w("**Old and new differ.** See `data/eval/post_relabel_comparison.md`; this report does not explain the difference.")
    w("")

    w("## 3. Per group")
    w("")
    w("### total_capped")
    w("")
    L.extend(_group_rows(new, old, "total_capped"))
    w("")
    w("### total_uncapped")
    w("")
    L.extend(_group_rows(new, old, "total_uncapped"))
    w("")
    w("### total_system_violation_only (capped)")
    w("")
    L.extend(_group_rows(new, old, "total_system_violation_only"))
    w("")
    w("What each group contains, derived only from `test_set_draft_v1.json` and `post_relabel_top3.json`. The test set stores no description or intent per group (its fields are `id`, `text_th`, `ingredients`, `health_tags`, `excluded`, `preview_top3`), so what a group is meant to test is **UNVERIFIED**.")
    w("")
    w("| group | query ids | ingredients per query | queries with health tags | queries with exclusions | dessert items returned |")
    w("|---|---|---|---|---|---|")
    for g in GROUPS:
        if g not in facts:
            continue
        x = facts[g]
        rng = str(x["min_ing"]) if x["min_ing"] == x["max_ing"] else f"{x['min_ing']}-{x['max_ing']}"
        w(f"| {g} | {', '.join(x['ids'])} | {rng} | {x['with_tags']} of {len(x['ids'])} | {x['with_excluded']} of {len(x['ids'])} | {x['returned_dessert']} of {x['returned']} |")
    w("")
    w(f"**Group E, the case that prompted this report:** capped lenient P@3 {_f(ge_cap['lenient']['precision_at_3'])} / Hit@3 {_f(ge_cap['lenient']['hit_at_3'])}; "
      f"uncapped lenient P@3 {_f(ge_unc['lenient']['precision_at_3'])} / Hit@3 {_f(ge_unc['lenient']['hit_at_3'])}. "
      f"The capped figure must not be quoted as a match-quality score; the gap between the two is the cap.")
    w("")

    w("## 4. Other metrics")
    w("")
    w("These do not depend on the variant.")
    w("")
    w("| metric | old | new |")
    w("|---|---|---|")
    w(f"| catalog coverage | {_f(old_ind['catalog_coverage'])} ({old_ind['distinct_recipes']}/{old_ind['catalog_size']}) | {_f(ind['catalog_coverage'])} ({ind['distinct_recipes']}/{ind['catalog_size']}) |")
    w(f"| intra-list diversity (mean Jaccard distance) | {_f(old_ind['intra_list_diversity_mean'])} | {_f(ind['intra_list_diversity_mean'])} |")
    w(f"| dessert share, pooled | {_f(old_ind['dessert_share_pooled'])} ({old_ind['dessert_items']}/{old_ind['total_items']}) | {_f(ind['dessert_share_pooled'])} ({ind['dessert_items']}/{ind['total_items']}) |")
    w(f"| dessert share, mean per query | {_f(old_ind['dessert_share_mean_per_query'])} | {_f(ind['dessert_share_mean_per_query'])} |")
    w(f"| mean system score of returned items | {_f(old_ind['mean_system_score'])} | {_f(ind['mean_system_score'])} |")
    w(f"| system rule violations in returned items | {old['system_rule_violations_in_returned_items']} | {new['system_rule_violations_in_returned_items']} |")
    w("")
    w(f"Queries with fewer than 3 results: {new['overall']['n_queries_short']}; with none: {new['overall']['n_queries_empty']}.")
    w("")

    w("## 5. Known limitations of this evaluation")
    w("")
    w(f"1. **Rubric constants are self-defined.** Every constant (A, B, C points, `B_PARTIAL_SHARE`, `DESSERT_TOTAL_CAP`, both pass lines, `TOP_K`) is commented \"definition we chose\" in `{RULE_FILE}:44-56`; none is derived from data. The stored `constants` block says the same.")
    w("2. **Draft test set, no human gold set.** `data/eval/test_set_draft_v1.json` has 30 queries. Its `preview_top3` field came from an external simulation and is ignored. No human relevance labels exist, so the rubric measures ingredient overlap, not whether a dish is a good answer.")
    meta = top3["meta"]
    w(f"3. **Category picker and seasoning weight are not exercised.** The stored call is `{meta['call']}`: no `category` argument (default `all`) and `seasonings_ticked` = {meta['seasonings_ticked']}. So the category choice and `SEASONING_WEIGHT` have no effect on these numbers.")
    if nonsav:
        w(f"4. **Snack and drink escape the dessert penalty** (`points_c` `:101-102` gives them C = 1 and the cap only applies when C = 0). In the stored top-3 files, categories returned are {cats_returned}, so some non-savory, non-dessert items were returned and their totals are not capped.")
    else:
        w(f"4. **Snack and drink escape the dessert penalty** (`points_c` `:101-102` gives them C = 1, and the cap only applies when C = 0). In the stored top-3 file the returned categories are {cats_returned}: no snack, drink or condiment was returned, so this has no effect on the stored numbers. It would matter if the test set were extended.")
    if mismatches:
        listed = "; ".join(f"{d['query']} rank {d['rank']} recipe {d['recipe_id']}" for d in mismatches)
        w(f"5. **Violation rule mismatch.** `recommend()` drops a dish only for an excluded ingredient in main or seasonings (`recommender/recommend.py:162-169`), but the capped and uncapped variants zero any item with the excluded ingredient even only in optional (`violation_with_optional`, `{RULE_FILE}:76`). The stored `differing_violations` lists {len(mismatches)} such returned item(s): {listed}. They score 0 in `total_capped` and `total_uncapped`, but not in `total_system_violation_only`.")
    else:
        w("5. **Violation rule mismatch.** None in the returned items of the stored run, although the two rules differ in the code (`eval_rule_score.py:76` vs `recommender/recommend.py:162-169`).")
    w("6. **No LLM-as-judge result exists.** The rubric is deterministic code only. `tools/eval_rule_score.py` describes itself as the deterministic half, and no judged half exists in the repo.")
    w("")

    w("## 6. How to quote these numbers")
    w("")
    w("- Always give the variant **and** the pass line, for example \"total_uncapped, lenient, P@3 0.967\". Never write just \"P@3\".")
    w("- Never describe a capped P@3 as match quality. For ingredient match quote `total_uncapped`; for \"dessert items do not pass\" quote `total_capped` and say that the cap forces it.")
    w("- Never quote a capped lenient or strict figure for a group that mostly returns desserts (Group E) without the uncapped figure next to it.")
    w("- Say these are self-defined rubric scores on a 30-query draft set with no human labels, not accuracy or user satisfaction.")
    w("- Cite the stored file (`data/eval/post_relabel_rule_metrics.json`) and the commit, and do not mix the old (`db8c153`) and new numbers without saying which is which.")
    w("")
    return "\n".join(L)


def generate() -> str:
    header = read_run_header()
    return build_report(
        new=_load(NEW_PATH),
        old=_load(OLD_PATH),
        header=header,
        date=commit_date(header["head"]),
        test_set=_load(TEST_SET_PATH),
        top3=_load(TOP3_PATH),
    )


def main() -> None:
    text = generate()
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
