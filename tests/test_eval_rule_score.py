"""
tests/test_eval_rule_score.py
=============================
Hand-made recipes exercising every branch of the deterministic rubric in
tools/eval_rule_score.py. No data files, no recommender, no LLM.

Run with:
    pytest tests/test_eval_rule_score.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import eval_rule_score as ers


def recipe(main=("egg",), optional=(), seasonings=(), health_tags=(), excluded_for=(), category="savory"):
    return {
        "main_ingredients": list(main),
        "optional_ingredients": list(optional),
        "seasonings": list(seasonings),
        "health_tags": list(health_tags),
        "excluded_for": list(excluded_for),
        "category": category,
    }


def query(ingredients=("egg",), health_tags=(), excluded=()):
    return {"ingredients": list(ingredients), "health_tags": list(health_tags), "excluded": list(excluded)}


# ---------------------------------------------------------------------------
# violations
# ---------------------------------------------------------------------------

def test_excluded_ingredient_only_in_optional_is_a_violation_only_with_optional():
    r = recipe(main=["egg"], optional=["chili"])
    system, with_optional = ers.violations(r, query(excluded=["chili"]))
    assert (system, with_optional) == (False, True)


def test_excluded_ingredient_in_main_or_seasonings_violates_both_rules():
    assert ers.violations(recipe(main=["egg", "pork"]), query(excluded=["pork"])) == (True, True)
    assert ers.violations(recipe(seasonings=["fish_sauce"]), query(excluded=["fish_sauce"])) == (True, True)


def test_requested_tag_missing_from_the_recipe_violates_both_rules():
    assert ers.violations(recipe(health_tags=["clean"]), query(health_tags=["keto"])) == (True, True)


def test_requested_tag_in_excluded_for_violates_both_rules():
    r = recipe(health_tags=["vegan"], excluded_for=["vegan"])   # contradictory data: the redundant guard still fires
    assert ers.violations(r, query(health_tags=["vegan"])) == (True, True)


def test_no_violation_when_tags_are_present_and_nothing_excluded_is_used():
    assert ers.violations(recipe(health_tags=["keto", "clean"]), query(health_tags=["keto"])) == (False, False)


def test_all_requested_tags_must_be_present():
    r = recipe(health_tags=["keto"])
    assert ers.violations(r, query(health_tags=["keto", "clean"])) == (True, True)


# ---------------------------------------------------------------------------
# A / B / C
# ---------------------------------------------------------------------------

def test_a_is_2_for_a_main_match_1_for_optional_only_0_otherwise():
    assert ers.points_a(recipe(main=["egg"], optional=["tomato"]), query(ingredients=["egg"])) == 2
    assert ers.points_a(recipe(main=["egg"], optional=["tomato"]), query(ingredients=["tomato"])) == 1
    assert ers.points_a(recipe(main=["egg"], optional=["tomato"]), query(ingredients=["pork"])) == 0


def test_a_main_match_wins_over_an_optional_match():
    assert ers.points_a(recipe(main=["egg"], optional=["tomato"]), query(ingredients=["egg", "tomato"])) == 2


def test_b_is_2_when_every_main_ingredient_is_present():
    assert ers.points_b(recipe(main=["egg", "tomato"]), query(ingredients=["egg", "tomato", "rice"])) == 2


def test_b_at_exactly_50_percent_missing_is_1():
    assert ers.points_b(recipe(main=["egg", "tomato"]), query(ingredients=["egg"])) == 1          # 1/2 missing
    assert ers.points_b(recipe(main=["a", "b", "c", "d"]), query(ingredients=["a", "b"])) == 1    # 2/4 missing


def test_b_over_50_percent_missing_is_0():
    assert ers.points_b(recipe(main=["a", "b", "c"]), query(ingredients=["a"])) == 0              # 2/3 missing
    assert ers.points_b(recipe(main=["egg"]), query(ingredients=["pork"])) == 0                    # everything missing


def test_c_is_0_for_dessert_and_1_otherwise():
    assert ers.points_c(recipe(category="dessert")) == 0
    assert ers.points_c(recipe(category="savory")) == 1


# ---------------------------------------------------------------------------
# totals
# ---------------------------------------------------------------------------

def test_full_marks_savory_total_is_5_in_every_variant():
    s = ers.score_recipe(recipe(main=["egg"]), query(ingredients=["egg"]))
    assert (s["A"], s["B"], s["C"]) == (2, 2, 1)
    assert s["total_capped"] == s["total_uncapped"] == s["total_system_violation_only"] == 5


def test_dessert_cap_applies_to_capped_and_system_only_but_not_to_uncapped():
    s = ers.score_recipe(recipe(main=["banana"], category="dessert"), query(ingredients=["banana"]))
    assert (s["A"], s["B"], s["C"]) == (2, 2, 0)
    assert s["total_uncapped"] == 4
    assert s["total_capped"] == 2
    assert s["total_system_violation_only"] == 2


def test_dessert_below_the_cap_is_not_raised():
    s = ers.score_recipe(recipe(main=["a", "b", "c"], category="dessert"), query(ingredients=["a"]))
    assert (s["A"], s["B"], s["C"]) == (2, 0, 0)
    assert s["total_capped"] == s["total_uncapped"] == 2


def test_a_1_case_totals():
    s = ers.score_recipe(recipe(main=["egg"], optional=["tomato"]), query(ingredients=["tomato"]))
    assert (s["A"], s["B"], s["C"]) == (1, 0, 1)
    assert s["total_capped"] == 2


def test_v1_optional_only_violation_zeroes_the_totals_but_not_the_system_only_variant():
    """Pins the ORIGINAL rubric (v1), which stays selectable so the old results remain reproducible."""
    r = recipe(main=["egg"], optional=["chili"])
    s = ers.score_recipe(r, query(ingredients=["egg"], excluded=["chili"]), rubric_version="v1")
    assert s["violation_system_rule"] is False and s["violation_with_optional"] is True
    assert s["total_capped"] == 0 and s["total_uncapped"] == 0
    assert s["total_system_violation_only"] == 5


# --- rubric v2 (default): an excluded ingredient that is only optional is not a violation ---

def test_v2_is_the_default_rubric_version():
    assert ers.RUBRIC_VERSION == "v2"
    assert ers.RUBRIC_VERSIONS == ("v1", "v2")
    r, q = recipe(main=["egg"], optional=["chili"]), query(ingredients=["egg"], excluded=["chili"])
    assert ers.score_recipe(r, q) == ers.score_recipe(r, q, rubric_version="v2")


def test_v2_excluded_ingredient_only_optional_is_not_zeroed():
    r = recipe(main=["egg"], optional=["chili"])
    s = ers.score_recipe(r, query(ingredients=["egg"], excluded=["chili"]), rubric_version="v2")
    assert s["violation_system_rule"] is False and s["violation_with_optional"] is True   # flags unchanged
    assert s["total_capped"] == s["total_uncapped"] == s["total_system_violation_only"] == 5


def test_v2_excluded_ingredient_as_main_is_zeroed():
    s = ers.score_recipe(recipe(main=["egg", "pork"]), query(ingredients=["egg"], excluded=["pork"]),
                         rubric_version="v2")
    assert s["total_capped"] == s["total_uncapped"] == s["total_system_violation_only"] == 0


def test_v2_excluded_ingredient_as_seasoning_is_zeroed():
    s = ers.score_recipe(recipe(main=["egg"], seasonings=["fish_sauce"]),
                         query(ingredients=["egg"], excluded=["fish_sauce"]), rubric_version="v2")
    assert s["total_capped"] == s["total_uncapped"] == s["total_system_violation_only"] == 0


def test_v2_health_tag_violation_still_zeroes():
    s = ers.score_recipe(recipe(main=["egg"], health_tags=["clean"]),
                         query(ingredients=["egg"], health_tags=["keto"]), rubric_version="v2")
    assert s["total_capped"] == s["total_uncapped"] == s["total_system_violation_only"] == 0


def test_v2_optional_only_dessert_is_still_capped_but_not_zeroed():
    r = recipe(main=["banana"], optional=["chili"], category="dessert")
    s = ers.score_recipe(r, query(ingredients=["banana"], excluded=["chili"]), rubric_version="v2")
    assert s["total_uncapped"] == 4 and s["total_capped"] == 2


def test_the_module_constant_switches_the_rubric(monkeypatch):
    r, q = recipe(main=["egg"], optional=["chili"]), query(ingredients=["egg"], excluded=["chili"])
    monkeypatch.setattr(ers, "RUBRIC_VERSION", "v1")
    assert ers.score_recipe(r, q)["total_capped"] == 0
    monkeypatch.setattr(ers, "RUBRIC_VERSION", "v2")
    assert ers.score_recipe(r, q)["total_capped"] == 5


def test_an_unknown_rubric_version_raises():
    with pytest.raises(ValueError):
        ers.score_recipe(recipe(), query(), rubric_version="v3")


def test_compute_records_the_rubric_version():
    q = baseline_query("D1", [result(1, "r1", main=["egg"], optional=["chili"])], ingredients=["egg"], excluded=["chili"])
    out = ers.compute({"meta": {"catalog_size": 400}, "queries": [q]})
    assert out["constants"]["RUBRIC_VERSION"] == "v2"
    assert out["queries"][0]["variants"]["total_capped"]["totals"] == [5]


def test_a_system_rule_violation_zeroes_every_variant():
    s = ers.score_recipe(recipe(main=["egg", "pork"]), query(ingredients=["egg"], excluded=["pork"]))
    assert s["total_capped"] == s["total_uncapped"] == s["total_system_violation_only"] == 0


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def baseline_query(qid, results, **q):
    base = query(**q)
    return {"id": qid, "group": qid[0], **base, "results": results}


def result(rank, rec_id, **kwargs):
    return {"rank": rank, "id": rec_id, "name_th": rec_id, "score": 0.5, **recipe(**kwargs)}


def test_empty_result_is_kept_as_a_miss_with_no_precision():
    row = ers.query_metrics(baseline_query("A1", []))
    assert row["empty"] and row["short"] and row["n_returned"] == 0
    line = row["variants"]["total_capped"]["lenient"]
    assert line["precision_at_3"] is None and line["hit_at_3"] == 0
    assert row["dessert_share"] is None and row["diversity"] is None


def test_precision_divides_by_the_number_returned_for_a_short_list():
    row = ers.query_metrics(baseline_query("A1", [result(1, "r1", main=["egg"])], ingredients=["egg"]))
    assert row["short"] and not row["empty"]
    line = row["variants"]["total_capped"]["lenient"]
    assert line["passing"] == 1 and line["precision_at_3"] == 1.0 and line["hit_at_3"] == 1


def test_pass_lines_are_inclusive():
    # total 3 = A2 + B0 + C1: passes lenient (>=3) but not strict (>=4)
    r = result(1, "r1", main=["egg", "a", "b"])
    row = ers.query_metrics(baseline_query("A1", [r], ingredients=["egg"]))
    v = row["variants"]["total_capped"]
    assert v["totals"] == [3]
    assert v["lenient"]["passing"] == 1 and v["strict"]["passing"] == 0


def test_aggregate_skips_empty_queries_in_precision_but_counts_them_in_hit():
    hit = baseline_query("A1", [result(1, "r1", main=["egg"])], ingredients=["egg"])
    empty = baseline_query("A2", [])
    rows = [ers.query_metrics(hit), ers.query_metrics(empty)]
    agg = ers.aggregate(rows, hit["results"], catalog_size=400)
    line = agg["variants"]["total_capped"]["lenient"]
    assert line["precision_at_3"] == 1.0        # only the non-empty query
    assert line["hit_at_3"] == 0.5              # both queries; the empty one is a miss
    assert agg["n_queries_empty"] == 1 and agg["n_queries_in_precision_mean"] == 1


def test_diversity_is_mean_pairwise_jaccard_distance_of_main_plus_optional():
    same = [result(1, "r1", main=["a", "b"]), result(2, "r2", main=["a", "b"])]
    disjoint = [result(1, "r1", main=["a"]), result(2, "r2", main=["b"])]
    assert ers.diversity(same) == 0.0
    assert ers.diversity(disjoint) == 1.0
    assert ers.diversity([result(1, "r1", main=["a"])]) is None
    half = [result(1, "r1", main=["a", "b"]), result(2, "r2", main=["b", "c"])]      # |inter|=1, |union|=3
    assert ers.diversity(half) == pytest.approx(1 - 1 / 3, abs=1e-4)


def test_coverage_and_dessert_share():
    q = baseline_query("A1", [result(1, "r1", main=["egg"]), result(2, "r2", main=["egg"], category="dessert")],
                       ingredients=["egg"])
    row = ers.query_metrics(q)
    agg = ers.aggregate([row], q["results"], catalog_size=400)
    assert row["dessert_share"] == 0.5
    assert agg["independent"]["distinct_recipes"] == 2
    assert agg["independent"]["catalog_coverage"] == 0.005


def test_differing_violations_lists_optional_only_cases():
    q = baseline_query("D1", [result(1, "r1", main=["egg"], optional=["chili"])], ingredients=["egg"], excluded=["chili"])
    out = ers.differing_violations([ers.query_metrics(q)])
    assert [(d["query"], d["recipe_id"]) for d in out] == [("D1", "r1")]


# ---------------------------------------------------------------------------
# groups F and G (the extra test set) appear only when such queries exist
# ---------------------------------------------------------------------------

def _group_baseline(*group_letters):
    queries = [
        baseline_query(f"{g}1", [result(1, f"r{g}", main=["egg"])], ingredients=["egg"])
        for g in group_letters
    ]
    return {"meta": {"catalog_size": 400}, "queries": queries}


def test_groups_include_f_and_g():
    assert ers.GROUPS == ("A", "B", "C", "D", "E", "F", "G")


def test_f_and_g_appear_in_the_group_table_when_present():
    out = ers.compute(_group_baseline("A", "F", "G"))
    assert list(out["groups"]) == ["A", "F", "G"]
    md = ers.to_markdown(out)
    assert "## Group F" in md and "## Group G" in md and "## Group A" in md


def test_f_and_g_are_absent_when_only_a_to_e_are_present():
    out = ers.compute(_group_baseline("A", "B", "C", "D", "E"))
    assert list(out["groups"]) == ["A", "B", "C", "D", "E"]
    md = ers.to_markdown(out)
    assert "## Group F" not in md and "## Group G" not in md


def test_a_group_with_no_queries_is_not_listed():
    out = ers.compute(_group_baseline("F"))
    assert list(out["groups"]) == ["F"]
