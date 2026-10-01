"""
tests/test_web_api.py
=====================
Behaviour tests for the FastAPI web backend (api/app.py), driven through
FastAPI's TestClient. The YOLO detector is stubbed: the *.pt weights are
gitignored, and these tests are about the API contract, not the model.

Run with:
    pytest tests/test_web_api.py -v
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

try:  # anthropic 1.x is built on httpx2
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx

from fastapi.testclient import TestClient

from api import app as app_module
from api import state, web_config
from nlp import extract_bert
from nlp.extract import extract

PNG = ("photo.png", b"\x89PNG-not-really", "image/png")


@pytest.fixture
def stub_detections():
    """Mutable list the fake detector returns; tests overwrite its contents."""
    return []


@pytest.fixture
def client(monkeypatch, stub_detections):
    monkeypatch.setattr(web_config, "CONFIDENCE_THRESHOLD", 0.5)
    monkeypatch.setattr(app_module, "_load_detector", lambda: (lambda path: list(stub_detections)))
    state.store.clear()
    app_module.limiter.reset()
    with TestClient(app_module.app) as c:
        yield c
    state.store.clear()
    app_module.limiter.reset()


def _upload(client, files=None, **data):
    files = files or [PNG]
    return client.post("/detect", files=[("images", f) for f in files], data=data)


def _start_session_with_text(client, text="chicken and egg"):
    """Return a session_id in awaiting_confirm with `text` extracted."""
    r = client.post("/extract", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_reports_the_detector_and_is_never_rate_limited(client):
    codes = [client.get("/health").status_code for _ in range(30)]
    assert codes == [200] * 30
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["detector"] == "loaded"
    assert body["bert"] in ("loaded", "pending", "unavailable")


def test_health_says_unavailable_without_weights(monkeypatch):
    monkeypatch.setattr(app_module, "_load_detector", lambda: None)
    with TestClient(app_module.app) as c:
        body = c.get("/health").json()
        assert body["status"] == "ok" and body["detector"] == "unavailable"


# ---------------------------------------------------------------------------
# /detect
# ---------------------------------------------------------------------------

def test_detect_filters_by_threshold_and_keeps_max_confidence(client, stub_detections):
    stub_detections[:] = [
        {"ingredient": "egg", "confidence": 0.92},
        {"ingredient": "egg", "confidence": 0.60},
        {"ingredient": "onion", "confidence": 0.31},  # below 0.5 -> dropped
    ]
    r = _upload(client, [PNG, PNG])
    assert r.status_code == 200
    body = r.json()
    assert [d["ingredient"] for d in body["detected"]] == ["egg"]
    assert body["detected"][0]["confidence"] == 0.92
    assert body["ingredients"] == ["egg"]
    assert body["images_processed"] == 2
    assert body["stage"] == "awaiting_confirm"
    assert len(body["session_id"]) == 32


def test_detect_unions_across_calls_in_one_session(client, stub_detections):
    stub_detections[:] = [{"ingredient": "egg", "confidence": 0.9}]
    sid = _upload(client).json()["session_id"]
    stub_detections[:] = [{"ingredient": "tomato", "confidence": 0.8}]
    body = _upload(client, session_id=sid).json()
    assert body["session_id"] == sid
    assert body["ingredients"] == ["egg", "tomato"]


def test_detect_skips_unsupported_files_but_processes_the_rest(client, stub_detections):
    stub_detections[:] = [{"ingredient": "egg", "confidence": 0.9}]
    r = _upload(client, [PNG, ("a.gif", b"GIF89a", "image/gif")])
    assert r.status_code == 200
    body = r.json()
    assert body["images_processed"] == 1
    assert body["images_skipped"] == [{"filename": "a.gif", "reason": "unsupported type"}]


def test_detect_with_no_usable_image_is_422(client):
    r = _upload(client, [("a.gif", b"GIF89a", "image/gif")])
    assert r.status_code == 422


def test_detect_rejects_too_many_images(client):
    r = _upload(client, [PNG] * (web_config.MAX_IMAGES_PER_REQUEST + 1))
    assert r.status_code == 422


def test_detect_reports_oversize_file(client, monkeypatch, stub_detections):
    monkeypatch.setattr(web_config, "MAX_IMAGE_BYTES", 4)
    stub_detections[:] = [{"ingredient": "egg", "confidence": 0.9}]
    r = _upload(client, [("big.png", b"12345678", "image/png")])
    assert r.status_code == 422
    assert "file too large" in r.text


def test_detect_returns_503_when_no_detector(monkeypatch):
    monkeypatch.setattr(app_module, "_load_detector", lambda: None)
    state.store.clear()
    app_module.limiter.reset()
    with TestClient(app_module.app) as c:
        assert _upload(c).status_code == 503
        # the other endpoints keep working without weights
        assert c.post("/extract", json={"text": "chicken"}).status_code == 200


def test_detect_survives_a_detector_crash_on_one_image(client, monkeypatch):
    def boom(path):
        raise RuntimeError("corrupt image")

    monkeypatch.setattr(app_module.app.state, "detector", boom)
    r = _upload(client)
    assert r.status_code == 422
    assert "unreadable image" in r.text


# ---------------------------------------------------------------------------
# /extract
# ---------------------------------------------------------------------------

def test_extract_returns_three_separate_lists(client):
    # Thai by design: the system's language is Thai (ไม่เอา = "don't want").
    r = client.post("/extract", json={"text": "มีไก่กับไข่ ไม่เอาหมู อยากกินคลีน"})
    assert r.status_code == 200
    body = r.json()
    assert body["include"] == ["chicken", "egg"]
    assert body["exclude"] == ["pork"]
    assert body["health_tags"] == ["clean"]
    assert body["ingredients"] == ["chicken", "egg"]
    assert body["stage"] == "awaiting_confirm"


def test_extract_merges_with_detected_ingredients(client, stub_detections):
    stub_detections[:] = [{"ingredient": "tomato", "confidence": 0.9}]
    sid = _upload(client).json()["session_id"]
    body = client.post("/extract", json={"text": "chicken", "session_id": sid}).json()
    assert body["ingredients"] == ["tomato", "chicken"]


def test_a_later_no_x_removes_an_earlier_x(client):
    sid = _start_session_with_text(client, "chicken and egg")
    body = client.post("/extract", json={"text": "ไม่เอาไข่", "session_id": sid}).json()
    assert body["ingredients"] == ["chicken"]
    assert body["exclude"] == ["egg"]


def test_extract_rejects_empty_text(client):
    assert client.post("/extract", json={"text": ""}).status_code == 422


def test_a_second_extract_with_a_new_health_tag_replaces_not_accumulates(client):
    sid = _start_session_with_text(client, "อยากกินคีโต")
    assert client.post("/extract", json={"text": "มีไก่", "session_id": sid}).json()["health_tags"] == []
    body = client.post("/extract", json={"text": "เปลี่ยนเป็นวีแกน", "session_id": sid}).json()
    assert body["health_tags"] == ["vegan"]
    assert state.store.get(sid).health_tags == ["vegan"], "session preference must not accumulate ['keto', 'vegan']"


# ---------------------------------------------------------------------------
# /confirm  (keyword stub -- see api/intent.py)
# ---------------------------------------------------------------------------

def _confirm(client, sid, reply):
    return client.post("/confirm", json={"session_id": sid, "reply": reply})


def test_confirm_yes_moves_to_confirmed(client):
    sid = _start_session_with_text(client)
    body = _confirm(client, sid, "yes that's right").json()
    assert body["intent"] == "confirm"
    assert body["stage"] == "confirmed"
    assert body["corrections"] == {"add": [], "remove": []}


def test_confirm_with_correction_applies_it_and_asks_again(client):
    sid = _start_session_with_text(client)
    body = _confirm(client, sid, "yeah that's right, but also add garlic").json()
    assert body["intent"] == "confirm+correction"
    assert body["corrections"]["add"] == ["garlic"]
    assert "garlic" in body["ingredients"]
    assert body["stage"] == "awaiting_confirm"  # NOT confirmed: the new list needs its own yes


def test_confirm_reject_moves_to_awaiting_correction(client):
    sid = _start_session_with_text(client)
    body = _confirm(client, sid, "no that's wrong").json()
    assert body["intent"] == "reject"
    assert body["stage"] == "awaiting_correction"


def test_bare_no_before_an_ingredient_is_not_a_reject(client):
    sid = _start_session_with_text(client)
    body = _confirm(client, sid, "no pork").json()
    assert body["intent"] == "unclear"  # "no <ingredient>" is not a rejection; nothing guessed


def test_unclear_reply_changes_nothing(client):
    sid = _start_session_with_text(client)
    body = _confirm(client, sid, "hmm what about dessert").json()
    assert body["intent"] == "unclear"
    assert body["stage"] == "awaiting_confirm"


def test_confirm_before_anything_was_sent_is_409(client):
    sid = client.post("/seasoning", json={"seasonings": []}).json()["session_id"]
    assert _confirm(client, sid, "yes").status_code == 409


# ---------------------------------------------------------------------------
# /correct
# ---------------------------------------------------------------------------

def test_correct_removes_checked_items_and_adds_typed_ones(client):
    sid = _start_session_with_text(client, "chicken and egg")
    body = client.post(
        "/correct", json={"session_id": sid, "exclude": ["egg"], "add_text": "garlic"}
    ).json()
    assert body["removed"] == ["egg"]
    assert body["added"] == ["garlic"]
    assert body["ingredients"] == ["chicken", "garlic"]
    assert body["stage"] == "awaiting_confirm"


def test_checklist_removal_does_not_ban_dishes_but_typed_no_does(client):
    sid = _start_session_with_text(client, "chicken and egg")
    client.post("/correct", json={"session_id": sid, "exclude": ["egg"]})
    assert state.store.get(sid).exclude == []           # wrong detection, not a ban
    client.post("/correct", json={"session_id": sid, "add_text": "ไม่เอาไก่"})
    assert state.store.get(sid).exclude == ["chicken"]   # typed "no X" is a ban


def test_correct_rejects_keys_not_in_the_list(client):
    sid = _start_session_with_text(client, "chicken")
    r = client.post("/correct", json={"session_id": sid, "exclude": ["shrimp"]})
    assert r.status_code == 422
    assert "shrimp" in r.text


def test_correct_with_nothing_to_do_is_422(client):
    sid = _start_session_with_text(client)
    assert client.post("/correct", json={"session_id": sid}).status_code == 422


def test_correct_before_chat_started_is_409(client):
    sid = client.post("/seasoning", json={"seasonings": []}).json()["session_id"]
    assert client.post("/correct", json={"session_id": sid, "add_text": "egg"}).status_code == 409


# ---------------------------------------------------------------------------
# /seasoning
# ---------------------------------------------------------------------------

def test_seasoning_creates_a_session_when_none_is_given(client):
    r = client.post("/seasoning", json={"seasonings": ["fish_sauce", "sugar", "sugar"]})
    assert r.status_code == 200
    body = r.json()
    assert body["seasonings"] == ["fish_sauce", "sugar"]
    assert len(body["session_id"]) == 32


def test_seasoning_rejects_non_seasoning_and_unknown_keys(client):
    r = client.post("/seasoning", json={"seasonings": ["fish_sauce", "chicken", "nope"]})
    assert r.status_code == 422
    assert "chicken" in r.text and "nope" in r.text


def test_seasoning_can_be_replaced_before_chat_starts(client):
    sid = client.post("/seasoning", json={"seasonings": ["sugar"]}).json()["session_id"]
    body = client.post("/seasoning", json={"session_id": sid, "seasonings": ["fish_sauce"]}).json()
    assert body["seasonings"] == ["fish_sauce"]


def test_seasoning_is_locked_once_the_chat_starts(client):
    sid = _start_session_with_text(client)
    r = client.post("/seasoning", json={"session_id": sid, "seasonings": ["sugar"]})
    assert r.status_code == 409


def test_seasoning_locked_flag_reflects_the_real_state_without_a_409(client):
    sid = client.post("/seasoning", json={"seasonings": ["sugar"]}).json()["session_id"]

    before = client.post("/seasoning", json={"session_id": sid})  # `seasonings` omitted = read-only
    assert before.status_code == 200
    assert before.json() == {"session_id": sid, "seasonings": ["sugar"], "locked": False}

    client.post("/extract", json={"text": "chicken", "session_id": sid})  # chat starts

    after = client.post("/seasoning", json={"session_id": sid})
    assert after.status_code == 200
    assert after.json() == {"session_id": sid, "seasonings": ["sugar"], "locked": True}
    # a WRITE after the lock is still refused, and the list is unchanged
    assert client.post("/seasoning", json={"session_id": sid, "seasonings": []}).status_code == 409
    assert state.store.get(sid).seasonings == ["sugar"]


def test_seasoning_empty_list_clears_but_omitted_does_not(client):
    sid = client.post("/seasoning", json={"seasonings": ["sugar"]}).json()["session_id"]
    assert client.post("/seasoning", json={"session_id": sid}).json()["seasonings"] == ["sugar"]
    assert client.post("/seasoning", json={"session_id": sid, "seasonings": []}).json()["seasonings"] == []


# ---------------------------------------------------------------------------
# /recommend
# ---------------------------------------------------------------------------

def test_recommend_before_confirm_is_409(client):
    sid = _start_session_with_text(client)
    assert client.post("/recommend", json={"session_id": sid}).status_code == 409


def test_recommend_uses_session_list_tags_excludes_and_seasonings(client):
    sid = client.post("/seasoning", json={"seasonings": ["fish_sauce"]}).json()["session_id"]
    client.post(
        "/extract", json={"text": "มีไก่ กระเทียม พริก ไม่เอาหมู อยากกินคลีน", "session_id": sid}
    )
    _confirm(client, sid, "yes")
    r = client.post("/recommend", json={"session_id": sid, "top_n": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["used"]["seasonings"] == ["fish_sauce"]
    assert body["used"]["health_tags"] == ["clean"]
    assert body["used"]["exclude"] == ["pork"]
    assert body["count"] == len(body["recipes"]) <= 5 and body["count"] > 0
    for dish in body["recipes"]:
        assert "clean" in dish["health_tags"]
        assert 0.0 <= dish["score"] <= 1.0
        assert "seasonings_matched" in dish
        # display data the web recipe cards render
        assert isinstance(dish["main_ingredients"], list) and dish["main_ingredients"]
        assert isinstance(dish["seasonings"], list)
        assert dish["recipe_source_url"].startswith("http")
        assert dish["cook_time_min"] > 0


def test_recommend_rejects_out_of_range_top_n(client):
    sid = _start_session_with_text(client)
    _confirm(client, sid, "yes")
    assert client.post("/recommend", json={"session_id": sid, "top_n": 0}).status_code == 422
    assert client.post("/recommend", json={"session_id": sid, "top_n": 11}).status_code == 422


def test_recommend_with_no_match_is_an_empty_200(client):
    sid = client.post("/extract", json={"text": "hello there"}).json()["session_id"]
    _confirm(client, sid, "yes")
    body = client.post("/recommend", json={"session_id": sid}).json()
    assert body["recipes"] == [] and body["count"] == 0


# ---------------------------------------------------------------------------
# A completed confirm/recommend cycle starts fresh on the next input,
# instead of merging onto the already-recommended list
# ---------------------------------------------------------------------------

def test_extract_after_a_completed_cycle_replaces_not_merges(client):
    sid = _start_session_with_text(client, "chicken and egg")
    _confirm(client, sid, "yes")
    client.post("/recommend", json={"session_id": sid})  # completes the cycle; stage stays "confirmed"

    body = client.post("/extract", json={"text": "fish and crab", "session_id": sid}).json()
    assert body["ingredients"] == ["fish", "crab"]
    assert "chicken" not in body["ingredients"] and "egg" not in body["ingredients"]
    assert body["stage"] == "awaiting_confirm"


def test_extract_bert_after_a_completed_cycle_replaces_not_merges(monkeypatch, client):
    # app.py imports extract_bert by name (`from nlp.extract_bert import extract_bert`),
    # so the patch target is app_module's own binding, not the source module's.
    monkeypatch.setattr(
        app_module, "extract_bert", lambda text: {"ingredients": ["chicken"], "health_tags": [], "excluded": []}
    )
    sid = client.post("/extract_bert", json={"text": "x"}).json()["session_id"]
    _confirm(client, sid, "yes")
    client.post("/recommend", json={"session_id": sid})

    monkeypatch.setattr(
        app_module, "extract_bert", lambda text: {"ingredients": ["fish"], "health_tags": [], "excluded": []}
    )
    body = client.post("/extract_bert", json={"text": "y", "session_id": sid}).json()
    assert body["ingredients"] == ["fish"]


def test_detect_after_a_completed_cycle_replaces_not_merges(client, stub_detections):
    stub_detections[:] = [{"ingredient": "chicken", "confidence": 0.9}]
    sid = _upload(client).json()["session_id"]
    _confirm(client, sid, "yes")
    client.post("/recommend", json={"session_id": sid})

    stub_detections[:] = [{"ingredient": "fish", "confidence": 0.9}]
    body = _upload(client, session_id=sid).json()
    assert body["ingredients"] == ["fish"]
    assert "chicken" not in body["ingredients"]


def test_extract_before_confirm_still_merges_as_before(client):
    """The reject/correct loop's legitimate accumulation must be unaffected."""
    sid = _start_session_with_text(client, "chicken")
    body = client.post("/extract", json={"text": "egg", "session_id": sid}).json()
    assert body["ingredients"] == ["chicken", "egg"]


