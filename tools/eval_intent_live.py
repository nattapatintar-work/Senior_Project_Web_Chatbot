"""
tools/eval_intent_live.py
=========================
LIVE check of the /confirm intent classifier against the REAL Anthropic API.

    python tools/eval_intent_live.py

*** THIS SCRIPT SPENDS MONEY. It makes at most 27 API calls: the 9 sentences in
tools/eval_intent_cases.py, 3 runs each, one Claude Haiku 4.5 call per run. At the
roughly $0.0016 per call measured for this classifier (Claude.md, Open Item 5) that is
about $0.04. It is never run by pytest or by any other script. ***

What it does
  Calls api.intent.classify_intent() -- the same function /confirm uses -- on each
  sentence, from the same starting list as eval_intent_cases.py ([chicken, egg]), and
  prints: sentence | label per run | add | remove | whether the label changed.
  `add` / `remove` are the resolved dictionary KEYS (what the handler would apply), not
  the raw phrases the model returned. classify_intent() never raises: on any API failure
  it falls back to the keyword classifier and prints a "[intent] ..." line. Such runs are
  marked "(fallback)" here so a keyword answer is never mistaken for the model's.

The API key
  Read from the ANTHROPIC_API_KEY environment variable (or .env, through api.web_config,
  exactly as the app does). It is never printed, logged or echoed. If it is missing or
  still the .env.example placeholder, the script exits with a message and makes no call.
"""

import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from api import intent, web_config
from eval_intent_cases import CASES, START_INGREDIENTS

RUNS_PER_SENTENCE = 3
MAX_CALLS = len(CASES) * RUNS_PER_SENTENCE      # 27


def classify_once(sentence: str) -> dict:
    """One real classify_intent() call. Reports whether the keyword fallback answered instead."""
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        result = intent.classify_intent(sentence, list(START_INGREDIENTS))
    failures = [line for line in log.getvalue().splitlines() if "LLM classifier failed" in line]
    return {
        "label": result.intent,
        "add": result.add,
        "remove": result.remove,
        "fallback": bool(failures),
    }


def label_text(run: dict) -> str:
    return run["label"] + (" (fallback)" if run["fallback"] else "")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not web_config.anthropic_key_configured():
        sys.exit("ANTHROPIC_API_KEY is not set (or is still the .env.example placeholder): "
                 "no API calls were made.")
    print(f"Live run: up to {MAX_CALLS} real API calls ({len(CASES)} sentences x {RUNS_PER_SENTENCE} runs).\n")

    rows = []
    for number, sentence, _add, _remove in CASES:
        runs = [classify_once(sentence) for _ in range(RUNS_PER_SENTENCE)]
        labels = [r["label"] for r in runs]
        rows.append({"n": number, "sentence": sentence, "runs": runs, "changed": len(set(labels)) > 1})

    print("| # | sentence | label per run | add (keys) per run | remove (keys) per run | label changed? |")
    print("|---|---|---|---|---|---|")
    for row in rows:
        labels = " / ".join(label_text(r) for r in row["runs"])
        adds = " / ".join(str(r["add"]) for r in row["runs"])
        removes = " / ".join(str(r["remove"]) for r in row["runs"])
        print(f"| {row['n']} | {row['sentence']} | {labels} | {adds} | {removes} | "
              f"{'YES' if row['changed'] else 'no'} |")

    changed = sum(1 for r in rows if r["changed"])
    fallbacks = sum(1 for row in rows for r in row["runs"] if r["fallback"])
    print(f"\nLabel changed between runs for {changed} of {len(rows)} sentences.")
    print(f"Runs answered by the keyword fallback instead of the model: {fallbacks} of {MAX_CALLS}.")


if __name__ == "__main__":
    main()
