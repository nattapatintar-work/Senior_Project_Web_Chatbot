"""
tools/judge_report.py
=====================
Turns the stored outputs of tools/judge_pairwise.py into metrics.json and report.md. Deterministic and offline:
it reads only plan.json and raw_calls.jsonl from the run directory and never calls anything.

    python tools/judge_report.py <run directory>        # e.g. data/eval/judge_f_v1

Metrics (all from the stored raw calls, so every number can be re-derived):
  * win rate of each candidate weight vs the reference 0.3, after un-swapping the A/B positions
    (win 1, tie 0.5, loss 0), over judged calls with a valid answer; identical pairs and parse/api errors are
    counted separately
  * position bias: the share of "A" answers (comparisons and controls separately)
  * order consistency: for the same (query, candidate, run), do the two presentation orders prefer the same list
  * self-consistency across runs: the share of (query, candidate, order) cells where every run agrees
  * negative-control accuracy: the real list wins against an unrelated query's list; below
    CONTROL_MIN_ACCURACY the judge is declared unreliable and the results must not be used

A report built from a MOCK run carries a MOCK banner on every section; mock output is never a real result.
"""

import json
import sys
from pathlib import Path

# A "definition we chose", not derived from data: the lowest negative-control accuracy at which the judge is
# trusted (14 of the 16 control calls).
CONTROL_MIN_ACCURACY = 0.875
SCORE = {"win": 1.0, "tie": 0.5, "loss": 0.0}

MOCK_BANNER = ("MOCK RUN: these numbers come from a mock client with pseudo-random answers. They are NOT real "
               "judge results and must never be quoted.")
LIMITATIONS = (
    "Only 8 queries (group F).",
    "The F pairs were chosen so that the ranking changes with the seasonings, so the share of changed rankings says "
    "nothing about real use.",
    "The judge measures agreement with the three stated criteria, not user satisfaction.",
    "There are no human labels to calibrate the judge against.",
    "The judge is a Claude model and the criteria were written by us.",
    "The judge model id is UNVERIFIED against the API (claude-sonnet-5 unless JUDGE_MODEL was set).",
    "Win rates are over a small number of calls and carry no confidence interval.",
)


