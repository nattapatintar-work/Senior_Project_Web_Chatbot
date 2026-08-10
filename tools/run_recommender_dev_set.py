"""
tools/run_recommender_dev_set.py
=================================
Runs recommender/recommend() against data/recommender_dev_set.json and
reports pass/fail per case.

WHY THIS ISN'T "Precision@3" YET
---------------------------------
Claude.md:472 calls for Precision@3 / Recall@5 on 30-40 cases with ground
truth from outsiders -- that is Week 10's job, against a labelled set Person 2
does not write alone (the whole point of outside labels is that they aren't
self-graded). This dev set has no ranked ground truth, only two cheap,
self-verifiable assertions per case:

    expect_top3_contains -- these recipe ids MUST appear somewhere in the
                             top-3 returned
    expect_absent        -- these recipe ids MUST NOT appear anywhere in the
                             top-3 returned (usually a health/excluded-filter
                             check, not a ranking check)

That is enough to catch a broken filter or a scoring regression -- which is
what this file is for -- without pretending to measure ranking quality against
data that doesn't exist yet.

Run with:
    python tools/run_recommender_dev_set.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from recommender.recommend import recommend

DEV_SET_PATH = Path(__file__).parent.parent / "data" / "recommender_dev_set.json"


def load_dev_set() -> list[dict]:
    with open(DEV_SET_PATH, encoding="utf-8") as f:
        return json.load(f)["cases"]


def run_case(case: dict) -> tuple[bool, str]:
    results = recommend(
        ingredients=case["ingredients"],
        health_tags=case.get("health_tags") or None,
        excluded=case.get("excluded") or None,
    )
    got_ids = {dish["id"] for dish in results}

    missing = [rid for rid in case["expect_top3_contains"] if rid not in got_ids]
    unwanted = [rid for rid in case["expect_absent"] if rid in got_ids]

    if not missing and not unwanted:
        return True, f"got {sorted(got_ids)}"

    problems = []
    if missing:
        problems.append(f"expected but absent: {missing}")
    if unwanted:
        problems.append(f"forbidden but present: {unwanted}")
    return False, "; ".join(problems) + f" (got {sorted(got_ids)})"


def main() -> None:
    cases = load_dev_set()
    passed = 0
    for case in cases:
        ok, detail = run_case(case)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['id']}: {detail}")
        if ok:
            passed += 1

    print(f"\n{passed}/{len(cases)} dev cases passed")
    if passed != len(cases):
        sys.exit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
