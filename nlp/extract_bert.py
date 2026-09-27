"""
nlp/extract_bert.py
====================
A second, experimental text extractor for POST /extract_bert (see api/app.py),
built on a fine-tuned WangchanBERTa NER model. This is NOT used by the
production POST /extract route (nlp.extract.extract(), dictionary + fuzzy +
Trie) -- it exists so the BERT model can be tested side by side with it
before any decision to switch.

    extract_bert(text) -> {"ingredients": [...], "health_tags": [...], "excluded": []}

Same three-key contract as nlp.extract.extract() (see that module's
docstring), except "excluded" is always empty here -- see "KNOWN GAP" below.

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

KNOWN GAP: NO EXCLUSION DETECTION
----------------------------------
The label schema here is two entity types only: ING, HEALTH. Neither the
fine-tuned model nor the ported LLM prompt has a way to represent negation
("no pork"), unlike nlp.extract.extract()'s two-token "ไม่" + verb scan.
So extract_bert()'s "excluded" key is always []. This is a real, named
functional gap versus /extract, not an oversight -- see Claude.md's working
style rule about naming why something doesn't make it into a result.
"""

import json
import threading

from nlp.extract import resolve_token

# ===========================================================================
# Model + label config loading (lazy, thread-safe singleton)
# ===========================================================================

_model = None
_tokenizer = None
_label_config = None
_model_lock = threading.Lock()


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
    global _model, _tokenizer, _label_config
    with _model_lock:
        if _model is None:
            model_path = _model_path()
            if not model_path.exists():
                raise FileNotFoundError(f"BERT NER model folder not found: {model_path}")

            from transformers import AutoModelForTokenClassification, AutoTokenizer

            _label_config = _load_label_config(model_path)
            _tokenizer = AutoTokenizer.from_pretrained(str(model_path))
            _model = AutoModelForTokenClassification.from_pretrained(str(model_path))
            _model.eval()
        return _model, _tokenizer, _label_config


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
    ablation (F1 0.774, 0% hallucination on the "unclear" category). Fails
    closed to [] on anything unparseable -- no entities is a safe answer,
    a crash is not.
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
        return []  # fail closed: no entities rather than a crash

    entities = []
    for item in found:
        value = item.get("value", "")
        idx = text.find(value)
        if value and idx != -1:
            entities.append({"start": idx, "end": idx + len(value), "type": item.get("type", "ING"), "value": value})
    return entities


# ===========================================================================
# Public entry point
# ===========================================================================

def _resolve_entities(entities: list[dict]) -> dict:
    """Map raw entity spans to canonical keys, dropping anything unresolvable."""
    ingredients: list[str] = []
    health_tags: list[str] = []
    for entity in entities:
        resolved = resolve_token(entity["value"].strip())
        if resolved is None:
            continue
        if resolved.startswith("health:"):
            tag = resolved.removeprefix("health:")
            if tag not in health_tags:
                health_tags.append(tag)
        elif resolved not in ingredients:
            ingredients.append(resolved)
    return {"ingredients": ingredients, "health_tags": health_tags, "excluded": []}


def extract_bert(text: str) -> dict:
    """
    BERT-primary text extraction for POST /extract_bert.

    Returns the same three-key contract as nlp.extract.extract():
        {"ingredients": [...], "health_tags": [...], "excluded": []}
    "excluded" is always empty -- see the module docstring's KNOWN GAP.

    Raises FileNotFoundError if the BERT model folder isn't configured on
    this server; the caller (api/app.py) turns that into a 503.
    """
    _, _, label_config = _get_model_and_config()
    threshold = label_config["confidence_threshold"]

    entities = predict_entities_bert_with_confidence(text)
    if not entities or any(e["confidence"] < threshold for e in entities):
        entities = predict_entities_llm(text)

    return _resolve_entities(entities)
