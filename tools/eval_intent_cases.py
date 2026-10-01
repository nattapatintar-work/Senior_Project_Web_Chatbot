"""
tools/eval_intent_cases.py
==========================
Behaviour check for the /confirm step on correction sentences. Nothing here calls the
network: the keyword fallback runs for real, and the Haiku client is replaced by a
stub, so the outputs are what the code does for a GIVEN model label, not what Haiku
would actually say.

    python tools/eval_intent_cases.py

For every sentence in CASES it reports, starting from ingredients=[chicken, egg] and
stage=awaiting_confirm:

  fallback   the keyword classifier (no key) through the real POST /confirm handler
  (a)        stub Haiku answers label=confirm+correction with the obvious phrases
  (b)        stub Haiku answers label=reject WITH the same phrases
  (c)        stub Haiku answers label=reject with NO phrases (what a plain reject does)

Each cell shows the intent the API returned, the final ingredient list, the `exclude`
list, the stage and reject_count. The real handler (api/app.py), SessionState and
extract() are used unchanged; only the LLM client and the YOLO loader are stubbed.

NOTE ON WHAT CHANGED SINCE THIS WAS FIRST WRITTEN
  - a removal at /confirm no longer goes into `exclude` (api/app.py passes
    ban_excluded=False), so `exclude` is empty in every column except where a
    first-message "no X" put something there;
  - column (b), an LLM `reject` WITH phrases, used to be reported as `unclear`; it is now
    treated as confirm+correction when at least one phrase resolves (api/intent.py), so
    (b) matches (a). Column (c), a reject with no phrases, is unchanged.
The keyword fallback (column "fallback") was NOT changed.
"""

import contextlib
import io
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api import app as app_module
from api import intent, state, web_config

FAKE_KEY = "sk-ant-api03-FAKEKEYFORTESTS-do-not-leak"   # placeholder; never a real credential
START_INGREDIENTS = ["chicken", "egg"]

# (number, sentence, obvious add phrases, obvious remove phrases) -- Thai test data
CASES = [
    (1, "ไม่ใช่ไก่ แต่เป็นหมู", ["หมู"], ["ไก่"]),
    (2, "ไม่เอาไก่ ใส่หมูแทน", ["หมู"], ["ไก่"]),
    (3, "ใช่ แต่เพิ่มหมูด้วย", ["หมู"], []),
    (4, "ไม่ใช่", [], []),
    (5, "ไม่ต้องมีไข่", [], ["ไข่"]),
    (6, "เปลี่ยนไก่เป็นหมู", ["หมู"], ["ไก่"]),
    (7, "ใช่ครับ", [], []),
    (8, "อืม", [], []),
    (9, "ไม่ใช่ไก่ แต่เป็นมังคุด", ["มังคุด"], ["ไก่"]),   # มังคุด is not in the dictionary
]


class StubClient:
    """Stands in for anthropic.Anthropic: always answers with one fixed report_intent call."""

    def __init__(self, label: str, add: list[str], remove: list[str]):
        block = SimpleNamespace(
            type="tool_use",
            name="report_intent",
            input={"intent": label, "add_phrases": list(add), "remove_phrases": list(remove)},
        )
        self._response = SimpleNamespace(stop_reason="tool_use", content=[block])
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        return self._response


def _forbidden_client():
    raise AssertionError("fallback run must not build an Anthropic client")


def confirm_once(http: TestClient, reply: str) -> dict:
    """POST /confirm from a fresh session holding START_INGREDIENTS; return a snapshot of what happened."""
    state.store.clear()
    app_module.limiter.reset()
    sess = state.store.create()
    sess.include = list(START_INGREDIENTS)
    sess.stage = state.STAGE_AWAITING_CONFIRM

    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        response = http.post("/confirm", json={"session_id": sess.session_id, "reply": reply})
    body = response.json()
    after = state.store.get(sess.session_id)
    return {
        "status": response.status_code,
        "intent": body["intent"],
        "corrections": body["corrections"],
        "ingredients": body["ingredients"],
        "stage": body["stage"],
        "exclude": list(after.exclude),
        "reject_count": after.reject_count,
        "log": [line for line in log.getvalue().splitlines() if line.startswith("[intent]")],
    }


def run_fallback(http: TestClient, sentence: str) -> dict:
    """Keyword classifier, no network: blank key, and any attempt to build a client blows up."""
    with mock.patch.object(web_config, "ANTHROPIC_API_KEY", ""), \
            mock.patch.object(intent, "_get_client", _forbidden_client):
        raw = intent.classify_intent(sentence, list(START_INGREDIENTS))
        snap = confirm_once(http, sentence)
    snap["classifier"] = {"label": raw.intent, "add": raw.add, "remove": raw.remove}
    return snap


def run_mocked(http: TestClient, sentence: str, label: str, add: list[str], remove: list[str]) -> dict:
    stub = StubClient(label, add, remove)
    with mock.patch.object(web_config, "ANTHROPIC_API_KEY", FAKE_KEY), \
            mock.patch.object(intent, "_get_client", lambda: stub):
        snap = confirm_once(http, sentence)
    snap["llm_calls"] = stub.calls
    return snap


def run_case(http: TestClient, sentence: str, add: list[str], remove: list[str]) -> dict:
    return {
        "fallback": run_fallback(http, sentence),
        "a_confirm_correction": run_mocked(http, sentence, intent.CONFIRM_AND_CORRECT, add, remove),
        "b_reject_with_phrases": run_mocked(http, sentence, intent.REJECT, add, remove),
        "c_reject_no_phrases": run_mocked(http, sentence, intent.REJECT, [], []),
    }


def cell(snap: dict) -> str:
    text = f"{snap['intent']}: {snap['ingredients']}"
    if snap["exclude"]:
        text += f" exclude={snap['exclude']}"
    text += f" [{snap['stage']}, rejects={snap['reject_count']}]"
    if snap["log"]:
        text += " (" + "; ".join(line.removeprefix("[intent] ") for line in snap["log"]) + ")"
    return text


def run_all() -> list[dict]:
    with mock.patch.object(app_module, "_load_detector", lambda: None):    # skip loading the YOLO model
        with TestClient(app_module.app) as http:
            rows = []
            for number, sentence, add, remove in CASES:
                rows.append({"n": number, "sentence": sentence, "add": add, "remove": remove,
                             **run_case(http, sentence, add, remove)})
    state.store.clear()
    app_module.limiter.reset()
    return rows


def to_markdown(rows: list[dict]) -> str:
    lines = [
        f"Start: ingredients={START_INGREDIENTS}, stage=awaiting_confirm. Cells: intent: final ingredients "
        "[exclude] [stage, reject_count].",
        "",
        "| # | sentence | fallback label (add / remove keys) | fallback result | mocked confirm+correction (a) "
        "| mocked reject + phrases (b) | mocked reject, no phrases (c) |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        clf = row["fallback"]["classifier"]
        lines.append(
            f"| {row['n']} | {row['sentence']} | {clf['label']} ({clf['add']} / {clf['remove']}) "
            f"| {cell(row['fallback'])} | {cell(row['a_confirm_correction'])} "
            f"| {cell(row['b_reject_with_phrases'])} | {cell(row['c_reject_no_phrases'])} |"
        )
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(to_markdown(run_all()))


if __name__ == "__main__":
    main()
