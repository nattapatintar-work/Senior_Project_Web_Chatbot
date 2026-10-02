"""
tools/judge_pairwise.py
=======================
LLM-as-judge pairwise comparison for the SEASONING_WEIGHT experiment on group F.

    python tools/judge_pairwise.py --dry-run                     # print the call plan + cost estimate, call nothing
    python tools/judge_pairwise.py --mock --out-dir <dir>        # mock client (the default mode): no network, no key
    python tools/judge_pairwise.py --real --out-dir data/eval/judge_f_v1   # REAL calls: needs ANTHROPIC_API_KEY

The JUDGE is this script plus an API model with a fixed prompt. A person (or Claude Code) never decides a
comparison. Reads data/eval/test_set_extra_v1.json (the 8 F queries), data/recipes.json and
data/ingredients.json (at run time, for the prompt text), and calls recommender.recommend() with a
temporarily changed recommender.recommend.SEASONING_WEIGHT (read at call time: recommend.py:75 defines it,
recommend.py:314 uses it; the value is restored after every call).

DESIGN
------
  Weights   0.0, 0.15, 0.3 (reference, the current value), 0.5.
  Pairs     candidate (0.0 / 0.15 / 0.5) vs the 0.3 top-3 of the same F query. Identical top-3 (same ids, same
            order) are NOT judged ("identical", cost zero); same ids in a different order ARE judged.
  Each judged pair is shown in BOTH presentation orders (A/B swapped) and repeated RUNS times.
  Negative controls (judge reliability): for each F query the real 0.3 top-3 vs the 0.3 top-3 of an unrelated F
  query (4 positions away in id order), shown in both orders, 1 run. A competent judge must prefer the real list.
  MAX_CALLS is a hard cap on API requests: checked against the plan before the first call, and before every
  request (retries, parse re-asks and 400 re-sends all count).

NOT VERIFIED (read before a real run)
-------------------------------------
  * The default judge model id "claude-sonnet-5" (the id used for the project's extraction fallback in
    api/web_config.py) has never been verified against the API. Override it with the JUDGE_MODEL env variable.
  * Notes bundled with Claude Code's claude-api skill (not checked against the live API) say Sonnet 5 may
    reject a `temperature` value, runs adaptive thinking unless it is disabled, and (on Sonnet 5.5) rejects a
    forced `tool_choice`. So the first request sends temperature 0 and thinking disabled and a forced tool
    call as required; if the API answers HTTP 400 mentioning one of them, that parameter is switched off for
    the rest of the run, the switch is recorded in raw_calls.jsonl, and the request is re-sent. A 400 is not billed.
  * PRICE_IN / PRICE_OUT are UNVERIFIED placeholders (None). Supply real prices with --price-in/--price-out.
  * The expected output size and the characters-per-token ratios in the cost estimate are assumptions.

SECRETS
-------
  The API key is read ONLY from the process environment (ANTHROPIC_API_KEY), ONLY in --real mode. The .env file is
  not read by this script. The key is never printed, logged or written; error text is redacted before storing.

OUTPUT (one directory per run)
------------------------------
  plan.json        the plan (comparisons, controls, identical pairs, settings, mode MOCK/REAL)
  raw_calls.jsonl  one line per judged call: both lists, full prompt text, response, order, run, tokens, status
  run_summary.json status counts, requests made, token totals, parameter adaptations
tools/judge_report.py turns these files into metrics.json and report.md.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

RECIPES_PATH = ROOT / "data" / "recipes.json"
INGREDIENTS_PATH = ROOT / "data" / "ingredients.json"
EXTRA_SET_PATH = ROOT / "data" / "eval" / "test_set_extra_v1.json"
DEFAULT_REAL_OUT_DIR = ROOT / "data" / "eval" / "judge_f_v1"

# ---------------------------------------------------------------------------
# Settings (all definitions we chose, none derived from data)
# ---------------------------------------------------------------------------
JUDGE_MODEL_DEFAULT = "claude-sonnet-5"        # UNVERIFIED against the API; override with env JUDGE_MODEL
REFERENCE_WEIGHT = 0.3                         # recommender.recommend.SEASONING_WEIGHT today
CANDIDATE_WEIGHTS = (0.0, 0.15, 0.5)
RUNS = 3
MAX_CALLS = 150                                # hard cap on API requests
MAX_TOKENS = 400                               # the answer is short (a tool call with 2-4 sentences of reasoning)
CONTROL_OFFSET = 4                             # control list = the F query this many positions away (8 queries)
MAX_RETRIES = 2                                # 429 / 5xx / connection errors; then "api_error"
BACKOFF_SECONDS = (1.0, 3.0)
PARSE_RETRIES = 1                              # a response that fails validation is re-asked once
TOOL_NAME = "report_judgement"

# UNVERIFIED placeholders: no price lookup is possible offline and none is invented here.
PRICE_IN = None                                # USD per million input tokens  (UNVERIFIED -> pass --price-in)
PRICE_OUT = None                               # USD per million output tokens (UNVERIFIED -> pass --price-out)
EXPECTED_OUTPUT_TOKENS = (80, 250)             # assumption: a short tool call
CHARS_PER_TOKEN_LOW = 4.0                      # rough proxy for English-like text (gives the LOW token estimate)
CHARS_PER_TOKEN_HIGH = 1.5                     # conservative proxy for Thai-heavy text (gives the HIGH token estimate)

JUDGE_SYSTEM_PROMPT = """\
You compare two ranked lists of three Thai recipes and decide which list better serves a home cook.