def test_seasonings_survive_a_completed_cycle_reset(client):
    sid = client.post("/seasoning", json={"seasonings": ["fish_sauce"]}).json()["session_id"]
    client.post("/extract", json={"text": "chicken", "session_id": sid})
    _confirm(client, sid, "yes")
    client.post("/recommend", json={"session_id": sid})

    client.post("/extract", json={"text": "fish", "session_id": sid})
    assert state.store.get(sid).seasonings == ["fish_sauce"]


# ---------------------------------------------------------------------------
# Whole flow, sessions, rate limiting, secrets
# ---------------------------------------------------------------------------

def test_full_flow_with_a_reject_loop(client, stub_detections):
    stub_detections[:] = [
        {"ingredient": "chicken", "confidence": 0.9},
        {"ingredient": "onion", "confidence": 0.8},  # a wrong detection
    ]
    sid = client.post("/seasoning", json={"seasonings": ["fish_sauce"]}).json()["session_id"]
    _upload(client, session_id=sid)
    client.post("/extract", json={"text": "garlic, want it clean", "session_id": sid})

    assert _confirm(client, sid, "no that's wrong").json()["stage"] == "awaiting_correction"
    fixed = client.post(
        "/correct", json={"session_id": sid, "exclude": ["onion"], "add_text": "chili"}
    ).json()
    assert fixed["ingredients"] == ["chicken", "garlic", "chili"]
    assert _confirm(client, sid, "yes").json()["stage"] == "confirmed"

    body = client.post("/recommend", json={"session_id": sid}).json()
    assert body["used"]["ingredients"] == ["chicken", "garlic", "chili"]
    assert body["count"] > 0


