"""
tools/eval_exclude_check.py
===========================
Shows, with real recommendations, whether removing an ingredient at the confirm step
also BANS dishes that contain it (i.e. adds it to the session's `exclude` list).

    python tools/eval_exclude_check.py

Uses the real /confirm and /recommend handlers, the real recommend() and recipes.json.
Only two things are stubbed, as in tools/eval_intent_cases.py: the Haiku client (a
fixed report_intent answer per call; no network, a placeholder key) and the YOLO loader.

Scenarios
  A  detected [chicken, egg]; "ไม่ใช่ไก่ แต่เป็นหมู" with the stub answering
     confirm+correction (add=[pork], remove=[chicken]); confirm; /recommend.
     Control: a fresh session with [egg, pork] and an empty exclude list.
  B  first message "ไม่เอาหมู" (real /extract), then a stubbed confirm+correction with
     remove=[pork]: does pork stay excluded?
  C  detected [chicken, egg]; "ไม่เอาไข่" with the stub answering remove=[egg]; confirm;
     /recommend. Control: a fresh session with [chicken] and an empty exclude list.

History: written to demonstrate that a removal at /confirm banned dishes (exclude=[chicken]);
after api/app.py started passing ban_excluded=False, A and C are expected to read NOT BANNED
with an empty exclude list, and B (a first-message "no pork") to keep pork excluded.

Verdict "BANNED" = the exclude list holds the removed ingredient, OR the session's top-3
differs from the control's only because dishes containing it (as a main ingredient or
seasoning, the fields recommend() filters on) were filtered out. Otherwise "NOT BANNED".
"""

import contextlib
import io
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from fastapi.testclient import TestClient

import eval_intent_cases as harness
from api import app as app_module
from api import intent, state, web_config
from recommender.recommend import recommend as real_recommend


@contextlib.contextmanager
def stubbed_llm(label: str, add: list[str], remove: list[str]):
    """The intent classifier answers with one fixed report_intent call; no network."""
    stub = harness.StubClient(label, add, remove)
    with mock.patch.object(web_config, "ANTHROPIC_API_KEY", harness.FAKE_KEY), \
            mock.patch.object(intent, "_get_client", lambda: stub):
        yield stub


def post(http: TestClient, path: str, payload: dict) -> dict:
    app_module.limiter.reset()
    log = io.StringIO()
    with contextlib.redirect_stdout(log):               # swallow "[recommend] ..." / "[intent] ..." log lines
        response = http.post(path, json=payload)
    assert response.status_code == 200, (path, response.status_code, response.text)
    return response.json()


def recipes_view(recipes: list[dict], banned_key: str) -> list[dict]:
    return [
        {
            "id": r["id"],
            "name_th": r["name_th"],
            "has_key": banned_key in r["main_ingredients"] or banned_key in r["seasonings"],
        }
        for r in recipes
    ]


def recommend(http: TestClient, session_id: str, top_n: int) -> dict:
    return post(http, "/recommend", {"session_id": session_id, "top_n": top_n})


def confirm_flow(http: TestClient, sess, sentence: str, add: list[str], remove: list[str]) -> dict:
    """/confirm with a stubbed correction, then /confirm 'yes', ready for /recommend."""
    with stubbed_llm("confirm+correction", add, remove):
        first = post(http, "/confirm", {"session_id": sess.session_id, "reply": sentence})
    with stubbed_llm("confirm", [], []):
        second = post(http, "/confirm", {"session_id": sess.session_id, "reply": "ใช่"})
    return {"first": first, "second": second}


def fresh_confirmed_session(ingredients: list[str]):
    """A control session: given ingredients, empty exclude list, stage confirmed."""
    sess = state.store.create()
    sess.include = list(ingredients)
    sess.stage = state.STAGE_CONFIRMED
    return sess


def removal_scenario(http: TestClient, name: str, detected: list[str], sentence: str,
                     add: list[str], remove: list[str], control: list[str], key: str) -> dict:
    state.store.clear()
    sess = state.store.create()
    sess.detected = {k: 0.9 for k in detected}
    sess.stage = state.STAGE_AWAITING_CONFIRM

    flow = confirm_flow(http, sess, sentence, add, remove)
    used = recommend(http, sess.session_id, 3)
    after = state.store.get(sess.session_id)
    top3 = recipes_view(used["recipes"], key)

    ctrl_sess = fresh_confirmed_session(control)
    ctrl_top10 = recipes_view(recommend(http, ctrl_sess.session_id, 10)["recipes"], key)
    ctrl_top3 = ctrl_top10[:3]

    # Supplementary, beyond /recommend's top_n cap of 10: where do dishes containing `key` sit in the
    # control's FULL ranking? (the real recommend(), same arguments, top_k = whole catalogue)
    with contextlib.redirect_stdout(io.StringIO()):
        full = real_recommend(ingredients=list(control), health_tags=[], excluded=[], top_k=400, seasonings=[])
    ranks = [i for i, d in enumerate(full, start=1) if key in d["main_ingredients"] or key in d["seasonings"]]
    control_full = {"scored": len(full), "with_key": len(ranks), "first_rank": ranks[0] if ranks else None}

    in_exclude = key in after.exclude
    missing_from_session = [r for r in ctrl_top3 if r["id"] not in {x["id"] for x in top3}]
    only_because_filtered = bool(missing_from_session) and all(r["has_key"] for r in missing_from_session)
    return {
        "name": name, "sentence": sentence, "key": key,
        "intent": flow["first"]["intent"], "stage_after_correction": flow["first"]["stage"],
        "ingredients": after.ingredients, "exclude": list(after.exclude),
        "used": used["used"], "top3": top3,
        "control_ingredients": control, "control_top3": ctrl_top3, "control_top10": ctrl_top10,
        "control_full": control_full,
        "in_exclude": in_exclude, "only_because_filtered": only_because_filtered,
        "verdict": "BANNED" if (in_exclude or only_because_filtered) else "NOT BANNED",
    }


