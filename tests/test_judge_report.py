"""
tests/test_judge_report.py
==========================
Offline tests for tools/judge_report.py on synthetic raw calls (and one mock run through tools/judge_pairwise.py).

Run with:
    pytest tests/test_judge_report.py -v
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import judge_pairwise as jp
import judge_report as jr


# ---------------------------------------------------------------------------
# synthetic raw calls
# ---------------------------------------------------------------------------

def cmp_rec(query, weight, order, run, winner, status="ok"):
    a_is, b_is = ("candidate", "reference") if order == "cand_first" else ("reference", "candidate")
    return {"kind": "compare", "query": query, "candidate_weight": weight, "order": order, "run": run,
            "a_is": a_is, "b_is": b_is, "status": status,
            "response": None if status != "ok" else {"reasoning": "r", "winner": winner, "confidence": 2},
            "usage": {"input_tokens": 100, "output_tokens": 10}, "adaptations": []}


def ctl_rec(query, order, winner, status="ok"):
    a_is, b_is = ("real", "foreign") if order == "real_first" else ("foreign", "real")
    return {"kind": "control", "query": query, "order": order, "run": 1, "a_is": a_is, "b_is": b_is, "status": status,
            "response": None if status != "ok" else {"reasoning": "r", "winner": winner, "confidence": 3},
            "usage": {"input_tokens": 100, "output_tokens": 10}, "adaptations": []}


def make_plan(mode="REAL", runs=2, weights=(0.0, 0.5), comparisons=None):
    comparisons = comparisons or [
        {"query": "F1", "candidate_weight": 0.0, "status": "different"},
        {"query": "F1", "candidate_weight": 0.5, "status": "identical"},
        {"query": "F2", "candidate_weight": 0.0, "status": "reordered"},
        {"query": "F2", "candidate_weight": 0.5, "status": "different"},
    ]
    return {"mode": mode, "model": "m", "settings": {"runs": runs, "candidate_weights": list(weights), "reference_weight": 0.3},
            "comparisons": comparisons, "n_identical": sum(1 for c in comparisons if c["status"] == "identical")}


# ---------------------------------------------------------------------------
# un-swapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("order, winner, expected", [
    ("cand_first", "A", "win"),     # A is the candidate
    ("cand_first", "B", "loss"),    # B is the reference
    ("ref_first", "A", "loss"),     # A is the reference
    ("ref_first", "B", "win"),      # B is the candidate
    ("cand_first", "tie", "tie"),
    ("ref_first", "tie", "tie"),
])
def test_unswapping_maps_the_position_answer_back_to_the_candidate(order, winner, expected):
    assert jr.candidate_result(cmp_rec("F1", 0.0, order, 1, winner)) == expected


def test_a_failed_call_has_no_outcome():
    assert jr.outcome(cmp_rec("F1", 0.0, "cand_first", 1, "A", status="parse_error")) is None
    assert jr.candidate_result(cmp_rec("F1", 0.0, "cand_first", 1, "A", status="api_error")) is None


def test_control_outcomes_are_un_swapped_to_real_or_foreign():
    assert jr.outcome(ctl_rec("F1", "real_first", "A")) == "real"
    assert jr.outcome(ctl_rec("F1", "foreign_first", "A")) == "foreign"
    assert jr.outcome(ctl_rec("F1", "foreign_first", "B")) == "real"


# ---------------------------------------------------------------------------
# win rate
# ---------------------------------------------------------------------------

def test_win_rate_counts_win_1_tie_half_loss_0():
    assert jr.win_rate(["win", "tie", "loss"]) == 0.5
    assert jr.win_rate(["win", "win"]) == 1.0
    assert jr.win_rate([]) is None


def test_win_rate_per_weight_uses_only_valid_judged_calls_and_reports_identical_pairs_separately():
    plan = make_plan()
    records = [
        cmp_rec("F1", 0.0, "cand_first", 1, "A"),          # candidate wins
        cmp_rec("F1", 0.0, "ref_first", 1, "B"),           # candidate wins (swapped)
        cmp_rec("F2", 0.0, "cand_first", 1, "B"),          # candidate loses
        cmp_rec("F2", 0.0, "ref_first", 1, "tie"),         # tie
        cmp_rec("F2", 0.0, "ref_first", 2, "A", status="parse_error"),   # excluded
        cmp_rec("F2", 0.5, "cand_first", 1, "A"),          # candidate wins
        cmp_rec("F2", 0.5, "ref_first", 1, "A"),           # candidate loses
    ]
    m = jr.compute_metrics(plan, records)
    w0 = m["win_rate_per_weight"]["0.0"]
    assert (w0["wins"], w0["ties"], w0["losses"], w0["valid_calls"], w0["calls"]) == (2, 1, 1, 4, 5)
    assert w0["win_rate_vs_reference"] == 0.625
    assert w0["judged_pairs"] == 2 and w0["identical_pairs"] == 0
    w5 = m["win_rate_per_weight"]["0.5"]
    assert w5["win_rate_vs_reference"] == 0.5 and w5["identical_pairs"] == 1 and w5["judged_pairs"] == 1
    assert m["win_rate_overall"]["valid_calls"] == 6 and m["win_rate_overall"]["wins"] == 3
    assert m["identical_pairs_skipped"] == 1
    assert m["status_counts"] == {"ok": 6, "parse_error": 1}


# ---------------------------------------------------------------------------
# bias and consistency
# ---------------------------------------------------------------------------

def test_position_bias_is_the_share_of_A_answers():
    records = [cmp_rec("F1", 0.0, "cand_first", 1, "A"), cmp_rec("F1", 0.0, "ref_first", 1, "A"),
               cmp_rec("F1", 0.0, "cand_first", 2, "B"), cmp_rec("F1", 0.0, "ref_first", 2, "tie"),
               ctl_rec("F1", "real_first", "A"), ctl_rec("F1", "foreign_first", "B")]
    pb = jr.compute_metrics(make_plan(), records)["position_bias"]
    assert pb["comparisons"] == {"valid_calls": 4, "share_A": 0.5}
    assert pb["controls"] == {"valid_calls": 2, "share_A": 0.5}
    assert pb["all"]["share_A"] == round(3 / 6, 4)


def test_a_judge_that_always_answers_A_is_order_inconsistent():
    records = [cmp_rec("F1", 0.0, "cand_first", 1, "A"), cmp_rec("F1", 0.0, "ref_first", 1, "A")]
    oc = jr.compute_metrics(make_plan(), records)["order_consistency"]
    assert oc == {"pairs_with_both_orders": 1, "consistent_share": 0.0}


def test_a_judge_that_prefers_the_same_list_in_both_orders_is_order_consistent():
    records = [cmp_rec("F1", 0.0, "cand_first", 1, "A"), cmp_rec("F1", 0.0, "ref_first", 1, "B"),    # candidate both times
               cmp_rec("F2", 0.0, "cand_first", 1, "B"), cmp_rec("F2", 0.0, "ref_first", 1, "A")]    # reference both times
    oc = jr.compute_metrics(make_plan(), records)["order_consistency"]
    assert oc == {"pairs_with_both_orders": 2, "consistent_share": 1.0}


def test_order_consistency_ignores_pairs_missing_one_valid_order():
    records = [cmp_rec("F1", 0.0, "cand_first", 1, "A"), cmp_rec("F1", 0.0, "ref_first", 1, "A", status="api_error")]
    oc = jr.compute_metrics(make_plan(), records)["order_consistency"]
    assert oc == {"pairs_with_both_orders": 0, "consistent_share": None}


def test_self_consistency_is_the_share_of_complete_cells_where_all_runs_agree():
    records = [
        cmp_rec("F1", 0.0, "cand_first", 1, "A"), cmp_rec("F1", 0.0, "cand_first", 2, "A"),          # agree
        cmp_rec("F1", 0.0, "ref_first", 1, "A"), cmp_rec("F1", 0.0, "ref_first", 2, "B"),            # disagree
        cmp_rec("F2", 0.0, "cand_first", 1, "A"), cmp_rec("F2", 0.0, "cand_first", 2, "A", status="api_error"),  # incomplete
    ]
    sc = jr.compute_metrics(make_plan(runs=2), records)["self_consistency"]
    assert sc["cells_total"] == 3 and sc["cells_with_all_runs_valid"] == 2 and sc["all_runs_agree_share"] == 0.5


# ---------------------------------------------------------------------------
# negative controls
# ---------------------------------------------------------------------------

def _controls(real_wins, foreign_wins, ties):
    recs = []
    for i in range(real_wins):
        recs.append(ctl_rec(f"F{i}", "real_first", "A"))
    for i in range(foreign_wins):
        recs.append(ctl_rec(f"F{i}", "real_first", "B"))
    for i in range(ties):
        recs.append(ctl_rec(f"F{i}", "real_first", "tie"))
    return recs


def test_negative_control_accuracy_is_the_share_where_the_real_list_wins():
    nc = jr.compute_metrics(make_plan(), _controls(7, 1, 0))["negative_controls"]
    assert (nc["real_wins"], nc["foreign_wins"], nc["ties"], nc["valid_calls"]) == (7, 1, 0, 8)
    assert nc["accuracy"] == 0.875 and nc["judge_reliable"] is True


def test_a_tie_counts_as_not_winning_a_control():
    nc = jr.compute_metrics(make_plan(), _controls(6, 0, 2))["negative_controls"]
    assert nc["accuracy"] == 0.75 and nc["judge_reliable"] is False


def test_the_report_declares_an_unreliable_judge_and_says_not_to_use_the_results():
    m = jr.compute_metrics(make_plan(), _controls(4, 4, 0) + [cmp_rec("F1", 0.0, "cand_first", 1, "A")])
    md = jr.to_markdown(m)
    assert m["negative_controls"]["judge_reliable"] is False
    assert "UNRELIABLE" in md and "must NOT be used" in md


def test_without_valid_controls_reliability_cannot_be_assessed():
    m = jr.compute_metrics(make_plan(), [cmp_rec("F1", 0.0, "cand_first", 1, "A"), ctl_rec("F1", "real_first", "A", status="api_error")])
    assert m["negative_controls"]["accuracy"] is None and m["negative_controls"]["judge_reliable"] is None
    assert "reliability cannot be assessed" in jr.to_markdown(m)


# ---------------------------------------------------------------------------
# per query table, banner, limitations
# ---------------------------------------------------------------------------

def test_the_per_query_table_shows_how_the_top3_changed_and_what_the_judge_said():
    records = [cmp_rec("F1", 0.0, "cand_first", 1, "A"), cmp_rec("F1", 0.0, "ref_first", 1, "A")]
    per_query = {r["query"]: r["weights"] for r in jr.compute_metrics(make_plan(), records)["per_query"]}
    assert per_query["F1"]["0.0"]["top3_change_vs_reference"] == "different"
    assert per_query["F1"]["0.0"]["judge"] == "1W/0T/1L of 2 valid calls"
    assert per_query["F1"]["0.5"] == {"top3_change_vs_reference": "identical", "judge": "not judged (identical)",
                                      "win_rate_vs_reference": None}
    assert per_query["F2"]["0.0"]["top3_change_vs_reference"] == "reordered"


def test_a_mock_report_carries_the_mock_banner_on_every_section():
    md = jr.to_markdown(jr.compute_metrics(make_plan(mode="MOCK"), _controls(8, 0, 0) + [cmp_rec("F1", 0.0, "cand_first", 1, "A")]))
    assert md.startswith("> **MOCK RUN")
    assert md.count(jr.MOCK_BANNER) >= 5
    assert "(MOCK)" in md


def test_a_real_report_has_no_mock_banner():
    md = jr.to_markdown(jr.compute_metrics(make_plan(mode="REAL"), _controls(8, 0, 0)))
    assert "MOCK" not in md


def test_the_report_states_the_limitations():
    md = jr.to_markdown(jr.compute_metrics(make_plan(), _controls(8, 0, 0)))
    for text in ("Only 8 queries", "chosen so that the ranking changes", "not user satisfaction", "no human labels",
                 "Claude model and the criteria were written by us", "UNVERIFIED"):
        assert text in md


def test_adaptations_and_token_totals_are_reported():
    rec = cmp_rec("F1", 0.0, "cand_first", 1, "A")
    rec["adaptations"] = ["temperature switched off after an HTTP 400"]
    m = jr.compute_metrics(make_plan(), [rec, cmp_rec("F1", 0.0, "ref_first", 1, "B")])
    assert m["adaptations"] == ["temperature switched off after an HTTP 400"]
    assert m["token_totals"] == {"input": 200, "output": 20}


# ---------------------------------------------------------------------------
# end to end on a mock run
# ---------------------------------------------------------------------------

def _mock_run(tmp_path):
    ids = sorted(jp.load_data()["recipes"])
    shift = {0.0: 3, 0.15: 0, 0.3: 0, 0.5: 1}

    def top3_fn(query, weight):
        i = int(query["id"][1:]) * 3
        return ids[i + shift[weight]: i + shift[weight] + 3]
    assert jp.main(["--mock", "--runs", "2", "--out-dir", str(tmp_path)], top3_fn=top3_fn) == 0


def test_a_mock_run_produces_a_deterministic_mock_labelled_report(tmp_path, capsys):
    _mock_run(tmp_path)
    assert jr.main([str(tmp_path)]) == 0
    first = (tmp_path / "report.md").read_text(encoding="utf-8"), (tmp_path / "metrics.json").read_text(encoding="utf-8")
    assert jr.main([str(tmp_path)]) == 0
    second = (tmp_path / "report.md").read_text(encoding="utf-8"), (tmp_path / "metrics.json").read_text(encoding="utf-8")
    assert first == second
    metrics = json.loads(first[1])
    assert metrics["mode"] == "MOCK" and first[0].startswith("> **MOCK RUN")
    assert metrics["calls_recorded"] == metrics["status_counts"]["ok"]


def test_the_report_cli_complains_about_a_missing_run_directory(tmp_path, capsys):
    assert jr.main([str(tmp_path / "nothing")]) == 2
    assert "missing" in capsys.readouterr().out
    assert jr.main([]) == 2