You are given the ingredients the user has, the seasonings the user has already ticked (they have these at home), then List A and List B. Each list has three recipes in rank order, with their main ingredients, optional ingredients and seasonings.

Judge with these criteria, in this priority order:
1. The dishes must be cookable mostly from the user's ingredients: the user's ingredients should appear as MAIN ingredients of the dish, and few main ingredients should be missing.
2. Among dishes that are similar on criterion 1, prefer dishes whose seasonings the user has already ticked, because the user already has those at home.
3. Rank order matters: the best dish for this user should be first.

Use only the data given. Answer by calling the tool report_judgement with: reasoning (2 to 4 short sentences, written first), winner ("A", "B" or "tie"), and confidence (1 = unsure, 2 = fairly sure, 3 = very sure).\
"""

JUDGE_TOOL = {
    "name": TOOL_NAME,
    "description": "Report which of the two ranked lists better serves the user.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string", "description": "2 to 4 short sentences."},
            "winner": {"type": "string", "enum": ["A", "B", "tie"]},
            "confidence": {"type": "integer", "enum": [1, 2, 3]},
        },
        "required": ["reasoning", "winner", "confidence"],
        "additionalProperties": False,
    },
}
AUTO_TOOL_CHOICE_SUFFIX = "\n\nAlways answer by calling the tool report_judgement."


class CapExceeded(Exception):
    """The MAX_CALLS cap would be exceeded."""


class MissingKey(Exception):
    """ANTHROPIC_API_KEY is not set (real mode only)."""


class ApiFailure(Exception):
    """An API request failed for good (after the bounded retries)."""

    def __init__(self, exc: Exception):
        super().__init__(type(exc).__name__)
        self.exc = exc


# ---------------------------------------------------------------------------
# Recommender access (lazy import) and the temporary weight
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def seasoning_weight(value: float):
    """Temporarily set recommender.recommend.SEASONING_WEIGHT; always restored."""
    import recommender.recommend as rec
    old = rec.SEASONING_WEIGHT
    rec.SEASONING_WEIGHT = value
    try:
        yield
    finally:
        rec.SEASONING_WEIGHT = old


def top3(query: dict, weight: float) -> list[str]:
    """Top-3 recipe ids of an F query at a given seasoning weight (same call as tools/eval_dump_top3.py)."""
    import recommender.recommend as rec
    with seasoning_weight(weight), contextlib.redirect_stdout(io.StringIO()):
        dishes = rec.recommend(
            ingredients=query["ingredients"], health_tags=query.get("health_tags", []),
            excluded=query.get("excluded", []), top_k=3, seasonings=list(query.get("seasonings", [])),
            category=query.get("category") or None)
    return [d["id"] for d in dishes]


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def list_status(candidate: list[str], reference: list[str]) -> str:
    if candidate == reference:
        return "identical"
    return "reordered" if set(candidate) == set(reference) else "different"


def build_plan(f_queries: list[dict], top3_fn=top3, runs: int = RUNS,
               candidate_weights=CANDIDATE_WEIGHTS, reference: float = REFERENCE_WEIGHT) -> dict:
    """Comparisons, negative controls and the expanded list of calls. Identical pairs get no calls."""
    queries = sorted(f_queries, key=lambda q: q["id"])
    lists = {(q["id"], w): top3_fn(q, w) for q in queries for w in {*candidate_weights, reference}}

    comparisons = []
    for q in queries:
        for w in candidate_weights:
            cand, ref = lists[(q["id"], w)], lists[(q["id"], reference)]
            comparisons.append({"query": q["id"], "candidate_weight": w, "reference_weight": reference,
                                "candidate_top3": cand, "reference_top3": ref, "status": list_status(cand, ref)})
    controls = []
    for i, q in enumerate(queries):
        other = queries[(i + CONTROL_OFFSET) % len(queries)]
        real, foreign = lists[(q["id"], reference)], lists[(other["id"], reference)]
        controls.append({"query": q["id"], "other_query": other["id"], "real_top3": real, "foreign_top3": foreign,
                         "status": "identical" if real == foreign else "judged"})

    calls = []

    def add(kind, query, a_ids, b_ids, a_is, b_is, **extra):
        calls.append({"call_id": f"c{len(calls) + 1:03d}", "kind": kind, "query": query,
                      "list_a": a_ids, "list_b": b_ids, "a_is": a_is, "b_is": b_is, **extra})

    for c in comparisons:
        if c["status"] == "identical":
            continue
        for run in range(1, runs + 1):
            add("compare", c["query"], c["candidate_top3"], c["reference_top3"], "candidate", "reference",
                candidate_weight=c["candidate_weight"], run=run, order="cand_first")
            add("compare", c["query"], c["reference_top3"], c["candidate_top3"], "reference", "candidate",
                candidate_weight=c["candidate_weight"], run=run, order="ref_first")
    for c in controls:
        if c["status"] == "identical":
            continue
        add("control", c["query"], c["real_top3"], c["foreign_top3"], "real", "foreign",
            other_query=c["other_query"], run=1, order="real_first")
        add("control", c["query"], c["foreign_top3"], c["real_top3"], "foreign", "real",
            other_query=c["other_query"], run=1, order="foreign_first")

    return {"comparisons": comparisons, "controls": controls, "calls": calls, "n_calls": len(calls),
            "n_identical": sum(1 for c in comparisons if c["status"] == "identical"),
            "settings": {"runs": runs, "candidate_weights": list(candidate_weights), "reference_weight": reference}}


def summarize_plan(plan: dict, max_calls: int = MAX_CALLS) -> dict:
    """Counts for the dry-run printout."""
    calls = plan["calls"]
    by_weight, by_order, by_run = {}, {}, {}
    for c in calls:
        if c["kind"] == "compare":
            by_weight[c["candidate_weight"]] = by_weight.get(c["candidate_weight"], 0) + 1
            by_run[c["run"]] = by_run.get(c["run"], 0) + 1
        by_order[c["order"]] = by_order.get(c["order"], 0) + 1
    judged_pairs = [c for c in plan["comparisons"] if c["status"] != "identical"]
    return {
        "total_calls": len(calls), "max_calls": max_calls,
        "comparison_calls": sum(by_weight.values()),
        "calls_by_candidate_weight": dict(sorted(by_weight.items())),
        "calls_by_order": dict(sorted(by_order.items())),
        "comparison_calls_by_run": dict(sorted(by_run.items())),
        "control_calls": sum(1 for c in calls if c["kind"] == "control"),
        "judged_pairs": len(judged_pairs),
        "judged_pairs_by_status": {s: sum(1 for c in judged_pairs if c["status"] == s) for s in ("reordered", "different")},
        "identical_skipped": [(c["query"], c["candidate_weight"]) for c in plan["comparisons"] if c["status"] == "identical"],
        "control_skipped": [c["query"] for c in plan["controls"] if c["status"] == "identical"],
    }


def check_cap(n_calls: int, max_calls: int) -> None:
    if n_calls > max_calls:
        raise CapExceeded(f"the plan needs {n_calls} calls but MAX_CALLS is {max_calls}; nothing was called")


# ---------------------------------------------------------------------------
# Prompt (user message = data only)
# ---------------------------------------------------------------------------

def load_data() -> dict:
    """recipes.json and ingredients.json, read now (never hard-coded into the prompt)."""
    with open(RECIPES_PATH, encoding="utf-8") as f:
        recipes = {r["id"]: r for r in json.load(f)}
    with open(INGREDIENTS_PATH, encoding="utf-8") as f:
        ingredients = json.load(f)
    return {"recipes": recipes, "ingredients": ingredients}


def _named(keys: list[str], ingredients: dict) -> str:
    if not keys:
        return "none"
    return ", ".join(f"{k} ({ingredients.get(k, {}).get('name_th', '?')})" for k in keys)


def _recipe_block(rank: int, recipe: dict, ingredients: dict) -> str:
    return (f"  {rank}. {recipe['id']} | {recipe['name_th']} | category: {recipe['category']}\n"
            f"     main: {_named(recipe['main_ingredients'], ingredients)}\n"
            f"     optional: {_named(recipe['optional_ingredients'], ingredients)}\n"
            f"     seasonings: {_named(recipe['seasonings'], ingredients)}")


def build_user_message(query: dict, list_a: list[str], list_b: list[str], data: dict | None = None) -> str:
    """The user message: the user's ingredients and seasonings, then List A and List B. Data only."""
    data = data or load_data()
    ing, rec = data["ingredients"], data["recipes"]
    parts = [f"Ingredients the user has: {_named(query['ingredients'], ing)}",
             f"Seasonings the user has ticked: {_named(query.get('seasonings', []), ing)}", ""]
    for name, ids in (("List A", list_a), ("List B", list_b)):
        parts.append(f"{name}:")
        parts.extend(_recipe_block(i, rec[rid], ing) for i, rid in enumerate(ids, start=1))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Cost estimate (never spends anything)
