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

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from api import app as app_module
from api import state, web_config

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
    assert client.get("/health").json() == {"status": "ok", "detector": "loaded"}


def test_health_says_unavailable_without_weights(monkeypatch):
    monkeypatch.setattr(app_module, "_load_detector", lambda: None)
    with TestClient(app_module.app) as c:
        assert c.get("/health").json() == {"status": "ok", "detector": "unavailable"}


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