def test_unknown_session_is_404_and_malformed_id_is_422(client):
    assert _confirm(client, "0" * 32, "yes").status_code == 404
    assert client.post("/recommend", json={"session_id": "0" * 32}).status_code == 404
    assert client.post("/extract", json={"text": "egg", "session_id": "nope"}).status_code == 422


def test_expired_sessions_are_swept(client):
    sid = _start_session_with_text(client)
    state.store.get(sid).last_seen -= web_config.SESSION_TTL_SECONDS + 1
    assert client.post("/recommend", json={"session_id": sid}).status_code == 404


def test_detect_is_limited_to_5_per_minute(client, stub_detections):
    stub_detections[:] = [{"ingredient": "egg", "confidence": 0.9}]
    codes = [_upload(client).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_other_endpoints_are_limited_to_10_per_minute(client):
    codes = [client.post("/extract", json={"text": "egg"}).status_code for _ in range(11)]
    assert codes == [200] * 10 + [429]


def test_rate_limit_keys_on_forwarded_for_only_when_trusted(client, monkeypatch, stub_detections):
    stub_detections[:] = [{"ingredient": "egg", "confidence": 0.9}]
    monkeypatch.setattr(web_config, "TRUST_FORWARDED_FOR", True)
    for _ in range(5):
        client.post("/detect", files=[("images", PNG)], headers={"x-forwarded-for": "1.1.1.1"})
    limited = client.post("/detect", files=[("images", PNG)], headers={"x-forwarded-for": "1.1.1.1"})
    other_ip = client.post("/detect", files=[("images", PNG)], headers={"x-forwarded-for": "2.2.2.2"})
    assert limited.status_code == 429
    assert other_ip.status_code == 200


def test_secret_helpers_never_expose_the_full_key(monkeypatch):
    assert web_config.mask_secret("") == "<unset>"
    masked = web_config.mask_secret("sk-ant-api03-SECRETSECRET")
    assert masked == "sk-a…" and "SECRET" not in masked

    monkeypatch.setattr(web_config, "ANTHROPIC_API_KEY", "your_anthropic_api_key_here")
    assert web_config.anthropic_key_configured() is False
    monkeypatch.setattr(web_config, "ANTHROPIC_API_KEY", "")
    assert web_config.anthropic_key_configured() is False
    monkeypatch.setattr(web_config, "ANTHROPIC_API_KEY", "sk-ant-real")
    assert web_config.anthropic_key_configured() is True


# ---------------------------------------------------------------------------
# /extract_bert: an LLM-fallback failure degrades to the keyword extract()
# (was: HTTP 500). BERT itself is stubbed to "found nothing", which is the
# input that triggers the Sonnet fallback.
# ---------------------------------------------------------------------------

FAKE_KEY = "sk-ant-api03-FAKEKEYFORTESTS-do-not-leak"
KEYWORD_TEXT = "มีไก่กับไข่"
_REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, status):
    return cls("boom", response=httpx.Response(status, request=_REQ, headers={"request-id": "req_abc"}), body=None)


