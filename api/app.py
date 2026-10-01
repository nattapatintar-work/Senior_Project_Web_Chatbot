"""
api/app.py
==========
FastAPI backend for the standalone web chatbot track. Replaces the LINE-era
api/main.py (webhook), api/session.py (debounce) and api/confirmation.py
(Quick Reply state), which stay in the repo, labeled LEGACY, until removal is
approved.

Run:   uvicorn api.app:app --port 8000

THE FLOW THESE SIX ENDPOINTS SERVE  (see Claude.md §3)
--------------------------------------------------------
    POST /seasoning     tick seasonings (before the chat starts; then locked)
    POST /detect        photo(s)  -> ingredients          } either or both;
    POST /extract       text      -> include/exclude/tags } same session_id
    POST /extract_bert  the live frontend's text extractor: WangchanBERTa NER +
                        Claude fallback (nlp/extract_bert.py); degrades to the
                        /extract keyword path if the model or the LLM is unavailable
    POST /confirm       free-text reply -> confirm / reject / confirm+correction / unclear
    POST /correct       checklist removals + typed additions (after a reject)
    POST /recommend     confirmed list -> top-N recipes
    GET  /health        load-balancer check ({"status","detector","bert"}); not rate limited

Everything reused as-is: nlp.extract.extract(), recommender.recommend.recommend()
(seasoning bonus is its one change), api.mock_cv.detect() (the real YOLO wrapper
despite its name).

DETECTOR NOTE
--------------
There is no Gemini fallback anywhere in this codebase yet, so /detect applies
only the flat `confidence >= threshold` filter api/main.py always used. See
the TODO in _detect_one_image() for where the max-confidence -> Gemini routing
(Claude.md §4.1) belongs once it exists.
"""

import os
import sys
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path

# Same path fix api/main.py and recommend.py use, so `uvicorn api.app:app` and
# pytest both find nlp/ and recommender/.
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from api import intent, schemas, state, web_config
from nlp.extract import extract, load_ingredients
from nlp.extract_bert import bert_status, extract_bert
from recommender.recommend import recommend

_INGREDIENTS = load_ingredients()


# ===========================================================================
# Detector (loaded once at startup; the app still boots without weights)
# ===========================================================================

def _load_detector():
    """
    Import api.mock_cv (loads + warms the YOLO model) and return its detect().
    Kept as a function so tests can replace it. Returns None if the model
    can't load -- e.g. the *.pt weights are gitignored and absent -- so the
    other five endpoints keep working and /detect answers 503.
    """
    try:
        from api import mock_cv

        return mock_cv.detect
    except Exception as exc:  # noqa: BLE001 - any load failure means "no detector"
        print(f"[app] detector unavailable: {type(exc).__name__}: {exc}", flush=True)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.detector = _load_detector()
    yield


# YOLO's predict() isn't documented as thread-safe and there is one GPU anyway:
# sync endpoints run in a threadpool, so serialise detector calls.
_detector_lock = threading.Lock()


# ===========================================================================
# App, rate limiting, CORS
# ===========================================================================

def _client_ip(request: Request) -> str:
    """Per-IP rate-limit key. Behind a proxy, trust the first X-Forwarded-For hop."""
    if web_config.TRUST_FORWARDED_FOR:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_client_ip)