# ---------------------------------------------------------------------------

def estimate_cost(plan: dict, queries_by_id: dict, data: dict | None = None,
                  price_in: float | None = PRICE_IN, price_out: float | None = PRICE_OUT) -> dict:
    data = data or load_data()
    tool_chars = len(json.dumps(JUDGE_TOOL))
    chars = [len(JUDGE_SYSTEM_PROMPT) + tool_chars +
             len(build_user_message(queries_by_id[c["query"]], c["list_a"], c["list_b"], data))
             for c in plan["calls"]]
    n = len(chars)
    avg_chars = sum(chars) / n if n else 0.0
    tokens_low, tokens_high = avg_chars / CHARS_PER_TOKEN_LOW, avg_chars / CHARS_PER_TOKEN_HIGH
    out_low, out_high = EXPECTED_OUTPUT_TOKENS
    est = {"n_calls": n, "avg_input_chars": round(avg_chars, 1),
           "avg_input_tokens_proxy_low": round(tokens_low), "avg_input_tokens_proxy_high": round(tokens_high),
           "expected_output_tokens_range": [out_low, out_high],
           "formula": "cost = n_calls * (avg_input_tokens / 1e6 * PRICE_IN + avg_output_tokens / 1e6 * PRICE_OUT)",
           "price_in": price_in, "price_out": price_out, "cost_low_usd": None, "cost_high_usd": None,
           "note": "avg_input_tokens is a characters/token PROXY (4 = low, 1.5 = Thai-heavy high); output size is an "
                   "assumption; prices are UNVERIFIED placeholders unless supplied."}
    if price_in is not None and price_out is not None:
        est["cost_low_usd"] = round(n * (tokens_low / 1e6 * price_in + out_low / 1e6 * price_out), 4)
        est["cost_high_usd"] = round(n * (tokens_high / 1e6 * price_in + out_high / 1e6 * price_out), 4)
    return est


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

