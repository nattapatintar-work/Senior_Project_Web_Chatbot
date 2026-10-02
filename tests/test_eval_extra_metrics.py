"""
tests/test_eval_extra_metrics.py
================================
Offline tests for tools/eval_extra_metrics.py (group F / G metrics) and for the per-query
seasonings/category support in tools/eval_dump_top3.py. Tiny synthetic data; the real
recommender is never called.

Run with:
    pytest tests/test_eval_extra_metrics.py -v
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import eval_dump_top3 as dump
import eval_extra_metrics as xm
import eval_rule_score as ers


def row(rid, main=("egg",), optional=(), seasonings=(), category="savory", rank=1):
    return {
        "rank": rank, "id": rid, "name_th": rid, "score": 0.5, "category": category,
        "main_ingredients": list(main), "optional_ingredients": list(optional),
        "seasonings": list(seasonings), "health_tags": [], "excluded_for": [],
    }


def query(qid, results, ingredients=("egg",), **extra):
    return {"id": qid, "group": qid[0], "ingredients": list(ingredients), "health_tags": [], "excluded": [],
            "results": results, **extra}


# ---------------------------------------------------------------------------
# overlap (recommend.py:306-313)
# ---------------------------------------------------------------------------

def test_seasoning_overlap_is_the_share_of_the_recipes_seasonings_that_were_ticked():
    assert xm.seasoning_overlap(["sugar", "soy_sauce"], ["sugar"]) == 0.5
    assert xm.seasoning_overlap(["sugar", "soy_sauce"], ["sugar", "soy_sauce", "salt"]) == 1.0
    assert xm.seasoning_overlap(["sugar"], ["salt"]) == 0.0


def test_seasoning_overlap_is_zero_for_a_recipe_without_seasonings():
    assert xm.seasoning_overlap([], ["sugar"]) == 0.0


def test_mean_overlap_averages_the_items():
    items = [row("a", seasonings=["sugar"]), row("b", seasonings=["sugar", "salt"]), row("c", seasonings=[])]
    assert xm.mean_overlap(items, ["sugar"]) == round((1.0 + 0.5 + 0.0) / 3, 4)


# ---------------------------------------------------------------------------
# changed positions, replaced items, rank changes
# ---------------------------------------------------------------------------

def test_positions_changed_counts_rank_positions_with_a_different_id():
    assert xm.positions_changed(["a", "b", "c"], ["a", "b", "c"]) == 0
    assert xm.positions_changed(["a", "b", "c"], ["a", "c", "b"]) == 2
    assert xm.positions_changed(["a", "b", "c"], ["a", "b", "d"]) == 1
    assert xm.positions_changed(["a", "b", "c"], ["x", "y", "z"]) == 3


def test_positions_changed_counts_a_shorter_list_as_changed_positions():
    assert xm.positions_changed(["a", "b", "c"], ["a", "b"]) == 1


def test_items_replaced_is_the_set_difference_not_the_position_count():
    out = xm.items_replaced(["a", "b", "c"], ["a", "c", "b"])
    assert out == {"count": 0, "dropped": [], "added": []}        # reordered only
    out = xm.items_replaced(["a", "b", "c"], ["b", "c", "d"])
    assert out == {"count": 1, "dropped": ["a"], "added": ["d"]}


def test_rank_changes_lists_surviving_items_whose_rank_moved():
    assert xm.rank_changes(["a", "b", "c"], ["b", "a", "d"]) == [
        {"id": "a", "rank_without": 1, "rank_with": 2},
        {"id": "b", "rank_without": 2, "rank_with": 1},
    ]
    assert xm.rank_changes(["a", "b", "c"], ["a", "b", "c"]) == []


# ---------------------------------------------------------------------------
# group F pair metrics
# ---------------------------------------------------------------------------

def test_f_pair_metrics_compare_the_with_and_without_lists():
    without = query("A2", [row("r1", seasonings=["salt"], rank=1), row("r2", seasonings=["salt"], rank=2),
                           row("r3", seasonings=["salt"], rank=3)])
    with_ = query("F1", [row("r2", seasonings=["sugar"], rank=1), row("r1", seasonings=["salt"], rank=2),
                         row("r4", seasonings=["sugar"], rank=3)], seasonings=["sugar"], paired_with="A2")
    m = xm.f_pair_metrics(with_, without)
    assert m["top3_changed"] is True
    assert m["positions_changed"] == 3
    assert m["items_replaced"] == {"count": 1, "dropped": ["r3"], "added": ["r4"]}
    assert {c["id"] for c in m["rank_changes_of_surviving_items"]} == {"r1", "r2"}
    assert m["mean_overlap_without"] == 0.0 and m["mean_overlap_with"] == round(2 / 3, 4)
    assert m["mean_overlap_delta"] == round(2 / 3, 4)
    assert m["paired_with"] == "A2"


def test_f_pair_metrics_rubric_totals_use_the_existing_scoring():
    without = query("A2", [row("r1", main=["egg"])])
    with_ = query("F1", [row("r1", main=["egg", "x", "y"])], seasonings=["sugar"], paired_with="A2")
    m = xm.f_pair_metrics(with_, without)
    assert m["rubric_without"]["totals_uncapped"] == [ers.score_recipe(row("r1", main=["egg"]), with_)["total_uncapped"]]
    assert m["rubric_without"]["totals_uncapped"] == [5]
    assert m["rubric_with"]["totals_uncapped"] == [3]           # A=2, B=0 (2 of 3 mains missing), C=1
    assert m["mean_total_uncapped_delta"] == -2.0


def test_f_aggregate_counts_changed_pairs_and_states_the_selection_caveat():
    changed = {"top3_changed": True, "positions_changed": 2, "items_replaced": {"count": 1},
               "mean_overlap_without": 0.0, "mean_overlap_with": 0.5, "mean_overlap_delta": 0.5,
               "rubric_without": {"mean_total_uncapped": 4.0, "mean_total_capped": 4.0},
               "rubric_with": {"mean_total_uncapped": 5.0, "mean_total_capped": 5.0}}
    unchanged = {**changed, "top3_changed": False, "positions_changed": 0, "items_replaced": {"count": 0},
                 "mean_overlap_delta": 0.0, "mean_overlap_with": 0.0}
    agg = xm.f_aggregate([changed, unchanged])
    assert agg["n_pairs"] == 2 and agg["n_top3_changed"] == 1
    assert agg["mean_positions_changed"] == 1.0 and agg["mean_items_replaced"] == 0.5
    assert "selected so that every pair changes" in agg["caveat"]
    assert "not how often" in agg["caveat"]


# ---------------------------------------------------------------------------
# group G metrics
# ---------------------------------------------------------------------------

def test_leak_rate_is_the_share_of_top3_items_outside_the_requested_category():
    q = query("G1", [row("a", category="savory"), row("b", category="dessert"), row("c", category="savory")],
              category="savory", paired_with="A1")
    m = xm.g_query_metrics(q, available=48)
    assert m["leaked_ids"] == ["b"]
    assert m["category_leak_rate"] == round(1 / 3, 4)


def test_no_leak_when_every_item_has_the_requested_category():
    q = query("G2", [row("a", category="dessert"), row("b", category="dessert")], category="dessert")
    assert xm.g_query_metrics(q, available=23)["category_leak_rate"] == 0.0


def test_leak_rate_is_undefined_for_an_empty_result_or_the_all_category():
    assert xm.g_query_metrics(query("G3", [], category="savory"), available=0)["category_leak_rate"] is None
    assert xm.g_query_metrics(query("G4", [row("a")], category="all"), available=5)["category_leak_rate"] is None


def test_zero_results_flag_comes_from_the_available_count():
    q = query("G3", [], category="savory")
    assert xm.g_query_metrics(q, available=0)["zero_results"] is True
    assert xm.g_query_metrics(q, available=7)["zero_results"] is False
    assert xm.g_query_metrics(q, available=None)["zero_results"] is None


def test_dessert_mode_reports_only_the_uncapped_variant():
    q = query("G2", [row("a", category="dessert", main=["egg"])], category="dessert")
    m = xm.g_query_metrics(q, available=23)
    assert m["capped_reported"] is False
    assert "totals_capped" not in m and "mean_total_capped" not in m
    assert m["totals_uncapped"] == [4] and m["mean_total_uncapped"] == 4.0
    assert m["lenient_share_uncapped"] == 1.0 and m["strict_share_uncapped"] == 1.0
    assert "DESSERT_TOTAL_CAP" in m["capped_note"] and "can never pass a dessert" in m["capped_note"]


def test_the_cap_is_below_both_pass_lines_so_a_capped_dessert_cannot_pass():
    assert ers.DESSERT_TOTAL_CAP < ers.PASS_LENIENT < ers.PASS_STRICT


def test_savory_mode_reports_both_variants():
    q = query("G1", [row("a", category="savory", main=["egg"])], category="savory")
    m = xm.g_query_metrics(q, available=48)
    assert m["capped_reported"] is True
    assert m["totals_capped"] == [5] and m["totals_uncapped"] == [5]


def test_g_query_notes_when_the_top3_equals_the_paired_all_list():
    q = query("G5", [row("a"), row("b")], category="savory")
    assert xm.g_query_metrics(q, 3, ["a", "b"])["top3_same_as_paired_all"] is True
    assert xm.g_query_metrics(q, 3, ["a", "c"])["top3_same_as_paired_all"] is False


# ---------------------------------------------------------------------------
# whole report on tiny synthetic inputs
# ---------------------------------------------------------------------------

def _tiny_report():
    paired = {"queries": [query("A2", [row("r1", seasonings=["salt"])], ingredients=["chicken"]),
                          query("A1", [row("g1", category="savory"), row("g2", category="dessert")])]}
    extra = {"meta": {"catalog_size": 10}, "queries": [
        query("F1", [row("r2", seasonings=["sugar"])], ingredients=["chicken"], seasonings=["sugar"],
              category="all", paired_with="A2"),
        query("G1", [row("g1", category="savory")], category="savory", paired_with="A1", seasonings=[]),
    ]}
    notes = {"notes": {"zero_or_thin_category_results": "dessert yields 0 for chicken"}}
    prov = {"git_head": "abc1234", "recipes": 10, "categories": {"savory": 10}, "RUBRIC_VERSION": "v2",
            "inputs": ["extra.json"]}
    return xm.build_metrics(extra, paired, notes, {"G1": 6}, prov)


def test_build_metrics_collects_f_and_g_and_the_zero_result_note():
    m = _tiny_report()
    assert [r["id"] for r in m["F"]["queries"]] == ["F1"]
    assert [r["id"] for r in m["G"]["queries"]] == ["G1"]
    assert m["G"]["queries"][0]["results_available"] == 6
    assert m["zero_result_note"] == "dessert yields 0 for chicken"
    assert set(m["rule_rubric_groups"]) == {"F", "G"}


def test_markdown_header_carries_provenance_and_the_caveats():
    md = xm.to_markdown(_tiny_report())
    assert "git HEAD: `abc1234`" in md and "recipes: 10" in md and "RUBRIC_VERSION: v2" in md
    assert "`extra.json`" in md
    assert "## Group F" in md and "## Group G" in md
    assert "sensitive the ranking is to the seasoning weight" in md
    assert "can never pass a dessert" in md
    assert "dessert yields 0 for chicken" in md


def test_build_metrics_fails_loudly_when_a_paired_query_is_missing():
    extra = {"meta": {"catalog_size": 10}, "queries": [
        query("F1", [row("r2")], seasonings=["sugar"], category="all", paired_with="ZZ")]}
    with pytest.raises(KeyError):
        xm.build_metrics(extra, {"queries": []}, {}, {}, {})


# ---------------------------------------------------------------------------
# tools/eval_dump_top3.py: optional per-query seasonings / category
# ---------------------------------------------------------------------------

def test_a_flat_list_and_an_object_with_queries_load_the_same(tmp_path):
    flat = [{"id": "A1", "ingredients": ["egg"]}]
    p1, p2 = tmp_path / "flat.json", tmp_path / "obj.json"
    p1.write_text(json.dumps(flat), encoding="utf-8")
    p2.write_text(json.dumps({"_readme": "x", "queries": flat}), encoding="utf-8")
    assert dump._load_queries(p1) == dump._load_queries(p2) == flat


def test_a_query_without_the_new_fields_makes_the_old_call():
    q = {"id": "A1", "ingredients": ["egg"], "health_tags": [], "excluded": []}
    assert dump._call_args(q) == {"seasonings": [], "category": None}
    assert dump._has_call_fields(q) is False


def test_a_query_with_the_new_fields_passes_them_on():
    q = {"id": "F1", "seasonings": ["sugar"], "category": "dessert"}
    assert dump._call_args(q) == {"seasonings": ["sugar"], "category": "dessert"}
    assert dump._has_call_fields(q) is True
    assert dump._call_args({"id": "G1", "category": "savory"}) == {"seasonings": [], "category": "savory"}


def test_the_default_input_label_is_unchanged():
    assert dump._source_label(dump.TEST_SET_PATH) == "data/eval/test_set_draft_v1.json (preview_top3 ignored)"
    assert "test_set_extra_v1.json" in dump._source_label(dump.ROOT / "data" / "eval" / "test_set_extra_v1.json")