class _FakeLLMClient:
    """Stands in for anthropic.Anthropic: records calls, returns text or raises."""

    def __init__(self, result):
        self.result = result
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return SimpleNamespace(content=[SimpleNamespace(text=self.result)])


@pytest.fixture
def bert_finds_nothing(monkeypatch):
    """BERT 'loaded' and finding no entities, so extract_bert() goes to the LLM fallback."""
    config = {"LABEL_LIST": [], "id2label": {}, "confidence_threshold": 0.8}
    monkeypatch.setattr(extract_bert, "_get_model_and_config", lambda: (None, None, config))
    monkeypatch.setattr(extract_bert, "predict_entities_bert_with_confidence", lambda text: [])


@pytest.fixture
def llm_client(monkeypatch):
    """Enable the LLM path (fake key) and return a function that installs a fake client."""
    monkeypatch.setattr(web_config, "ANTHROPIC_API_KEY", FAKE_KEY)

    def install(result):
        fake = _FakeLLMClient(result)
        monkeypatch.setattr(extract_bert, "_get_client", lambda: fake)
        return fake

    return install


@pytest.fixture
def lenient_client(monkeypatch):
    """Like `client`, but a server error comes back as an HTTP 500 instead of raising in the test."""
    monkeypatch.setattr(app_module, "_load_detector", lambda: None)
    state.store.clear()
    app_module.limiter.reset()
    with TestClient(app_module.app, raise_server_exceptions=False) as c:
        yield c
    state.store.clear()
    app_module.limiter.reset()


