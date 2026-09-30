"""
nlp/extract_bert.py
====================
A second, experimental text extractor for POST /extract_bert (see api/app.py),
built on a fine-tuned WangchanBERTa NER model. This is NOT used by the
production POST /extract route (nlp.extract.extract(), dictionary + fuzzy +
Trie) -- it exists so the BERT model can be tested side by side with it
before any decision to switch.

    extract_bert(text) -> {"ingredients": [...], "health_tags": [...], "excluded": [...],
                           "unknown": [...]}

The same three keys as nlp.extract.extract() (see that module's docstring),
plus "unknown": the raw words an entity labelled ING carried that resolved to
no dictionary key (e.g. "มังคุด"), so the UI can say so instead of dropping
them silently. "excluded" comes from the rule-based negation pass -- see
"KNOWN GAP" below.

DEGRADES TO THE KEYWORD PATH, NEVER FAILS
-----------------------------------------
extract_bert() falls back to nlp.extract.extract() (with "unknown" == [] --
unresolved keyword tokens are not known to be ingredients) when
  - the BERT model can't be loaded (folder/weights absent, transformers/torch
    missing, corrupt files): one warning per process, then silent; or
  - the Sonnet fallback fails for ANY reason (no key, timeout, 429, a rejected
    model id, unparseable output): one `[extract] ...` log line per failure,
    same pattern as api/intent.py. Never the key, never the user's text.

HOW IT WORKS
------------
1. predict_entities_bert_with_confidence(text) -- ported as-is from the
   Colab notebook that trained and ablated this model (BERT overall F1
   0.902 vs. a Claude Haiku zero-shot baseline's F1 0.774). Runs the
   fine-tuned model, decodes its BIO tags into character spans, and scores
   each span's confidence as the mean per-token max-softmax probability.
2. Fallback (whole-sentence, not per-entity): if BERT finds zero entities,
   OR any entity's confidence is below label_config.json's
   confidence_threshold, the BERT result is discarded entirely and
   predict_entities_llm(text) is called instead (Claude Sonnet 5, prompt
   also ported from the same Colab notebook).

   The confidence score is a WEAK signal, verified in the ablation: mean
   confidence was 0.996 on true positives and 0.994 on false positives
   (min 0.782) -- a threshold barely separates correct predictions from
   confidently wrong ones. In practice this fallback mainly helps the
   "BERT found nothing" case; it will not reliably catch a confident wrong
   span, and the fallback should be expected to fire often, not rarely.
   That is exactly why the fallback calls Sonnet, not Haiku.
3. Whichever list won (BERT's or the LLM's), every entity's raw text is
   resolved to a canonical key via nlp.extract.resolve_token() -- the same
   exact/fuzzy synonym-index lookup nlp.extract.extract() and
   api.intent.classify_intent() already use. Neither model can invent a
   key outside data/ingredients.json / data/health_terms.json: an entity
   that doesn't resolve is dropped. The resolver's own classification
   (ingredient key vs. "health:<tag>") is trusted over the model's
   self-reported entity type, since the resolver is grounded in the
   dictionaries and the model can mislabel type.

4. apply_negation_cues(text, entities) -- a NegEx-style rule-based pass, run
   on whichever entity list won (BERT's or the LLM's), after the fallback
   decision and before resolution. For each entity it looks backward, up to
   the previous entity's end or a fixed character window (whichever is
   closer), for a negation cue substring ("ไม่เอา", "ไม่ใส่", "ไม่มี", the
   same NEGATION_VERBS nlp.extract.py's own tokenizer-based scan uses, just
   pre-combined for raw-text substring search). A matching ING entity is
   marked negated=True and routed to "excluded" instead of "ingredients".

KNOWN GAP: NEGATION DETECTION IS A RAW-TEXT HEURISTIC, NOT PARITY WITH /extract
--------------------------------------------------------------------------------
The label schema here is two entity types only: ING, HEALTH -- there is no
model-level negation type. apply_negation_cues() (above) covers the common
case ("ไม่เอาหมู") without retraining, but it is NOT the same mechanism as
nlp.extract.extract()'s tokenizer-based two-token scan, and two limitations
remain, both left as-is on purpose rather than silently glossed over:
  - HEALTH entities are never marked negated, even if a cue sits in their
    window -- negated health tags ("ไม่กินคีโต") are rarer and out of scope
    for this pass.
  - The cue must fall within NEGATION_CUE_WINDOW_CHARS characters of the
    entity's start (and not cross into a preceding entity's span). A cue
    further back in a long clause will be missed, unlike /extract's
    tokenizer scan, which has no such window limit.
"""

import json
import threading
import time

from nlp.extract import NEGATION_CUES, extract, resolve_token