app = FastAPI(title="FoodFridgeGreen web chatbot API", lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": f"rate limit exceeded: {exc.detail}"})


if web_config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=web_config.CORS_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


# ===========================================================================
# Helpers
# ===========================================================================

def _session(session_id: str | None, *, create: bool) -> state.SessionState:
    """Look up a session, or create one when allowed and no id was passed."""
    try:
        return state.store.get_or_create(session_id) if create else state.store.get(session_id)
    except state.UnknownSession:
        raise HTTPException(404, "unknown session") from None


def _name_th(key: str) -> str | None:
    return _INGREDIENTS.get(key, {}).get("name_th")


def _detect_one_image(detector, path: str) -> dict[str, float]:
    """
    Run detect() on one saved image and apply the confidence filter.

    Returns {key: max confidence} for detections >= the threshold, the same
    filter api/main.py applied (>= CONFIDENCE_THRESHOLD, dedupe by key).

    TODO: Gemini fallback. Claude.md §4.1 says: if the image's MAX confidence is
    below the threshold, call the LLM instead of trusting YOLO. That routing
    does not exist in this codebase yet; it belongs here, before the filter.
    """
    kept: dict[str, float] = {}
    with _detector_lock:
        detections = detector(path)
    for det in detections:
        if det["confidence"] >= web_config.CONFIDENCE_THRESHOLD:
            key = det["ingredient"]
            kept[key] = max(det["confidence"], kept.get(key, 0.0))
    return kept


# ===========================================================================
# GET /health  (load-balancer check: no auth, deliberately NOT rate limited)
# ===========================================================================

@app.get("/health")
def health_endpoint(request: Request):
    detector = getattr(request.app.state, "detector", None)
    return {
        "status": "ok",
        "detector": "loaded" if detector else "unavailable",
        # "loaded" | "pending" (weights on disk, loads on first text request) | "unavailable"
        # (text falls back to the keyword extractor).
        "bert": bert_status(),
    }


# ===========================================================================
# POST /detect
# ===========================================================================

@app.post("/detect", response_model=schemas.DetectResponse)
@limiter.limit(web_config.LIMIT_DETECT)
def detect_endpoint(
    request: Request,
    images: list[UploadFile] = File(...),
    session_id: str | None = Form(default=None, pattern=schemas.SESSION_ID_REGEX),
):
    detector = getattr(request.app.state, "detector", None)
    if detector is None:
        raise HTTPException(503, "detector unavailable")
    if not images:
        raise HTTPException(422, "no images uploaded")
    if len(images) > web_config.MAX_IMAGES_PER_REQUEST:
        raise HTTPException(
            422, f"too many images (max {web_config.MAX_IMAGES_PER_REQUEST} per request)"
        )

    sess = _session(session_id, create=True)

    union: dict[str, float] = {}
    skipped: list[schemas.SkippedImage] = []
    processed = 0

    for upload in images:
        name = upload.filename or "image"
        if upload.content_type not in web_config.ALLOWED_IMAGE_TYPES:
            skipped.append(schemas.SkippedImage(filename=name, reason="unsupported type"))
            continue
        data = upload.file.read(web_config.MAX_IMAGE_BYTES + 1)
        if len(data) > web_config.MAX_IMAGE_BYTES:
            skipped.append(schemas.SkippedImage(filename=name, reason="file too large"))
            continue

        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[
            upload.content_type
        ]
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(data)
            for key, conf in _detect_one_image(detector, tmp_path).items():
                union[key] = max(conf, union.get(key, 0.0))
            processed += 1
        except Exception as exc:  # noqa: BLE001 - one unreadable image must not sink the batch
            print(f"[app] detect failed for {name!r}: {type(exc).__name__}", flush=True)
            skipped.append(schemas.SkippedImage(filename=name, reason="unreadable image"))
        finally:
            os.unlink(tmp_path)

    if processed == 0:
        raise HTTPException(
            422, f"no usable images: {[f'{s.filename}: {s.reason}' for s in skipped]}"
        )

    with state.store.lock:
        if sess.stage == state.STAGE_CONFIRMED:
            # Same reset as /extract and /extract_bert: a prior confirm cycle
            # already finished, so new photos describe a new meal.
            sess.start_new_round()
        sess.add_detected(union)
        sess.stage = state.STAGE_AWAITING_CONFIRM
        combined = sess.ingredients
        stage = sess.stage

    detected = sorted(union.items(), key=lambda kv: kv[1], reverse=True)
    return schemas.DetectResponse(
        session_id=sess.session_id,
        detected=[
            schemas.DetectedItem(ingredient=k, confidence=round(c, 3), name_th=_name_th(k))
            for k, c in detected
        ],
        ingredients=combined,
        images_processed=processed,
        images_skipped=skipped,
        stage=stage,
    )


# ===========================================================================
# POST /extract
# ===========================================================================

@app.post("/extract", response_model=schemas.ExtractResponse)
@limiter.limit(web_config.LIMIT_DEFAULT)
def extract_endpoint(request: Request, body: schemas.ExtractRequest):
    sess = _session(body.session_id, create=True)
    parsed = extract(body.text)

    with state.store.lock:
        if sess.stage == state.STAGE_CONFIRMED:
            # A prior confirm (and, in the real UI, /recommend) cycle already
            # finished on this session -- new text describes a new meal, not
            # an addition to the one that was just recommended.
            sess.start_new_round()
        sess.apply_text_result(parsed)
        sess.stage = state.STAGE_AWAITING_CONFIRM
        # `unknown` stays [] on this keyword path: extract() only sees tokens, and an
        # unresolved token is not known to have been meant as an ingredient.
        return schemas.ExtractResponse(
            session_id=sess.session_id,
            include=parsed["ingredients"],
            exclude=parsed["excluded"],
            health_tags=parsed["health_tags"],
            ingredients=sess.ingredients,
            stage=sess.stage,
        )


# ===========================================================================
# POST /extract_bert
# ===========================================================================
# WangchanBERTa NER primary, Claude Sonnet 5 fallback, plus a rule-based
# negation pass (see nlp/extract_bert.py). This is now the live frontend's
# primary text extractor (web/js/api.js), not just a side-by-side test
# endpoint -- /extract above stays untouched as a working fallback route.
# extract_bert()'s "excluded" output comes from a raw-text heuristic, not a
# model or /extract's tokenizer-based scan -- see nlp/extract_bert.py's
# docstring for what that heuristic does and does not catch.

@app.post("/extract_bert", response_model=schemas.ExtractResponse)
@limiter.limit(web_config.LIMIT_DEFAULT)
def extract_bert_endpoint(request: Request, body: schemas.ExtractRequest):
    sess = _session(body.session_id, create=True)
    # extract_bert() never raises for a missing model or a failed LLM fallback: it
    # degrades to the keyword extract() path itself (nlp/extract_bert.py).
    parsed = extract_bert(body.text)

    with state.store.lock:
        if sess.stage == state.STAGE_CONFIRMED:
            sess.start_new_round()
        sess.apply_text_result(parsed)
        sess.stage = state.STAGE_AWAITING_CONFIRM
        return schemas.ExtractResponse(
            session_id=sess.session_id,
            include=parsed["ingredients"],
            exclude=parsed["excluded"],
            health_tags=parsed["health_tags"],
            ingredients=sess.ingredients,
            stage=sess.stage,
            unknown=parsed.get("unknown", []),
        )


# ===========================================================================
# POST /confirm
# ===========================================================================

@app.post("/confirm", response_model=schemas.ConfirmResponse)
@limiter.limit(web_config.LIMIT_DEFAULT)
def confirm_endpoint(request: Request, body: schemas.ConfirmRequest):
    sess = _session(body.session_id, create=False)
    if sess.stage == state.STAGE_NEW:
        raise HTTPException(409, "nothing to confirm yet: send images or text first")

    result = intent.classify_intent(body.reply, sess.ingredients)
    corrections = schemas.Corrections()

    with state.store.lock:
        if result.intent == intent.CONFIRM:
            sess.stage = state.STAGE_CONFIRMED
        elif result.intent == intent.CONFIRM_AND_CORRECT:
            # Apply the correction, then ask again: the user confirmed the OLD
            # list, so the corrected one gets its own confirmation (same as /correct).
            # A removal here fixes the list ("not chicken, pork"); it is not a dietary
            # "no", so it must not ban dishes (ban_excluded=False), same as the /correct
            # checklist. An earlier first-message "no X" stays in `exclude`.
            sess.apply_text_result(
                {"ingredients": result.add, "excluded": result.remove, "health_tags": []},
                ban_excluded=False,
            )
            sess.stage = state.STAGE_AWAITING_CONFIRM
            corrections = schemas.Corrections(add=result.add, remove=result.remove)
        elif result.intent == intent.REJECT:
            sess.stage = state.STAGE_AWAITING_CORRECTION
            sess.reject_count += 1
        # UNCLEAR: nothing changes; the UI re-asks.

        return schemas.ConfirmResponse(
            session_id=sess.session_id,
            intent=result.intent,
            corrections=corrections,
            ingredients=sess.ingredients,
            stage=sess.stage,
        )


# ===========================================================================
# POST /correct
# ===========================================================================

@app.post("/correct", response_model=schemas.CorrectResponse)
@limiter.limit(web_config.LIMIT_DEFAULT)
def correct_endpoint(request: Request, body: schemas.CorrectRequest):
    sess = _session(body.session_id, create=False)
    if sess.stage == state.STAGE_NEW:
        raise HTTPException(409, "nothing to correct yet: send images or text first")

    add_text = (body.add_text or "").strip()
    if not body.exclude and not add_text:
        raise HTTPException(422, "nothing to correct: give `exclude` and/or `add_text`")

    with state.store.lock:
        before = sess.ingredients
        not_in_list = [key for key in body.exclude if key not in before]
        if not_in_list:
            raise HTTPException(422, f"not in the current ingredient list: {not_in_list}")

        # Checklist ticks are wrong detections: removed from the list, but they
        # do NOT ban dishes (unlike a typed "no X").
        sess.remove_ingredients(body.exclude)
        if add_text:
            sess.apply_text_result(extract(add_text))
        sess.stage = state.STAGE_AWAITING_CONFIRM

        after = sess.ingredients
        return schemas.CorrectResponse(
            session_id=sess.session_id,
            removed=[key for key in before if key not in after],
            added=[key for key in after if key not in before],
            ingredients=after,
            health_tags=list(sess.health_tags),
            stage=sess.stage,
        )


# ===========================================================================
# POST /seasoning
# ===========================================================================

@app.post("/seasoning", response_model=schemas.SeasoningResponse)
@limiter.limit(web_config.LIMIT_DEFAULT)
def seasoning_endpoint(request: Request, body: schemas.SeasoningRequest):
    unknown = [
        key
        for key in (body.seasonings or [])
        if not _INGREDIENTS.get(key, {}).get("is_seasoning")
    ]
    if unknown:
        raise HTTPException(422, f"not seasoning ingredients: {unknown}")

    sess = _session(body.session_id, create=True)
    with state.store.lock:
        locked = sess.stage != state.STAGE_NEW
        # `seasonings` omitted = read-only: the frontend can learn whether the
        # list is still editable without provoking a 409.
        if body.seasonings is not None:
            if locked:
                raise HTTPException(409, "seasonings are locked once the chat starts")
            sess.seasonings = list(dict.fromkeys(body.seasonings))
        return schemas.SeasoningResponse(
            session_id=sess.session_id, seasonings=list(sess.seasonings), locked=locked
        )


# ===========================================================================
# POST /recommend
# ===========================================================================

@app.post("/recommend", response_model=schemas.RecommendResponse)
@limiter.limit(web_config.LIMIT_DEFAULT)
def recommend_endpoint(request: Request, body: schemas.RecommendRequest):
    sess = _session(body.session_id, create=False)
    with state.store.lock:
        if sess.stage != state.STAGE_CONFIRMED:
            raise HTTPException(409, "ingredients not confirmed yet: call /confirm first")
        # The picker's choice rides on this request (every page of "ขอเพิ่ม" re-sends it) and is
        # kept in the session like the list and the tags; start_new_round() resets it to "all".
        sess.category = body.category
        used = schemas.UsedInputs(
            ingredients=sess.ingredients,
            exclude=list(sess.exclude),
            health_tags=list(sess.health_tags),
            seasonings=list(sess.seasonings),
            category=sess.category,
        )

    def run(category: str, top_k: int) -> list[dict]:
        return recommend(
            ingredients=used.ingredients,
            health_tags=used.health_tags,
            excluded=used.exclude,
            top_k=top_k,
            seasonings=used.seasonings,
            category=category,
        )

    results = run(used.category, body.top_n)

    # Nothing in the chosen category: is that the category's fault, or would "all" be empty too?
    # One extra cheap call, only in the already-empty case, so the UI can pick the right message.
    empty_for_category = (
        not results and used.category != "all" and bool(run("all", 1))
    )
    return schemas.RecommendResponse(
        session_id=sess.session_id,
        used=used,
        recipes=results,
        count=len(results),
        empty_for_category=empty_for_category,
    )