LLM_FAILURES = {
    "timeout": anthropic.APITimeoutError(request=_REQ),
    "connection": anthropic.APIConnectionError(request=_REQ),
    "rate_limit_429": _status_error(anthropic.RateLimitError, 429),
    "auth_401": _status_error(anthropic.AuthenticationError, 401),
    "server_500": _status_error(anthropic.InternalServerError, 500),
    # Item 2: a model id the account does not have / the API rejects
    "model_not_found_404": _status_error(anthropic.NotFoundError, 404),
    "model_rejected_400": _status_error(anthropic.BadRequestError, 400),
    "unexpected": RuntimeError("something else entirely"),
}


@pytest.mark.parametrize("failure", list(LLM_FAILURES), ids=list(LLM_FAILURES))
def test_extract_bert_llm_failure_falls_back_to_keyword_extract(
    failure, lenient_client, bert_finds_nothing, llm_client, capsys
):
    llm_client(LLM_FAILURES[failure])
    r = lenient_client.post("/extract_bert", json={"text": KEYWORD_TEXT})
    assert r.status_code == 200, r.text
    body = r.json()
    keyword = extract(KEYWORD_TEXT)
    assert body["include"] == keyword["ingredients"] and body["include"]
    assert body["exclude"] == keyword["excluded"]
    assert body["health_tags"] == keyword["health_tags"]
    assert body["stage"] == "awaiting_confirm"
    out = capsys.readouterr().out
    assert out.count("[extract] LLM fallback failed") == 1  # exactly one line per failure
    assert FAKE_KEY not in out and KEYWORD_TEXT not in out  # never the key or the user's text