# ===========================================================================
# Model + label config loading (lazy, thread-safe singleton)
# ===========================================================================

_model = None
_tokenizer = None
_label_config = None
_model_lock = threading.Lock()

# Set when loading failed for a reason other than "folder not there" (missing
# transformers/torch, corrupt weights). Remembered so a slow failing load is not
# retried, under _model_lock, on every request. A missing folder is NOT
# remembered: checking it is free, so dropping the model in works without a restart.
_load_failure = None
_warned: set[str] = set()   # warning keys already printed (each is logged once per process)
_warned_lock = threading.Lock()


def _warn_once(key: str, message: str) -> None:
    with _warned_lock:
        if key in _warned:
            return
        _warned.add(key)
    print(message, flush=True)


def _model_path():
    from api import web_config

    return web_config.BERT_NER_MODEL_PATH


def _load_label_config(model_path) -> dict:
    """
    Read label_config.json from the exported model folder.

    id2label's keys are strings (JSON has no int keys) -- cast with int(k)
    here, once, so callers never have to remember to do it themselves.
    """
    config_path = model_path / "label_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"{config_path} not found")
    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)
    return {
        "LABEL_LIST": raw["LABEL_LIST"],
        "id2label": {int(k): v for k, v in raw["id2label"].items()},
        "confidence_threshold": float(raw.get("confidence_threshold", 0.8)),
    }


def _get_model_and_config():
    """
    One shared model/tokenizer/label_config (thread-safe), built on first use.
    Imports are lazy so the app still boots without transformers/torch
    installed or the model folder present -- the failure then surfaces as a
    503 from POST /extract_bert instead of at startup.
    """
    global _model, _tokenizer, _label_config, _load_failure
    with _model_lock:
        if _model is None:
            if _load_failure is not None:
                raise _load_failure
            model_path = _model_path()
            if not model_path.exists():
                raise FileNotFoundError(f"BERT NER model folder not found: {model_path}")

            try:
                from transformers import AutoModelForTokenClassification, AutoTokenizer

                label_config = _load_label_config(model_path)
                tokenizer = AutoTokenizer.from_pretrained(str(model_path))
                model = AutoModelForTokenClassification.from_pretrained(str(model_path))
                model.eval()
            except FileNotFoundError:
                raise  # a missing file is re-checked on the next request
            except Exception as exc:  # noqa: BLE001 - remember any other load failure
                _load_failure = exc
                raise
            _label_config, _tokenizer, _model = label_config, tokenizer, model
        return _model, _tokenizer, _label_config


def bert_status() -> str:
    """
    For /health, without importing torch or loading anything:
        "loaded"       the model is in memory
        "unavailable"  the weights are missing, or a load already failed
        "pending"      weights are on disk; they load on the first text request
    """
    if _model is not None:
        return "loaded"
    if _load_failure is not None:
        return "unavailable"
    path = _model_path()
    has_weights = path.is_dir() and any(
        [*path.glob("*.safetensors"), *path.glob("pytorch_model*.bin")]
    )
    return "pending" if has_weights and (path / "label_config.json").exists() else "unavailable"


# ===========================================================================
# BERT entity extraction (ported as-is from the Colab ablation notebook)
# ===========================================================================

def predict_entities_bert_with_confidence(text: str) -> list[dict]:
    """
    Run the fine-tuned WangchanBERTa NER model and decode its BIO tags into
    character-span entities, each carrying a 0-1 confidence score (average
    softmax probability of its predicted label, averaged over the entity's
    tokens). Ported as-is from the notebook that trained and ablated this
    model -- do not "improve" the decoding logic here without re-running
    that ablation.
    """
    import torch
    import torch.nn.functional as F

    model, tokenizer, label_config = _get_model_and_config()
    id2label = label_config["id2label"]

    enc = tokenizer(text, return_tensors="pt", truncation=True, max_length=64, return_offsets_mapping=True)
    offsets = enc.pop("offset_mapping")[0].tolist()
    enc = {k: v.to(model.device) for k, v in enc.items()}

    with torch.no_grad():
        logits = model(**enc).logits[0]  # (seq_len, num_labels)
    probs = F.softmax(logits, dim=-1)  # (seq_len, num_labels)
    confs, pred_ids = probs.max(dim=-1)  # per-token confidence + label id
    pred_ids = pred_ids.tolist()
    confs = confs.tolist()
    pred_labels = [id2label[i] for i in pred_ids]

    entities = []
    cur_type, cur_start, cur_end, cur_confs = None, None, None, []

    def flush():
        if cur_type is not None:
            value = text[cur_start:cur_end]
            entities.append(
                {
                    "type": cur_type,
                    "start": cur_start,
                    "end": cur_end,
                    "value": value,
                    "confidence": round(sum(cur_confs) / len(cur_confs), 4),
                }
            )

    for (start, end), label, conf in zip(offsets, pred_labels, confs):
        if start == end:  # special tokens ([CLS], [SEP], padding)
            continue
        if label == "O":
            flush()
            cur_type, cur_start, cur_end, cur_confs = None, None, None, []
            continue
        prefix, ent_type = label.split("-", 1)
        if prefix == "B" or ent_type != cur_type:
            flush()
            cur_type, cur_start, cur_end, cur_confs = ent_type, start, end, [conf]
        else:  # "I-" continuing the same entity
            cur_end = end
            cur_confs.append(conf)
    flush()

    return entities