def read_api_key() -> str:
    """ANTHROPIC_API_KEY from the process environment only (never from .env)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise MissingKey("ANTHROPIC_API_KEY is not set in the environment. Export it and run again "
                         "(this script does not read the .env file).")
    return key


def make_real_client(key: str):
    """A real Anthropic client. max_retries=0: this script owns the bounded retry loop, so nothing is retried silently."""
    import anthropic
    return anthropic.Anthropic(api_key=key, max_retries=0, timeout=60.0)


class MockClient:
    """
    Deterministic stand-in for the Anthropic client: no network, no key. Every response is labelled MOCK.
    `script` is consumed one item per request before the policy applies: an Exception instance is raised,
    the string "garbage" returns an unparseable response, a dict is returned as the tool input.
    policy: "hash" (pseudo-random but repeatable per prompt), "A", "B", "tie".
    """

    def __init__(self, policy: str = "hash", script: list | None = None):
        self.policy = policy
        self.script = list(script or [])
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        user = kwargs["messages"][0]["content"]
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            if item == "garbage":
                return self._response({"reasoning": "MOCK", "winner": "maybe", "confidence": 9}, user)
            return self._response(item, user)
        if self.policy in ("A", "B", "tie"):
            winner = self.policy
        else:
            winner = "A" if int(hashlib.sha256(user.encode("utf-8")).hexdigest(), 16) % 2 == 0 else "B"
        return self._response({"reasoning": "MOCK reasoning: not a real judgement.", "winner": winner,
                               "confidence": 2}, user)

    @staticmethod
    def _response(tool_input: dict, user: str):
        digest = hashlib.sha256(user.encode("utf-8")).hexdigest()[:10]
        return SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", name=TOOL_NAME, input=tool_input)],
            usage=SimpleNamespace(input_tokens=max(1, len(user) // 4), output_tokens=100),
            stop_reason="tool_use", _request_id=f"mock_{digest}")


# ---------------------------------------------------------------------------
# Running calls
# ---------------------------------------------------------------------------

def parse_response(resp) -> dict | None:
    """The validated tool input, or None if the response is unusable (no tool call, bad fields, truncated)."""
    if getattr(resp, "stop_reason", None) == "max_tokens":
        return None
    for block in getattr(resp, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == TOOL_NAME:
            data = getattr(block, "input", None)
            if not isinstance(data, dict):
                return None
            reasoning, winner, conf = data.get("reasoning"), data.get("winner"), data.get("confidence")
            if (isinstance(reasoning, str) and reasoning.strip() and winner in ("A", "B", "tie")
                    and isinstance(conf, int) and not isinstance(conf, bool) and conf in (1, 2, 3)):
                return {"reasoning": reasoning.strip(), "winner": winner, "confidence": conf}
            return None
    return None


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status == 429 or (isinstance(status, int) and status >= 500)
    return type(exc).__name__ in ("APIConnectionError", "APITimeoutError", "ConnectionError", "TimeoutError")


class Runner:
    """Runs planned calls against an injected client with a hard request cap and bounded retries."""

    def __init__(self, client, model: str, max_calls: int = MAX_CALLS, send_temperature: bool = True,
                 sleep=time.sleep, secrets: tuple = (), data: dict | None = None):
        self.client, self.model, self.max_calls = client, model, max_calls
        self.sleep, self.secrets, self.data = sleep, tuple(s for s in secrets if s), data
        self.state = {"temperature": send_temperature, "force_tool": True, "thinking": True}
        self.requests_made = 0
        self.adaptations: list[str] = []

    def _redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        return text

    def _system(self) -> str:
        return JUDGE_SYSTEM_PROMPT if self.state["force_tool"] else JUDGE_SYSTEM_PROMPT + AUTO_TOOL_CHOICE_SUFFIX

    def _kwargs(self, user: str) -> dict:
        kwargs = {"model": self.model, "max_tokens": MAX_TOKENS, "system": self._system(), "tools": [JUDGE_TOOL],
                  "messages": [{"role": "user", "content": user}],
                  "tool_choice": {"type": "tool", "name": TOOL_NAME} if self.state["force_tool"] else {"type": "auto"}}
        if self.state["temperature"]:
            kwargs["extra_body"] = {"temperature": 0}      # anthropic 1.x has no temperature= keyword
        if self.state["thinking"]:
            kwargs["thinking"] = {"type": "disabled"}
        return kwargs

    def _adapt(self, error_text: str) -> bool:
        """After an HTTP 400 naming a parameter, switch that parameter off once. True if something changed."""
        text, changed = error_text.lower(), False
        for flag, word in (("temperature", "temperature"), ("force_tool", "tool_choice"), ("thinking", "thinking")):
            if self.state[flag] and word in text:
                self.state[flag] = False
                self.adaptations.append(f"{word} switched off after an HTTP 400")
                changed = True
        return changed

    def _request(self, user: str, record: dict):
        retries = 0
        while True:
            if self.requests_made >= self.max_calls:
                raise CapExceeded(f"MAX_CALLS ({self.max_calls}) reached; stopping before another request")
            self.requests_made += 1
            kwargs = self._kwargs(user)
            record["attempts"] += 1
            record["params_sent"] = {"model": self.model, "max_tokens": MAX_TOKENS,
                                     "tool_choice": kwargs["tool_choice"]["type"],
                                     "temperature_sent": "extra_body" in kwargs,
                                     "thinking": kwargs.get("thinking", "omitted")}
            record["prompt_system"] = kwargs["system"]
            try:
                return self.client.messages.create(**kwargs)
            except CapExceeded:
                raise
            except Exception as exc:     # noqa: BLE001 - classified below, never swallowed silently
                status = getattr(exc, "status_code", None)
                if status == 400 and self._adapt(str(exc)):
                    record["adaptations"] = list(self.adaptations)
                    continue
                if _is_retryable(exc) and retries < MAX_RETRIES:
                    self.sleep(BACKOFF_SECONDS[min(retries, len(BACKOFF_SECONDS) - 1)])
                    retries += 1
                    continue
                raise ApiFailure(exc) from exc

    def judge(self, call: dict, query: dict) -> dict:
        """One planned call -> one raw record (status ok / parse_error / api_error)."""
        user = build_user_message(query, call["list_a"], call["list_b"], self.data)
        record = {**call, "model": self.model, "prompt_system": self._system(), "prompt_user": user,
                  "attempts": 0, "adaptations": [], "response": None, "status": None, "usage": None,
                  "request_id": None, "error": None}
        parse_failures = 0
        while True:
            try:
                resp = self._request(user, record)
            except ApiFailure as failure:
                record["status"] = "api_error"
                record["error"] = self._redact(f"{type(failure.exc).__name__} status={getattr(failure.exc, 'status_code', None)}: "
                                               f"{str(failure.exc)[:200]}")
                return record
            usage = getattr(resp, "usage", None)
            record["usage"] = {"input_tokens": getattr(usage, "input_tokens", None),
                               "output_tokens": getattr(usage, "output_tokens", None)}
            record["request_id"] = getattr(resp, "_request_id", None)
            parsed = parse_response(resp)
            if parsed is not None:
                record["response"], record["status"] = parsed, "ok"
                return record
            parse_failures += 1
            if parse_failures > PARSE_RETRIES:
                record["status"] = "parse_error"
                return record


def run_plan(plan: dict, queries_by_id: dict, runner: Runner, out_dir: Path, mode: str) -> dict:
    """Write plan.json, run every call (appending raw_calls.jsonl line by line), write run_summary.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    check_cap(plan["n_calls"], runner.max_calls)
    plan_doc = {**plan, "mode": mode, "model": runner.model, "max_calls": runner.max_calls,
                "calls": [{k: v for k, v in c.items()} for c in plan["calls"]]}
    (out_dir / "plan.json").write_text(json.dumps(plan_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw_path = out_dir / "raw_calls.jsonl"
    statuses: dict = {}
    tokens = {"input": 0, "output": 0}
    aborted = None
    with open(raw_path, "w", encoding="utf-8", newline="\n") as raw:
        for call in plan["calls"]:
            try:
                record = runner.judge(call, queries_by_id[call["query"]])
            except CapExceeded as exc:
                aborted = str(exc)
                break
            record["mode"] = mode
            raw.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw.flush()
            statuses[record["status"]] = statuses.get(record["status"], 0) + 1
            if record["usage"]:
                tokens["input"] += record["usage"]["input_tokens"] or 0
                tokens["output"] += record["usage"]["output_tokens"] or 0
    summary = {"mode": mode, "model": runner.model, "planned_calls": plan["n_calls"], "judged_calls": sum(statuses.values()),
               "requests_made": runner.requests_made, "status_counts": statuses, "token_totals": tokens,
               "adaptations": runner.adaptations, "aborted": aborted}
    (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def judge_model() -> str:
    return os.environ.get("JUDGE_MODEL", "").strip() or JUDGE_MODEL_DEFAULT


def _print_plan(plan: dict, max_calls: int, estimate: dict) -> None:
    s = summarize_plan(plan, max_calls)
    print("CALL PLAN")
    print(f"  total planned calls            : {s['total_calls']} (MAX_CALLS {s['max_calls']})")
    print(f"  comparison calls               : {s['comparison_calls']}  by candidate weight {s['calls_by_candidate_weight']}")
    print(f"  comparison calls by run        : {s['comparison_calls_by_run']}")
    print(f"  calls by presentation order    : {s['calls_by_order']}")
    print(f"  judged pairs                   : {s['judged_pairs']}  {s['judged_pairs_by_status']}")
    print(f"  negative-control calls         : {s['control_calls']}  (controls skipped as identical: {s['control_skipped']})")
    print(f"  identical pairs skipped (cost 0): {len(s['identical_skipped'])}  {s['identical_skipped']}")
    print("COST ESTIMATE (nothing is spent)")
    print(f"  average input per call         : {estimate['avg_input_chars']} chars = "
          f"{estimate['avg_input_tokens_proxy_low']} tokens (chars/4 proxy) to "
          f"{estimate['avg_input_tokens_proxy_high']} tokens (chars/1.5, Thai-heavy proxy)")
    print(f"  expected output per call       : {estimate['expected_output_tokens_range']} tokens (assumption)")
    print(f"  formula                        : {estimate['formula']}")
    if estimate["cost_low_usd"] is None:
        print("  PRICE_IN / PRICE_OUT           : UNVERIFIED placeholders (None); supply --price-in / --price-out "
              "(USD per million tokens) to get a dollar range")
    else:
        print(f"  prices used (USD/Mtok)         : in {estimate['price_in']} / out {estimate['price_out']} (as supplied)")
        print(f"  cost range                     : ${estimate['cost_low_usd']} to ${estimate['cost_high_usd']}")


def main(argv=None, *, client_factory=None, sleep=time.sleep, top3_fn=top3) -> int:
    parser = argparse.ArgumentParser(description="Pairwise LLM judge for the SEASONING_WEIGHT experiment (group F).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="use the mock client (the default)")
    mode.add_argument("--real", action="store_true", help="make REAL API calls (needs ANTHROPIC_API_KEY)")
    parser.add_argument("--runs", type=int, default=RUNS)
    parser.add_argument("--max-calls", type=int, default=MAX_CALLS)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="print the call plan and cost estimate, call nothing")
    parser.add_argument("--no-temperature", action="store_true", help="do not send temperature at all")
    parser.add_argument("--price-in", type=float, default=PRICE_IN, help="USD per million input tokens (UNVERIFIED unless you know it)")
    parser.add_argument("--price-out", type=float, default=PRICE_OUT, help="USD per million output tokens")
    args = parser.parse_args(argv)
    real = bool(args.real)

    with open(EXTRA_SET_PATH, encoding="utf-8") as f:
        f_queries = [q for q in json.load(f)["queries"] if q["id"].startswith("F")]
    queries_by_id = {q["id"]: q for q in f_queries}
    plan = build_plan(f_queries, top3_fn=top3_fn, runs=args.runs)
    data = load_data()
    estimate = estimate_cost(plan, queries_by_id, data, args.price_in, args.price_out)
    print("MODE: REAL (API calls will be made)" if real and not args.dry_run else
          "MODE: DRY RUN (no calls)" if args.dry_run else "MODE: MOCK (no network, no API key, MOCK results)")
    print(f"judge model: {judge_model()}  (UNVERIFIED id; set JUDGE_MODEL to override)")
    _print_plan(plan, args.max_calls, estimate)
    try:
        check_cap(plan["n_calls"], args.max_calls)
    except CapExceeded as exc:
        print(f"ABORT: {exc}")
        return 2
    if args.dry_run:
        return 0

    secrets: tuple = ()
    if real:
        out_dir = args.out_dir or DEFAULT_REAL_OUT_DIR
        if out_dir.exists() and any(out_dir.iterdir()):
            print(f"ABORT: {out_dir} is not empty; a real run never overwrites or mixes with existing results")
            return 2
        try:
            key = read_api_key()
        except MissingKey as exc:
            print(f"ABORT: {exc}")
            return 2
        secrets = (key,)
        client = (client_factory or make_real_client)(key)
    else:
        out_dir = args.out_dir or Path(tempfile.mkdtemp(prefix="judge_f_mock_"))
        client = MockClient()
    runner = Runner(client, judge_model(), max_calls=args.max_calls, send_temperature=not args.no_temperature,
                    sleep=sleep, secrets=secrets, data=data)
    summary = run_plan(plan, queries_by_id, runner, out_dir, "REAL" if real else "MOCK")
    print(f"done: {summary['judged_calls']} calls judged, {summary['requests_made']} requests, "
          f"status counts {summary['status_counts']}, adaptations {summary['adaptations']}, output in {out_dir}")
    if summary["aborted"]:
        print(f"ABORTED: {summary['aborted']}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