@pytest.mark.parametrize("bad", ["this is not json", '{"value": "ไก่"}', '["ไก่"]', ""])
def test_extract_bert_unusable_llm_output_falls_back_to_keyword_extract(
    bad, lenient_client, bert_finds_nothing, llm_client
):
    llm_client(bad)
    r = lenient_client.post("/extract_bert", json={"text": KEYWORD_TEXT})
    assert r.status_code == 200, r.text
    assert r.json()["include"] == extract(KEYWORD_TEXT)["ingredients"]


def test_extract_bert_without_an_api_key_skips_the_llm_and_uses_keyword(
    monkeypatch, lenient_client, bert_finds_nothing
):
    def _must_not_build_a_client():
        raise AssertionError("no key configured: the LLM client must not even be built")

    monkeypatch.setattr(extract_bert, "_get_client", _must_not_build_a_client)
    r = lenient_client.post("/extract_bert", json={"text": KEYWORD_TEXT})
    assert r.status_code == 200, r.text
    assert r.json()["include"] == extract(KEYWORD_TEXT)["ingredients"]


def test_extract_bert_a_working_llm_is_still_used(lenient_client, bert_finds_nothing, llm_client):
    fake = llm_client('[{"value": "ไข่", "type": "ING"}]')
    r = lenient_client.post("/extract_bert", json={"text": "อยากได้ไข่"})
    assert r.status_code == 200, r.text
    assert r.json()["include"] == ["egg"]
    assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# Item 2: the extraction model id is overridable; a rejected id never 500s
# (the 404/400 cases are in LLM_FAILURES above)
# ---------------------------------------------------------------------------