# ===========================================================================
# LLM fallback (Claude Sonnet 5) -- ported as-is from the Colab notebook,
# only the model string changed. Not the same use case as api/intent.py's
# classifier, so this keeps its own small client rather than importing
# intent.py's (a private module-level singleton meant for /confirm only).
# ===========================================================================

LLM_PROMPT = """\
คุณเป็นระบบสกัด entity จากข้อความภาษาไทย หาคำที่เป็น "วัตถุดิบอาหาร" (ING) และ "รูปแบบการกิน/ไดเอท" (HEALTH เช่น คีโต คลีน มังสวิรัติ วีแกน) ในข้อความต่อไปนี้

ตอบเป็น JSON array เท่านั้น ไม่ต้องมีคำอธิบายอื่น รูปแบบ:
[{{"value": "<คำที่เจอ>", "type": "ING หรือ HEALTH"}}]
ถ้าไม่เจอเลยให้ตอบ []

ข้อความ: {text}"""

class _BadLLMResponse(Exception):
    """The API call worked but its answer can't be used. Message is ours: no user text."""


_client = None
_client_lock = threading.Lock()


def _get_client():
    """
    Lazy, thread-safe Anthropic client for the extraction fallback only.
    Same shape as api/intent.py's _get_client, deliberately duplicated
    rather than imported, so this change stays scoped to extraction and
    never touches the /confirm module.
    """
    global _client
    with _client_lock:
        if _client is None:
            import anthropic
            from api import web_config

            _client = anthropic.Anthropic(
                api_key=web_config.ANTHROPIC_API_KEY,
                timeout=web_config.EXTRACTION_LLM_TIMEOUT_SECONDS,
                max_retries=0,
            )
        return _client


def predict_entities_llm(text: str) -> list[dict]:
    """
    Claude Sonnet 5 fallback, same prompt/parsing validated in the Colab
    ablation (F1 0.774, 0% hallucination on the "unclear" category).

    A valid answer of [] means "no entities". Anything unusable -- not JSON,
    not a list of {"value","type"} objects -- raises _BadLLMResponse, and so
    does any API error; extract_bert() catches it and uses the keyword path.
    """
    from api import web_config

    resp = _get_client().messages.create(
        model=web_config.EXTRACTION_LLM_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": LLM_PROMPT.format(text=text)}],
    )
    raw = resp.content[0].text.strip()

    # Claude sometimes wraps JSON in a markdown code fence (```json ... ```);
    # strip it off before parsing, otherwise json.loads silently fails.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        raw = raw.removeprefix("json").strip()

    try:
        found = json.loads(raw)
    except json.JSONDecodeError:
        raise _BadLLMResponse("output is not JSON") from None
    if not isinstance(found, list) or not all(isinstance(item, dict) for item in found):
        raise _BadLLMResponse("output is not a list of objects")

    entities = []
    for item in found:
        value = item.get("value", "")
        idx = text.find(value)
        if value and idx != -1:
            entities.append({"start": idx, "end": idx + len(value), "type": item.get("type", "ING"), "value": value})
    return entities


# ===========================================================================
# Negation post-processing (NegEx-style rule-based pass, no model involved)
# ===========================================================================

# Tune if needed after testing on real examples.
NEGATION_CUE_WINDOW_CHARS = 10


def apply_negation_cues(text: str, entities: list[dict]) -> list[dict]:
    """
    For each entity, look back from its start position (up to the previous
    entity's end, or a fixed character window, whichever is closer) for a
    negation cue substring. If found, mark entity["negated"] = True. Does
    not mutate entity["type"] -- "what BERT/LLM predicted" and "polarity
    decision" stay separate concerns for debuggability.

    Bounding the window at the previous entity's end (not just a flat
    character count) matters: without it, "ไม่เอาหมู เอาไก่แทน" would let
    the "ไม่" that belongs to หมู leak into ไก่'s window too.
    """
    entities_sorted = sorted(entities, key=lambda e: e["start"])
    prev_end = 0
    for e in entities_sorted:
        window_start = max(prev_end, e["start"] - NEGATION_CUE_WINDOW_CHARS)
        window = text[window_start:e["start"]]
        e["negated"] = any(cue in window for cue in NEGATION_CUES)
        prev_end = e["end"]
    return entities_sorted