def scenario_b(http: TestClient) -> dict:
    state.store.clear()
    first = post(http, "/extract", {"text": "มีไข่กับไก่ ไม่เอาหมู"})          # the real keyword extractor
    sid = first["session_id"]
    before = state.store.get(sid)
    before_view = {"ingredients": before.ingredients, "exclude": list(before.exclude)}
    with stubbed_llm("confirm+correction", [], ["หมู"]):
        resp = post(http, "/confirm", {"session_id": sid, "reply": "เอาหมูออก"})
    after = state.store.get(sid)
    return {
        "first_message": "มีไข่กับไก่ ไม่เอาหมู", "before": before_view,
        "intent": resp["intent"], "stage": resp["stage"], "corrections": resp["corrections"],
        "ingredients": after.ingredients, "exclude": list(after.exclude),
        "pork_still_excluded": "pork" in after.exclude,
    }


def fmt(recipes: list[dict]) -> str:
    return "; ".join(f"{r['id']} {r['name_th']}" for r in recipes) or "(none)"


def print_removal(result: dict) -> None:
    key = result["key"]
    print(f"### Scenario {result['name']}: {result['sentence']}  (stub: confirm+correction, removes {key})")
    print(f"- intent returned: {result['intent']} -> stage {result['stage_after_correction']}")
    print(f"- session ingredients: {result['ingredients']}")
    print(f"- session exclude:     {result['exclude']}")
    print(f"- /recommend used:     ingredients={result['used']['ingredients']} exclude={result['used']['exclude']}")
    print(f"- session top-3:       {fmt(result['top3'])}")
    print(f"- control ({result['control_ingredients']}, empty exclude) top-3: {fmt(result['control_top3'])}")
    print(f"- control top-10 (marked = {key} is a main ingredient or seasoning):")
    for i, r in enumerate(result["control_top10"], start=1):
        mark = f"  <-- contains {key}" if r["has_key"] else ""
        print(f"    {i:>2}. {r['id']} {r['name_th']}{mark}")
    lost = sum(1 for r in result["control_top10"] if r["has_key"])
    print(f"- {lost} of the control's top-10 contain {key} and would be lost if it were banned")
    full = result["control_full"]
    print(f"- control full ranking: {full['scored']} scored dishes, {full['with_key']} contain {key}, "
          f"first one at rank {full['first_rank']}")
    print(f"- exclude holds {key}: {result['in_exclude']} | top-3 differs only because of the filter: "
          f"{result['only_because_filtered']}")
    print(f"- VERDICT: {result['verdict']}\n")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    with mock.patch.object(app_module, "_load_detector", lambda: None):
        with TestClient(app_module.app) as http:
            a = removal_scenario(http, "A", ["chicken", "egg"], "ไม่ใช่ไก่ แต่เป็นหมู",
                                 ["หมู"], ["ไก่"], ["egg", "pork"], "chicken")
            b = scenario_b(http)
            c = removal_scenario(http, "C", ["chicken", "egg"], "ไม่เอาไข่",
                                 [], ["ไข่"], ["chicken"], "egg")
    state.store.clear()
    app_module.limiter.reset()

    print_removal(a)
    print("### Scenario B: first message excludes pork, then a stubbed confirm+correction removes pork")
    print(f"- first message:   {b['first_message']}")
    print(f"- before /confirm: ingredients={b['before']['ingredients']} exclude={b['before']['exclude']}")
    print(f"- /confirm answer: {b['intent']} corrections={b['corrections']} -> stage {b['stage']}")
    print(f"- final:           ingredients={b['ingredients']} exclude={b['exclude']}")
    print(f"- pork still excluded: {b['pork_still_excluded']}\n")
    print_removal(c)

    print("### Summary")
    print("| scenario | ingredients | exclude | top-3 | verdict |")
    print("|---|---|---|---|---|")
    for r in (a, c):
        print(f"| {r['name']} | {r['ingredients']} | {r['exclude']} | {fmt(r['top3'])} | {r['verdict']} |")
    print(f"| B | {b['ingredients']} | {b['exclude']} | - | pork still excluded: {b['pork_still_excluded']} |")


if __name__ == "__main__":
    main()