def _model_id_in_a_fresh_process(env_value):
    import os
    import subprocess

    env = {k: v for k, v in os.environ.items() if k != "EXTRACTION_LLM_MODEL"}
    if env_value is not None:
        env["EXTRACTION_LLM_MODEL"] = env_value
    out = subprocess.run(
        [sys.executable, "-c", "from api import web_config; print(web_config.EXTRACTION_LLM_MODEL)"],
        cwd=Path(__file__).parent.parent, env=env, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_extraction_model_id_defaults_and_is_overridable_by_env():
    assert _model_id_in_a_fresh_process(None) == "claude-sonnet-5"        # default unchanged
    assert _model_id_in_a_fresh_process("") == "claude-sonnet-5"          # blank = unset
    assert _model_id_in_a_fresh_process("my-account-model") == "my-account-model"


# ---------------------------------------------------------------------------
# Item 3: BERT model absent / unloadable -> keyword extract(), one warning, /health says so
# ---------------------------------------------------------------------------

@pytest.fixture
def bert_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(extract_bert, "_model", None)
    monkeypatch.setattr(extract_bert, "_load_failure", None)
    monkeypatch.setattr(extract_bert, "_warned", set())
    monkeypatch.setattr(extract_bert, "_model_path", lambda: tmp_path / "no_such_model_folder")


def test_missing_bert_model_falls_back_to_keyword_and_warns_once(lenient_client, bert_absent, capsys):
    for _ in range(3):
        r = lenient_client.post("/extract_bert", json={"text": KEYWORD_TEXT})
        assert r.status_code == 200, r.text            # was 503
        body = r.json()
        assert body["include"] == extract(KEYWORD_TEXT)["ingredients"] and body["include"]
        assert body["unknown"] == []
    out = capsys.readouterr().out
    assert out.count("[extract] BERT model unavailable") == 1     # once per process, not per request


def test_health_reports_bert_unavailable_when_the_model_is_missing(lenient_client, bert_absent):
    body = lenient_client.get("/health").json()
    assert body["bert"] == "unavailable"
    assert body["status"] == "ok"


def test_a_model_that_fails_to_load_is_tried_once_then_keyword(
    monkeypatch, lenient_client, bert_absent, tmp_path, capsys
):
    """Present but unloadable (corrupt weights, torch missing): not retried, under the model lock, per request."""
    attempts = []

    def _boom(path):
        attempts.append(path)
        raise RuntimeError("corrupt weights")

    fake_transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=_boom),
        AutoModelForTokenClassification=SimpleNamespace(from_pretrained=_boom),
    )
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setattr(extract_bert, "_model_path", lambda: tmp_path)
    monkeypatch.setattr(extract_bert, "_load_label_config", lambda path: {})

    for _ in range(3):
        r = lenient_client.post("/extract_bert", json={"text": KEYWORD_TEXT})
        assert r.status_code == 200, r.text
        assert r.json()["include"] == extract(KEYWORD_TEXT)["ingredients"]
    assert len(attempts) == 1
    assert capsys.readouterr().out.count("[extract] BERT model unavailable") == 1
    assert lenient_client.get("/health").json()["bert"] == "unavailable"


# ---------------------------------------------------------------------------
# Item 4: `unknown` in ExtractResponse
# ---------------------------------------------------------------------------