# ===========================================================================
# Public entry point
# ===========================================================================

def _resolve_entities(entities: list[dict]) -> dict:
    """
    Map raw entity spans to canonical keys, dropping anything unresolvable.

    A negated ING entity (see apply_negation_cues above) routes to excluded
    instead of ingredients. HEALTH entities are never affected by the
    negated flag, even if one is set -- see the module docstring's KNOWN GAP.
    """
    ingredients: list[str] = []
    excluded: list[str] = []
    health_tags: list[str] = []
    unknown: list[str] = []
    for entity in entities:
        value = entity["value"].strip()
        resolved = resolve_token(value)
        if resolved is None:
            # The model labelled this span an ingredient but the dictionary has no
            # key for it: report it rather than dropping it silently. HEALTH spans
            # that don't resolve are not "unknown ingredients", so they stay dropped.
            if entity.get("type") == "ING" and value and value not in unknown:
                unknown.append(value)
            continue
        if resolved.startswith("health:"):
            tag = resolved.removeprefix("health:")
            if tag not in health_tags:
                health_tags.append(tag)
        elif entity.get("negated"):
            if resolved not in excluded:
                excluded.append(resolved)
        elif resolved not in ingredients:
            ingredients.append(resolved)

    # Same rule as nlp.extract.extract(): a key is never allowed in both
    # lists at once, and excluded wins.
    ingredients = [key for key in ingredients if key not in excluded]

    return {
        "ingredients": ingredients,
        "health_tags": health_tags,
        "excluded": excluded,
        "unknown": unknown,
    }


def _keyword_result(text: str) -> dict:
    """
    The keyword path (nlp.extract.extract) in extract_bert()'s shape.

    "unknown" is always [] here: extract() only sees tokens, and an unresolved
    keyword token is not known to have been meant as an ingredient (most
    tokens are function words like "มี" or "กับ"), so reporting them would
    flood the user with false "not in the system" notes.
    """
    return {**extract(text), "unknown": []}


def _log_llm_fallback(exc: Exception, elapsed_ms: float) -> None:
    """
    One line per failure: which failure, never the user's text or the key. Only
    our own _BadLLMResponse messages are echoed (same rule as api/intent.py).
    """
    parts = [type(exc).__name__]
    status = getattr(exc, "status_code", None)
    if status:
        parts.append(f"status={status}")
    request_id = getattr(exc, "request_id", None)
    if request_id:
        parts.append(f"request_id={request_id}")
    if isinstance(exc, _BadLLMResponse):
        parts.append(str(exc))
    print(
        f"[extract] LLM fallback failed ({', '.join(parts)}, {elapsed_ms:.0f}ms) "
        f"-> keyword extract()",
        flush=True,
    )


def extract_bert(text: str) -> dict:
    """
    BERT-primary text extraction for POST /extract_bert.

    Returns nlp.extract.extract()'s three keys plus "unknown":
        {"ingredients": [...], "health_tags": [...], "excluded": [...], "unknown": [...]}
    "excluded" comes only from apply_negation_cues's rule-based scan, not
    from any model -- see the module docstring's KNOWN GAP for what that
    heuristic does and does not catch.

    Never raises for a missing model or a failed LLM fallback: both degrade
    to the keyword extract() path (see the module docstring).
    """
    from api import web_config

    try:
        _, _, label_config = _get_model_and_config()
    except Exception as exc:  # noqa: BLE001 - any load failure means "no BERT"
        _warn_once(
            "bert_unavailable",
            f"[extract] BERT model unavailable ({type(exc).__name__}: "
            f"{_model_path()}) -> using keyword extract() for text input",
        )
        return _keyword_result(text)
    threshold = label_config["confidence_threshold"]

    entities = predict_entities_bert_with_confidence(text)
    if not entities or any(e["confidence"] < threshold for e in entities):
        if not web_config.anthropic_key_configured():
            _warn_once(
                "llm_no_key",
                "[extract] ANTHROPIC_API_KEY not configured: BERT-unsure text uses keyword extract()",
            )
            return _keyword_result(text)
        started = time.monotonic()
        try:
            entities = predict_entities_llm(text)
        except Exception as exc:  # noqa: BLE001 - by design, ANY failure must fall back
            _log_llm_fallback(exc, (time.monotonic() - started) * 1000)
            return _keyword_result(text)

    entities = apply_negation_cues(text, entities)
    return _resolve_entities(entities)