def _f(value, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _mean(values: list) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def load_run(run_dir: Path) -> tuple[dict, list[dict]]:
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (run_dir / "raw_calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return plan, records


def outcome(record: dict) -> str | None:
    """Which list the judge preferred after un-swapping: the role name ('candidate', 'reference', 'real', 'foreign') or 'tie'."""
    if record.get("status") != "ok":
        return None
    winner = record["response"]["winner"]
    if winner == "tie":
        return "tie"
    return record["a_is"] if winner == "A" else record["b_is"]


def candidate_result(record: dict) -> str | None:
    """win / tie / loss for the candidate weight in a comparison record."""
    out = outcome(record)
    if out is None:
        return None
    return {"candidate": "win", "tie": "tie", "reference": "loss"}[out]


def win_rate(results: list[str]) -> float | None:
    return _mean([SCORE[r] for r in results])


def compute_metrics(plan: dict, records: list[dict]) -> dict:
    compare = [r for r in records if r["kind"] == "compare"]
    control = [r for r in records if r["kind"] == "control"]
    valid = [r for r in records if r["status"] == "ok"]
    runs = plan["settings"]["runs"]

    # --- win rate per candidate weight ---
    per_weight = {}
    for w in plan["settings"]["candidate_weights"]:
        calls = [r for r in compare if r["candidate_weight"] == w]
        results = [candidate_result(r) for r in calls if r["status"] == "ok"]
        per_weight[str(w)] = {
            "candidate_weight": w,
            "judged_pairs": sum(1 for c in plan["comparisons"] if c["candidate_weight"] == w and c["status"] != "identical"),
            "identical_pairs": sum(1 for c in plan["comparisons"] if c["candidate_weight"] == w and c["status"] == "identical"),
            "calls": len(calls), "valid_calls": len(results),
            "wins": results.count("win"), "ties": results.count("tie"), "losses": results.count("loss"),
            "win_rate_vs_reference": win_rate(results),
        }
    all_results = [candidate_result(r) for r in compare if r["status"] == "ok"]
    overall = {"valid_calls": len(all_results), "wins": all_results.count("win"), "ties": all_results.count("tie"),
               "losses": all_results.count("loss"), "win_rate_vs_reference": win_rate(all_results)}

    # --- position bias ---
    def share_a(rs):
        ok = [r for r in rs if r["status"] == "ok"]
        return {"valid_calls": len(ok), "share_A": _mean([1.0 if r["response"]["winner"] == "A" else 0.0 for r in ok])}
    position_bias = {"comparisons": share_a(compare), "controls": share_a(control), "all": share_a(records)}

    # --- order consistency: same (query, candidate weight, run), both orders valid ---
    cells = {}
    for r in compare:
        if r["status"] == "ok":
            cells.setdefault((r["query"], r["candidate_weight"], r["run"]), {})[r["order"]] = outcome(r)
    both = [v for v in cells.values() if len(v) == 2]
    order_consistency = {"pairs_with_both_orders": len(both),
                         "consistent_share": _mean([1.0 if v["cand_first"] == v["ref_first"] else 0.0 for v in both])}

    # --- self-consistency across runs: cells (query, candidate weight, order) with every run valid ---
    runs_by_cell = {}
    for r in compare:
        runs_by_cell.setdefault((r["query"], r["candidate_weight"], r["order"]), []).append(r)
    complete = [rs for rs in runs_by_cell.values() if len(rs) == runs and all(x["status"] == "ok" for x in rs)]
    self_consistency = {"runs_per_cell": runs, "cells_total": len(runs_by_cell), "cells_with_all_runs_valid": len(complete),
                        "all_runs_agree_share": _mean([1.0 if len({outcome(x) for x in rs}) == 1 else 0.0 for rs in complete])}

    # --- negative controls ---
    control_results = [outcome(r) for r in control if r["status"] == "ok"]
    n_ctl = len(control_results)
    accuracy = round(control_results.count("real") / n_ctl, 4) if n_ctl else None
    reliable = None if accuracy is None else accuracy >= CONTROL_MIN_ACCURACY
    negative_controls = {"valid_calls": n_ctl, "calls": len(control), "real_wins": control_results.count("real"),
                         "ties": control_results.count("tie"), "foreign_wins": control_results.count("foreign"),
                         "accuracy": accuracy, "min_accuracy_to_trust": CONTROL_MIN_ACCURACY, "judge_reliable": reliable}

    # --- per query ---
    per_query = []
    for q in sorted({c["query"] for c in plan["comparisons"]}):
        row = {"query": q, "weights": {}}
        for c in [c for c in plan["comparisons"] if c["query"] == q]:
            results = [candidate_result(r) for r in compare
                       if r["query"] == q and r["candidate_weight"] == c["candidate_weight"] and r["status"] == "ok"]
            row["weights"][str(c["candidate_weight"])] = {
                "top3_change_vs_reference": c["status"],
                "judge": ("not judged (identical)" if c["status"] == "identical" else
                          f"{results.count('win')}W/{results.count('tie')}T/{results.count('loss')}L of {len(results)} valid calls"),
                "win_rate_vs_reference": win_rate(results) if results else None}
        per_query.append(row)

    tokens = {"input": sum((r.get("usage") or {}).get("input_tokens") or 0 for r in records),
              "output": sum((r.get("usage") or {}).get("output_tokens") or 0 for r in records)}
    return {
        "mode": plan.get("mode", "UNKNOWN"), "model": plan.get("model"),
        "settings": plan["settings"], "calls_recorded": len(records),
        "status_counts": {s: sum(1 for r in records if r["status"] == s) for s in sorted({r["status"] for r in records})},
        "identical_pairs_skipped": plan["n_identical"],
        "win_rate_per_weight": per_weight, "win_rate_overall": overall,
        "position_bias": position_bias, "order_consistency": order_consistency, "self_consistency": self_consistency,
        "negative_controls": negative_controls, "per_query": per_query, "token_totals": tokens,
        "adaptations": sorted({a for r in records for a in r.get("adaptations", [])}),
        "limitations": list(LIMITATIONS),
    }


def to_markdown(m: dict) -> str:
    mock = m["mode"] == "MOCK"
    L = []
    w = L.append
    if mock:
        w(f"> **{MOCK_BANNER}**\n")
    w("# SEASONING_WEIGHT pairwise judge: report" + (" (MOCK)" if mock else ""))
    w("")
    w(f"- mode: **{m['mode']}**; judge model: `{m['model']}` (UNVERIFIED id)")
    w(f"- runs per pair: {m['settings']['runs']}; candidate weights {m['settings']['candidate_weights']} vs reference "
      f"{m['settings']['reference_weight']}")
    w(f"- calls recorded: {m['calls_recorded']}; status counts: {m['status_counts']}; identical pairs skipped (never judged): "
      f"{m['identical_pairs_skipped']}")
    w(f"- tokens used (from the stored usage fields): input {m['token_totals']['input']}, output {m['token_totals']['output']}")
    if m["adaptations"]:
        w(f"- parameter adaptations during the run: {m['adaptations']}")
    w("")
    nc = m["negative_controls"]
    w("## Judge reliability (negative controls)")
    w("")
    if mock:
        w(f"> {MOCK_BANNER}\n")
    w(f"The real top-3 beat an unrelated query's top-3 in {nc['real_wins']} of {nc['valid_calls']} valid control calls "
      f"(accuracy {_f(nc['accuracy'])}; ties {nc['ties']}, foreign list won {nc['foreign_wins']}). "
      f"Trust threshold: {nc['min_accuracy_to_trust']} (a definition we chose).")
    w("")
    if nc["judge_reliable"] is None:
        w("**No valid control calls: reliability cannot be assessed, so the results below must not be used.**")
    elif not nc["judge_reliable"]:
        w("**The judge is UNRELIABLE (control accuracy below the threshold). The results below must NOT be used.**")
    else:
        w("The judge passes the control check (this does not make it a measure of user satisfaction).")
    w("")
    w("## Win rate of each candidate weight versus 0.3")
    w("")
    if mock:
        w(f"> {MOCK_BANNER}\n")
    w("Positions are un-swapped before counting. Win = 1, tie = 0.5, loss = 0, over judged calls with a valid answer. "
      "Identical top-3 pairs are not judged and are not in the win rate.")
    w("")
    w("| candidate weight | judged pairs | identical pairs | valid calls | wins | ties | losses | win rate vs 0.3 |")
    w("|---|---|---|---|---|---|---|---|")
    for row in m["win_rate_per_weight"].values():
        w(f"| {row['candidate_weight']} | {row['judged_pairs']} | {row['identical_pairs']} | {row['valid_calls']} | {row['wins']} "
          f"| {row['ties']} | {row['losses']} | {_f(row['win_rate_vs_reference'])} |")
    o = m["win_rate_overall"]
    w(f"| all candidates | | | {o['valid_calls']} | {o['wins']} | {o['ties']} | {o['losses']} | {_f(o['win_rate_vs_reference'])} |")
    w("")
    w("## Bias and consistency")
    w("")
    pb, oc, sc = m["position_bias"], m["order_consistency"], m["self_consistency"]
    w(f"- position bias, share of answers \"A\": comparisons {_f(pb['comparisons']['share_A'])} ({pb['comparisons']['valid_calls']} calls), "
      f"controls {_f(pb['controls']['share_A'])} ({pb['controls']['valid_calls']} calls), all {_f(pb['all']['share_A'])}. "
      "Values far from 0.5 suggest the judge favors a position.")
    w(f"- order consistency (same pair and run, A/B swapped, same list preferred): {_f(oc['consistent_share'])} "
      f"over {oc['pairs_with_both_orders']} pairs")
    w(f"- self-consistency across runs (all {sc['runs_per_cell']} runs agree in a (pair, order) cell): {_f(sc['all_runs_agree_share'])} "
      f"over {sc['cells_with_all_runs_valid']} complete cells (of {sc['cells_total']} cells)")
    w("")
    w("## Per query")
    w("")
    if mock:
        w(f"> {MOCK_BANNER}\n")
    weights = list(m["win_rate_per_weight"])
    w("| query | " + " | ".join(f"{x}: top-3 vs 0.3 / judge" for x in weights) + " |")
    w("|---|" + "---|" * len(weights))
    for row in m["per_query"]:
        cells = [f"{row['weights'][x]['top3_change_vs_reference']} / {row['weights'][x]['judge']}" for x in weights]
        w(f"| {row['query']} | " + " | ".join(cells) + " |")
    w("")
    w("## Limitations")
    w("")
    for item in m["limitations"]:
        w(f"- {item}")
    w("")
    if mock:
        w(f"> **{MOCK_BANNER}**")
        w("")
    return "\n".join(L)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python tools/judge_report.py <run directory>")
        return 2
    run_dir = Path(args[0])
    for name in ("plan.json", "raw_calls.jsonl"):
        if not (run_dir / name).exists():
            print(f"missing {run_dir / name}")
            return 2
    plan, records = load_run(run_dir)
    metrics = compute_metrics(plan, records)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run_dir / "report.md").write_text(to_markdown(metrics), encoding="utf-8")
    print(f"wrote {run_dir / 'metrics.json'} and {run_dir / 'report.md'} (mode {metrics['mode']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