def test_extract_bert_reports_unknown_ingredient_words(monkeypatch, client):
    config = {"LABEL_LIST": [], "id2label": {}, "confidence_threshold": 0.8}
    monkeypatch.setattr(extract_bert, "_get_model_and_config", lambda: (None, None, config))
    monkeypatch.setattr(
        extract_bert,
        "predict_entities_bert_with_confidence",
        lambda t: [
            {"type": "ING", "start": 2, "end": 8, "value": "มังคุด", "confidence": 0.99},
            {"type": "ING", "start": 12, "end": 15, "value": "ไก่", "confidence": 0.99},
        ],
    )
    r = client.post("/extract_bert", json={"text": "มีมังคุดกับไก่"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unknown"] == ["มังคุด"]
    assert body["include"] == ["chicken"] and body["ingredients"] == ["chicken"]
    assert body["stage"] == "awaiting_confirm"       # the confirm flow is unchanged


def test_extract_keyword_path_leaves_unknown_empty(client):
    body = client.post("/extract", json={"text": "มีมังคุดกับไก่"}).json()
    assert body["unknown"] == []
    assert body["include"] == ["chicken"]


def test_unknown_defaults_to_empty_when_the_extractor_does_not_supply_it(monkeypatch, client):
    """Old-shaped extractor results (three keys) still work: the field is optional."""
    monkeypatch.setattr(
        app_module, "extract_bert", lambda text: {"ingredients": ["egg"], "health_tags": [], "excluded": []}
    )
    body = client.post("/extract_bert", json={"text": "x"}).json()
    assert body["unknown"] == [] and body["include"] == ["egg"]


# ---------------------------------------------------------------------------
# Category picker on POST /recommend ("all" | "savory" | "dessert"; omitted = "all")
# ---------------------------------------------------------------------------

def _confirmed_session(client, text):
    """A session whose list came from `text` and is confirmed, ready for /recommend."""
    sid = client.post("/extract", json={"text": text}).json()["session_id"]
    assert _confirm(client, sid, "yes").json()["stage"] == "confirmed"
    return sid


def _recommend(client, sid, **extra):
    return client.post("/recommend", json={"session_id": sid, **extra})


def _categories_in(body):
    from recommender.recommend import load_recipes

    by_id = {recipe["id"]: recipe["category"] for recipe in load_recipes()}
    return {by_id[dish["id"]] for dish in body["recipes"]}


@pytest.mark.parametrize("category", ["all", "savory", "dessert"])
def test_recommend_accepts_each_category_and_echoes_it(client, category):
    sid = _confirmed_session(client, "egg")
    r = _recommend(client, sid, category=category)
    assert r.status_code == 200, r.text
    assert r.json()["used"]["category"] == category


@pytest.mark.parametrize("bad", ["snack", "drink", "condiment", "SAVORY", "", None, 3, ["savory"]])
def test_recommend_rejects_any_other_category_value(client, bad):
    sid = _confirmed_session(client, "egg")
    assert _recommend(client, sid, category=bad).status_code == 422


def test_a_missing_category_means_all(client):
    sid = _confirmed_session(client, "egg")
    plain = _recommend(client, sid, top_n=10).json()
    explicit = _recommend(client, sid, top_n=10, category="all").json()
    assert plain["used"]["category"] == "all"
    assert [d["id"] for d in plain["recipes"]] == [d["id"] for d in explicit["recipes"]]
    assert plain["empty_for_category"] is False


def test_recommend_filters_by_the_chosen_category(client):
    sid = _confirmed_session(client, "banana")
    allowed = {"savory": {"savory"}, "dessert": {"dessert"}}
    for category in ("savory", "dessert"):
        body = _recommend(client, sid, top_n=10, category=category).json()
        assert _categories_in(body) <= allowed[category]
    assert _categories_in(_recommend(client, sid, top_n=10, category="dessert").json()) == {"dessert"}
    assert "condiment" not in _categories_in(_recommend(client, sid, top_n=10, category="all").json())


def test_nothing_in_the_chosen_category_sets_empty_for_category(client):
    # rambutan appears only in desserts; squid only in savory dishes
    rambutan = _confirmed_session(client, "rambutan")
    body = _recommend(client, rambutan, category="savory").json()
    assert body["recipes"] == [] and body["count"] == 0 and body["empty_for_category"] is True
    body = _recommend(client, rambutan, category="dessert").json()
    assert body["count"] > 0 and body["empty_for_category"] is False
    assert _recommend(client, rambutan, category="all").json()["count"] > 0

    squid = _confirmed_session(client, "squid")
    body = _recommend(client, squid, category="dessert").json()
    assert body["count"] == 0 and body["empty_for_category"] is True
    assert _recommend(client, squid, category="savory").json()["count"] > 0


def test_empty_in_every_mode_is_not_blamed_on_the_category(client):
    sid = _confirmed_session(client, "fish sauce")          # a seasoning-only list matches nothing anywhere
    for category in ("all", "savory", "dessert"):
        body = _recommend(client, sid, category=category).json()
        assert body["count"] == 0
        assert body["empty_for_category"] is False, category


def test_the_category_is_kept_in_the_session_and_reset_when_a_new_round_starts(client):
    sid = _confirmed_session(client, "egg")
    assert state.store.get(sid).category == "all"
    _recommend(client, sid, category="dessert")
    assert state.store.get(sid).category == "dessert"

    # the cycle is finished (stage "confirmed"), so new input starts a new round and clears the choice
    assert client.post("/extract", json={"text": "pork", "session_id": sid}).status_code == 200
    assert state.store.get(sid).category == "all"
    assert state.store.get(sid).stage == "awaiting_confirm"


def test_a_choice_does_not_leak_into_the_next_recommend_call(client):
    sid = _confirmed_session(client, "egg")
    _recommend(client, sid, category="dessert")
    body = _recommend(client, sid).json()                   # omitted -> "all", not the previous "dessert"
    assert body["used"]["category"] == "all"


def test_the_schema_literal_matches_the_recommenders_choices():
    from typing import get_args

    from api import schemas
    from recommender.recommend import CATEGORY_CHOICES

    assert get_args(schemas.Category) == CATEGORY_CHOICES == ("all", "savory", "dessert")
