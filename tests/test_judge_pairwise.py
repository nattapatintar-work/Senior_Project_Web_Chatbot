"""
tests/test_judge_pairwise.py
============================
Offline tests for tools/judge_pairwise.py using the MockClient and synthetic data. No real API call is
ever made; the real client factory is never built, and an injected stand-in is used where the real path matters.

Run with:
    pytest tests/test_judge_pairwise.py -v
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import judge_pairwise as jp

SENTINEL_KEY = "sk-ant-TEST-SENTINEL-KEY-0123456789"


class FakeApiError(Exception):
    def __init__(self, status_code, message="boom"):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def f_queries(n=8):
    return [{"id": f"F{i}", "ingredients": ["chicken"], "seasonings": ["sugar"], "health_tags": [], "excluded": [],
             "category": "all"} for i in range(1, n + 1)]


def fake_top3(designed=None):
    """top3_fn: every query has its own base list; `designed` maps (query, weight) to another list."""
    designed = designed or {}

    def fn(query, weight):
        if (query["id"], weight) in designed:
            return designed[(query["id"], weight)]
        return [f"{query['id']}_a", f"{query['id']}_b", f"{query['id']}_c"]
    return fn


def real_id_top3():
    """top3_fn over REAL recipe ids so the prompt builder can read recipes.json; weights shift the list."""
    ids = sorted(jp.load_data()["recipes"])
    shift = {0.0: 3, 0.15: 0, 0.3: 0, 0.5: 1}

    def fn(query, weight):
        i = int(query["id"][1:]) * 3
        return ids[i + shift[weight]: i + shift[weight] + 3]
    return fn


class AnyRecipes(dict):
    """Recipes keyed by id; an unknown id (the synthetic plan ids) gets a copy of r1 so prompts can be built."""

    def __missing__(self, rid):
        return {**self["r1"], "id": rid}


def tiny_data():
    return {"ingredients": {"chicken": {"name_th": "ไก่"}, "sugar": {"name_th": "น้ำตาล"}},
            "recipes": AnyRecipes({"r1": {"id": "r1", "name_th": "จานหนึ่ง", "category": "savory",
                                          "main_ingredients": ["chicken"], "optional_ingredients": [],
                                          "seasonings": ["sugar"]},
                                   "r2": {"id": "r2", "name_th": "จานสอง", "category": "dessert",
                                          "main_ingredients": ["chicken"], "optional_ingredients": ["sugar"],
                                          "seasonings": []}})}


def one_call(order="cand_first"):
    a_is, b_is = ("candidate", "reference") if order == "cand_first" else ("reference", "candidate")
    return {"call_id": "c001", "kind": "compare", "query": "F1", "list_a": ["r1"], "list_b": ["r2"],
            "a_is": a_is, "b_is": b_is, "candidate_weight": 0.0, "run": 1, "order": order}


def runner(client, **kw):
    return jp.Runner(client, "test-model", sleep=kw.pop("sleep", lambda s: None), data=tiny_data(), **kw)


# ---------------------------------------------------------------------------
# plan: identical pairs skipped, order-only pairs judged
# ---------------------------------------------------------------------------

def test_identical_pairs_are_skipped_and_reordered_pairs_are_judged():
    designed = {("F1", 0.0): ["F1_x", "F1_y", "F1_z"],            # different
                ("F1", 0.5): ["F1_c", "F1_b", "F1_a"]}            # same ids, different order
    plan = jp.build_plan(f_queries(), top3_fn=fake_top3(designed), runs=3)
    status = {(c["query"], c["candidate_weight"]): c["status"] for c in plan["comparisons"]}
    assert status[("F1", 0.0)] == "different"
    assert status[("F1", 0.15)] == "identical"
    assert status[("F1", 0.5)] == "reordered"
    f1_calls = [c for c in plan["calls"] if c["kind"] == "compare" and c["query"] == "F1"]
    assert {c["candidate_weight"] for c in f1_calls} == {0.0, 0.5}          # 0.15 (identical) has no calls
    assert len(f1_calls) == 2 * (2 * 3)                                      # 2 weights x 2 orders x 3 runs
    assert plan["n_identical"] == len(f_queries()) * 3 - 2                    # everything else is identical


def test_every_judged_pair_is_run_in_both_orders_and_every_run():
    designed = {("F2", 0.0): ["F2_x", "F2_y", "F2_z"]}
    plan = jp.build_plan(f_queries(), top3_fn=fake_top3(designed), runs=3)
    calls = [c for c in plan["calls"] if c["kind"] == "compare"]
    assert sorted((c["run"], c["order"]) for c in calls) == sorted((r, o) for r in (1, 2, 3) for o in ("cand_first", "ref_first"))
    cand_first = next(c for c in calls if c["order"] == "cand_first")
    ref_first = next(c for c in calls if c["order"] == "ref_first" and c["run"] == cand_first["run"])
    assert cand_first["list_a"] == ref_first["list_b"] and cand_first["list_b"] == ref_first["list_a"]
    assert (cand_first["a_is"], cand_first["b_is"]) == ("candidate", "reference")
    assert (ref_first["a_is"], ref_first["b_is"]) == ("reference", "candidate")


def test_negative_controls_use_the_query_four_positions_away_in_both_orders():
    plan = jp.build_plan(f_queries(), top3_fn=fake_top3(), runs=3)
    controls = [c for c in plan["calls"] if c["kind"] == "control"]
    assert len(controls) == 16                                               # 8 queries x 2 orders x 1 run
    assert {c["other_query"] for c in controls if c["query"] == "F1"} == {"F5"}
    assert {c["other_query"] for c in controls if c["query"] == "F6"} == {"F2"}
    pair = [c for c in controls if c["query"] == "F1"]
    assert {c["order"] for c in pair} == {"real_first", "foreign_first"} and all(c["run"] == 1 for c in pair)


def test_summarize_plan_counts_by_weight_order_run_and_controls():
    designed = {("F1", 0.0): ["x", "y", "z"], ("F2", 0.5): ["p", "q", "r"]}
    plan = jp.build_plan(f_queries(), top3_fn=fake_top3(designed), runs=3)
    s = jp.summarize_plan(plan, 150)
    assert s["comparison_calls"] == 12 and s["control_calls"] == 16 and s["total_calls"] == 28
    assert s["calls_by_candidate_weight"] == {0.0: 6, 0.5: 6}
    assert s["comparison_calls_by_run"] == {1: 4, 2: 4, 3: 4}
    assert s["calls_by_order"] == {"cand_first": 6, "ref_first": 6, "real_first": 8, "foreign_first": 8}
    assert len(s["identical_skipped"]) == 22


# ---------------------------------------------------------------------------
# the seasoning weight is only changed temporarily
# ---------------------------------------------------------------------------

def test_the_seasoning_weight_is_restored_after_use_and_after_an_exception():
    import recommender.recommend as rec
    before = rec.SEASONING_WEIGHT
    with jp.seasoning_weight(0.5):
        assert rec.SEASONING_WEIGHT == 0.5
    assert rec.SEASONING_WEIGHT == before
    with pytest.raises(RuntimeError):
        with jp.seasoning_weight(0.0):
            raise RuntimeError("boom")
    assert rec.SEASONING_WEIGHT == before


def test_top3_uses_the_temporary_weight_and_leaves_it_restored():
    import recommender.recommend as rec
    query = {"ingredients": ["chicken"], "seasonings": ["sugar", "soy_sauce"], "health_tags": [], "excluded": [], "category": "all"}
    before = rec.SEASONING_WEIGHT
    ids_zero, ids_default = jp.top3(query, 0.0), jp.top3(query, jp.REFERENCE_WEIGHT)
    assert len(ids_zero) == len(ids_default) == 3
    assert rec.SEASONING_WEIGHT == before == jp.REFERENCE_WEIGHT


# ---------------------------------------------------------------------------
# prompt
# ---------------------------------------------------------------------------

def test_the_user_message_is_data_only_with_no_scores_weights_or_which_list_is_new():
    query = {"ingredients": ["chicken"], "seasonings": ["sugar"]}
    user = jp.build_user_message(query, ["r1"], ["r2"], tiny_data())
    for text in (user, jp.JUDGE_SYSTEM_PROMPT):
        assert not re.search(r"\b(score|scores|weight|weights|new|old|baseline|candidate|reference)\b", text, re.I), text
    assert "List A:" in user and "List B:" in user and user.index("List A:") < user.index("List B:")
    assert "chicken (ไก่)" in user and "sugar (น้ำตาล)" in user
    assert "จานหนึ่ง" in user and "จานสอง" in user and "category: dessert" in user


def test_the_prompt_data_comes_from_the_json_files_at_call_time(tmp_path, monkeypatch):
    (tmp_path / "recipes.json").write_text(json.dumps([{"id": "t1", "name_th": "ชื่อทดสอบ", "category": "savory",
                                                      "main_ingredients": ["chicken"], "optional_ingredients": [],
                                                      "seasonings": []}], ensure_ascii=False), encoding="utf-8")
    (tmp_path / "ingredients.json").write_text(json.dumps({"chicken": {"name_th": "ไก่ทดสอบ"}}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(jp, "RECIPES_PATH", tmp_path / "recipes.json")
    monkeypatch.setattr(jp, "INGREDIENTS_PATH", tmp_path / "ingredients.json")
    user = jp.build_user_message({"ingredients": ["chicken"], "seasonings": []}, ["t1"], ["t1"])
    assert "ชื่อทดสอบ" in user and "ไก่ทดสอบ" in user
    assert "Seasonings the user has ticked: none" in user


def test_the_criteria_are_stated_in_priority_order():
    p = jp.JUDGE_SYSTEM_PROMPT
    assert p.index("1. ") < p.index("2. ") < p.index("3. ")
    assert "MAIN ingredients" in p.split("2. ")[0]
    assert "already ticked" in p.split("2. ")[1].split("3. ")[0]
    assert "Rank order matters" in p.split("3. ")[1]


def test_the_tool_schema_puts_reasoning_first_and_forces_a_short_json_answer():
    props = list(jp.JUDGE_TOOL["input_schema"]["properties"])
    assert props == ["reasoning", "winner", "confidence"]
    assert jp.JUDGE_TOOL["input_schema"]["properties"]["winner"]["enum"] == ["A", "B", "tie"]


# ---------------------------------------------------------------------------
# judging one call: parse errors, retries, adaptation
# ---------------------------------------------------------------------------

def test_a_valid_answer_is_recorded_with_usage_and_the_parameters_sent():
    client = jp.MockClient(policy="A")
    rec = runner(client).judge(one_call(), {"ingredients": ["chicken"], "seasonings": ["sugar"]})
    assert rec["status"] == "ok" and rec["response"]["winner"] == "A" and rec["attempts"] == 1
    assert rec["usage"]["output_tokens"] == 100 and rec["request_id"].startswith("mock_")
    assert rec["params_sent"]["tool_choice"] == "tool" and rec["params_sent"]["temperature_sent"] is True
    assert rec["prompt_system"] == jp.JUDGE_SYSTEM_PROMPT and "List A:" in rec["prompt_user"]
    kwargs = client.requests[0]
    assert kwargs["extra_body"] == {"temperature": 0} and kwargs["thinking"] == {"type": "disabled"}
    assert kwargs["tool_choice"] == {"type": "tool", "name": jp.TOOL_NAME} and kwargs["max_tokens"] == jp.MAX_TOKENS


def test_a_parse_failure_is_retried_once_then_recorded_as_parse_error():
    client = jp.MockClient(script=["garbage", "garbage"])
    rec = runner(client).judge(one_call(), {"ingredients": ["chicken"]})
    assert rec["status"] == "parse_error" and rec["attempts"] == 2 and rec["response"] is None
    assert len(client.requests) == 2                                         # never more than one retry


def test_a_parse_failure_followed_by_a_good_answer_is_ok():
    client = jp.MockClient(script=["garbage"], policy="B")
    rec = runner(client).judge(one_call(), {"ingredients": ["chicken"]})
    assert rec["status"] == "ok" and rec["attempts"] == 2 and rec["response"]["winner"] == "B"


@pytest.mark.parametrize("bad", [
    {"reasoning": "", "winner": "A", "confidence": 2},
    {"reasoning": "x", "winner": "C", "confidence": 2},
    {"reasoning": "x", "winner": "A", "confidence": 4},
    {"reasoning": "x", "winner": "A", "confidence": True},
    {"reasoning": "x", "winner": "A"},
])
def test_parse_response_rejects_invalid_tool_input(bad):
    resp = jp.MockClient._response(bad, "u")
    assert jp.parse_response(resp) is None


def test_a_truncated_response_is_not_parsed():
    resp = jp.MockClient._response({"reasoning": "x", "winner": "A", "confidence": 2}, "u")
    resp.stop_reason = "max_tokens"
    assert jp.parse_response(resp) is None


def test_a_429_is_retried_with_backoff_then_succeeds():
    sleeps = []
    client = jp.MockClient(script=[FakeApiError(429)], policy="A")
    rec = runner(client, sleep=sleeps.append).judge(one_call(), {"ingredients": ["chicken"]})
    assert rec["status"] == "ok" and rec["attempts"] == 2 and sleeps == [jp.BACKOFF_SECONDS[0]]


def test_api_errors_stop_after_two_retries_and_become_api_error():
    sleeps = []
    client = jp.MockClient(script=[FakeApiError(500), FakeApiError(529), FakeApiError(503)])
    rec = runner(client, sleep=sleeps.append).judge(one_call(), {"ingredients": ["chicken"]})
    assert rec["status"] == "api_error" and rec["attempts"] == 3 and len(client.requests) == 3
    assert sleeps == [jp.BACKOFF_SECONDS[0], jp.BACKOFF_SECONDS[1]]
    assert "status=503" in rec["error"]


def test_a_client_error_other_than_400_is_not_retried():
    client = jp.MockClient(script=[FakeApiError(401, "invalid key")])
    rec = runner(client).judge(one_call(), {"ingredients": ["chicken"]})
    assert rec["status"] == "api_error" and rec["attempts"] == 1


def test_an_http_400_naming_temperature_switches_it_off_once_and_for_the_rest_of_the_run():
    client = jp.MockClient(script=[FakeApiError(400, "temperature: sampling parameters are not supported")], policy="A")
    r = runner(client)
    first = r.judge(one_call(), {"ingredients": ["chicken"]})
    assert first["status"] == "ok" and first["attempts"] == 2
    assert "extra_body" in client.requests[0] and "extra_body" not in client.requests[1]
    assert first["params_sent"]["temperature_sent"] is False and first["adaptations"] == ["temperature switched off after an HTTP 400"]
    second = r.judge(one_call("ref_first"), {"ingredients": ["chicken"]})
    assert second["attempts"] == 1 and "extra_body" not in client.requests[2]


def test_an_http_400_naming_tool_choice_falls_back_to_auto_with_an_instruction():
    client = jp.MockClient(script=[FakeApiError(400, "tool_choice 'tool' is not supported for this model")], policy="A")
    rec = runner(client).judge(one_call(), {"ingredients": ["chicken"]})
    assert rec["status"] == "ok" and client.requests[1]["tool_choice"] == {"type": "auto"}
    assert rec["prompt_system"].endswith(jp.AUTO_TOOL_CHOICE_SUFFIX)


def test_an_unrelated_http_400_is_not_adapted_and_not_retried():
    client = jp.MockClient(script=[FakeApiError(400, "messages: invalid")])
    rec = runner(client).judge(one_call(), {"ingredients": ["chicken"]})
    assert rec["status"] == "api_error" and rec["attempts"] == 1


def test_the_no_temperature_option_never_sends_it():
    client = jp.MockClient(policy="A")
    runner(client, send_temperature=False).judge(one_call(), {"ingredients": ["chicken"]})
    assert "extra_body" not in client.requests[0]


def test_error_text_is_redacted_before_it_is_stored():
    client = jp.MockClient(script=[FakeApiError(401, f"bad key {SENTINEL_KEY}")])
    rec = runner(client, secrets=(SENTINEL_KEY,)).judge(one_call(), {"ingredients": ["chicken"]})
    assert SENTINEL_KEY not in json.dumps(rec) and "[REDACTED]" in rec["error"]


# ---------------------------------------------------------------------------
# the hard cap
# ---------------------------------------------------------------------------

def test_the_cap_aborts_before_the_first_call_when_the_plan_is_too_big(tmp_path):
    plan = jp.build_plan(f_queries(), top3_fn=fake_top3({("F1", 0.0): ["x", "y", "z"]}), runs=3)
    client = jp.MockClient()
    with pytest.raises(jp.CapExceeded):
        jp.run_plan(plan, {q["id"]: q for q in f_queries()}, runner(client, max_calls=plan["n_calls"] - 1), tmp_path, "MOCK")
    assert client.requests == []


def test_the_cap_also_counts_retries_and_stops_the_run_cleanly(tmp_path):
    plan = jp.build_plan(f_queries(), top3_fn=fake_top3({("F1", 0.0): ["x", "y", "z"]}), runs=1)
    plan["calls"] = plan["calls"][:2]
    plan["n_calls"] = 2
    client = jp.MockClient(script=[FakeApiError(429), FakeApiError(429)], policy="A")
    r = runner(client, max_calls=3)
    summary = jp.run_plan(plan, {q["id"]: q for q in f_queries()}, r, tmp_path, "MOCK")
    assert r.requests_made == 3 and len(client.requests) == 3
    assert summary["aborted"] and "MAX_CALLS" in summary["aborted"] and summary["judged_calls"] == 1


def test_check_cap_passes_at_exactly_the_cap():
    jp.check_cap(150, 150)
    with pytest.raises(jp.CapExceeded):
        jp.check_cap(151, 150)


# ---------------------------------------------------------------------------
# a full mock run through main()
# ---------------------------------------------------------------------------

def _main(args, **kw):
    return jp.main(args, top3_fn=real_id_top3(), sleep=lambda s: None, **kw)


def test_a_full_mock_run_writes_the_plan_the_raw_calls_and_a_summary(tmp_path, capsys):
    assert _main(["--mock", "--runs", "2", "--out-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "MODE: MOCK" in out and "CALL PLAN" in out
    plan = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    lines = [json.loads(line) for line in (tmp_path / "raw_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert plan["mode"] == "MOCK" and len(lines) == plan["n_calls"]
    assert all(rec["mode"] == "MOCK" and rec["status"] == "ok" and rec["prompt_user"] and rec["response"] for rec in lines)
    assert {rec["kind"] for rec in lines} == {"compare", "control"}
    summary = json.loads((tmp_path / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["requests_made"] == plan["n_calls"] and summary["aborted"] is None


def test_the_default_mode_is_mock_and_uses_a_temporary_directory(capsys):
    assert _main(["--runs", "1"]) == 0
    out = capsys.readouterr().out
    assert "MODE: MOCK" in out and "judge_f_mock_" in out


def test_dry_run_prints_the_plan_and_the_cost_formula_and_calls_nothing(tmp_path, capsys):
    def boom(key):
        raise AssertionError("no client may be built in a dry run")
    assert _main(["--dry-run", "--real", "--out-dir", str(tmp_path / "x")], client_factory=boom) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "total planned calls" in out and "identical pairs skipped" in out
    assert "UNVERIFIED placeholders" in out and "PRICE_IN" in out
    assert not (tmp_path / "x").exists()


def test_supplied_prices_give_a_dollar_range_and_none_gives_none():
    plan = jp.build_plan(f_queries(), top3_fn=fake_top3({("F1", 0.0): ["r1", "r2", "r1"]}), runs=1)
    queries = {q["id"]: q for q in f_queries()}
    data = tiny_data()
    plan["calls"] = [c for c in plan["calls"] if c["kind"] == "compare"]
    no_price = jp.estimate_cost(plan, queries, data, None, None)
    assert no_price["cost_low_usd"] is None and no_price["cost_high_usd"] is None
    priced = jp.estimate_cost(plan, queries, data, 2.0, 10.0)
    assert 0 < priced["cost_low_usd"] < priced["cost_high_usd"]
    assert priced["n_calls"] == len(plan["calls"]) and priced["avg_input_tokens_proxy_low"] < priced["avg_input_tokens_proxy_high"]


def test_the_placeholder_prices_are_unverified_none():
    assert jp.PRICE_IN is None and jp.PRICE_OUT is None


# ---------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------

class GuardedEnviron(dict):
    """An os.environ stand-in that fails the test if ANTHROPIC_API_KEY is touched."""

    def _check(self, key):
        if key == "ANTHROPIC_API_KEY":
            raise AssertionError("ANTHROPIC_API_KEY was read")

    def get(self, key, default=None):
        self._check(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self._check(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self._check(key)
        return super().__contains__(key)


def test_mock_mode_never_reads_the_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(jp.os, "environ", GuardedEnviron({"ANTHROPIC_API_KEY": SENTINEL_KEY}))
    assert _main(["--mock", "--runs", "1", "--out-dir", str(tmp_path)]) == 0


def test_dry_run_never_reads_the_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(jp.os, "environ", GuardedEnviron({"ANTHROPIC_API_KEY": SENTINEL_KEY}))
    assert _main(["--dry-run"]) == 0


def test_real_mode_without_a_key_exits_with_a_clear_message_and_builds_no_client(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def boom(key):
        raise AssertionError("a client was built without a key")
    assert _main(["--real", "--runs", "1", "--out-dir", str(tmp_path / "real")], client_factory=boom) == 2
    out = capsys.readouterr().out
    assert "ANTHROPIC_API_KEY is not set" in out and ".env" in out
    assert not (tmp_path / "real").exists()


def test_real_mode_refuses_a_non_empty_output_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL_KEY)
    (tmp_path / "old.txt").write_text("x", encoding="utf-8")

    def boom(key):
        raise AssertionError("no client may be built")
    assert _main(["--real", "--out-dir", str(tmp_path)], client_factory=boom) == 2
    assert "not empty" in capsys.readouterr().out


def test_the_key_never_appears_in_stdout_stderr_or_any_output_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL_KEY)
    seen = {}

    def factory(key):
        seen["key"] = key
        # every request fails and its error text carries the key, to prove it is redacted before storing
        return jp.MockClient(script=[FakeApiError(401, f"invalid x-api-key {SENTINEL_KEY}")] * 400)
    code = _main(["--real", "--runs", "1", "--out-dir", str(tmp_path / "run")], client_factory=factory)
    captured = capsys.readouterr()
    assert code == 0 and seen["key"] == SENTINEL_KEY
    assert SENTINEL_KEY not in captured.out and SENTINEL_KEY not in captured.err
    files = list((tmp_path / "run").iterdir())
    assert files
    for path in files:
        assert SENTINEL_KEY not in path.read_text(encoding="utf-8"), path.name
    summary = json.loads((tmp_path / "run" / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "REAL" and summary["status_counts"] == {"api_error": summary["judged_calls"]}


def test_the_real_client_factory_builds_a_client_with_sdk_retries_off(monkeypatch):
    import types
    created = {}

    class FakeAnthropic:
        def __init__(self, **kw):
            created.update(kw)
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=FakeAnthropic))
    jp.make_real_client("k")
    assert created["api_key"] == "k" and created["max_retries"] == 0


def test_the_judge_model_defaults_to_claude_sonnet_5_and_can_be_overridden(monkeypatch):
    monkeypatch.delenv("JUDGE_MODEL", raising=False)
    assert jp.judge_model() == "claude-sonnet-5"
    monkeypatch.setenv("JUDGE_MODEL", "some-other-model")
    assert jp.judge_model() == "some-other-model"
