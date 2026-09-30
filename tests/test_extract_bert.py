"""
tests/test_extract_bert.py
===========================
The experimental BERT-primary text extractor (nlp/extract_bert.py) behind
POST /extract_bert: fallback routing, id2label casting, canonical-key
resolution, and the three-key contract. Mirrors the mocking style of
tests/test_intent_llm.py so these tests never need real model weights or a
real Anthropic call.

Run with:
    pytest tests/test_extract_bert.py -v
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api import web_config
from nlp import extract_bert

THRESHOLD = 0.8


@pytest.fixture
def label_config(monkeypatch):
    config = {
        "LABEL_LIST": ["O", "B-ING", "I-ING", "B-HEALTH", "I-HEALTH"],
        "id2label": {0: "O", 1: "B-ING", 2: "I-ING", 3: "B-HEALTH", 4: "I-HEALTH"},
        "confidence_threshold": THRESHOLD,
    }
    monkeypatch.setattr(
        extract_bert, "_get_model_and_config", lambda: (None, None, config)
    )
    return config


@pytest.fixture
def llm_enabled(monkeypatch):
    """extract_bert() only attempts the LLM fallback when a key is configured; tests/conftest.py blanks it."""
    monkeypatch.setattr(web_config, "ANTHROPIC_API_KEY", "sk-ant-api03-FAKEKEYFORTESTS-do-not-leak")


def entity(value, ent_type="ING", confidence=0.99):
    return {"type": ent_type, "start": 0, "end": len(value), "value": value, "confidence": confidence}


def entity_in(text, value, ent_type="ING", confidence=0.99):
    """Like entity(), but with start/end resolved to value's real position in text."""
    idx = text.find(value)
    assert idx != -1, f"{value!r} not found in {text!r}"
    return {"type": ent_type, "start": idx, "end": idx + len(value), "value": value, "confidence": confidence}


# ---------------------------------------------------------------------------
# Routing: BERT primary, whole-sentence fallback to the LLM
# ---------------------------------------------------------------------------

def test_high_confidence_bert_result_is_used_as_is(monkeypatch, label_config):
    monkeypatch.setattr(
        extract_bert, "predict_entities_bert_with_confidence", lambda text: [entity("ไก่", confidence=0.99)]
    )

    def _llm_should_not_be_called(text):
        raise AssertionError("LLM fallback must not fire when BERT is confident")

    monkeypatch.setattr(extract_bert, "predict_entities_llm", _llm_should_not_be_called)

    result = extract_bert.extract_bert("มีไก่")
    assert result["ingredients"] == ["chicken"]


def test_zero_bert_entities_triggers_the_llm_fallback(monkeypatch, label_config, llm_enabled):
    monkeypatch.setattr(extract_bert, "predict_entities_bert_with_confidence", lambda text: [])
    monkeypatch.setattr(
        extract_bert, "predict_entities_llm", lambda text: [entity("ไข่", confidence=None)]
    )

    result = extract_bert.extract_bert("x")
    assert result["ingredients"] == ["egg"]


def test_one_low_confidence_entity_discards_the_whole_bert_result(monkeypatch, label_config, llm_enabled):
    """Whole-sentence fallback: one weak entity throws out BERT's other, confident entities too."""
    monkeypatch.setattr(
        extract_bert,
        "predict_entities_bert_with_confidence",
        lambda text: [entity("ไก่", confidence=0.99), entity("ไข่", confidence=0.5)],
    )
    monkeypatch.setattr(
        extract_bert, "predict_entities_llm", lambda text: [entity("กระเทียม", confidence=None)]
    )

    result = extract_bert.extract_bert("x")
    assert result["ingredients"] == ["garlic"]  # BERT's "chicken" is gone, not merged in


def test_confidence_exactly_at_threshold_does_not_fall_back(monkeypatch, label_config):
    monkeypatch.setattr(
        extract_bert, "predict_entities_bert_with_confidence", lambda text: [entity("ไก่", confidence=THRESHOLD)]
    )

    def _llm_should_not_be_called(text):
        raise AssertionError("threshold is inclusive: exactly-at should not fall back")

    monkeypatch.setattr(extract_bert, "predict_entities_llm", _llm_should_not_be_called)

    result = extract_bert.extract_bert("มีไก่")
    assert result["ingredients"] == ["chicken"]


# ---------------------------------------------------------------------------
# label_config.json loading
# ---------------------------------------------------------------------------

def test_id2label_string_keys_are_cast_to_int(tmp_path):
    raw = {
        "LABEL_LIST": ["O", "B-ING", "I-ING", "B-HEALTH", "I-HEALTH"],
        "id2label": {"0": "O", "1": "B-ING", "2": "I-ING", "3": "B-HEALTH", "4": "I-HEALTH"},
        "confidence_threshold": 0.8,
    }
    (tmp_path / "label_config.json").write_text(json.dumps(raw), encoding="utf-8")

    config = extract_bert._load_label_config(tmp_path)
    assert config["id2label"][0] == "O"
    assert config["id2label"][3] == "B-HEALTH"
    assert all(isinstance(k, int) for k in config["id2label"])


def test_missing_label_config_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_bert._load_label_config(tmp_path)


# ---------------------------------------------------------------------------
# Resolution to canonical keys: the model can propose a span, never a key
# ---------------------------------------------------------------------------

def test_health_entity_resolves_into_health_tags_not_ingredients(monkeypatch, label_config):
    monkeypatch.setattr(
        extract_bert, "predict_entities_bert_with_confidence", lambda text: [entity("คลีน", ent_type="HEALTH")]
    )
    result = extract_bert.extract_bert("x")
    assert result["health_tags"] == ["clean"]
    assert result["ingredients"] == []


def test_resolver_classification_wins_over_the_models_self_reported_type(monkeypatch, label_config):
    """A HEALTH-labeled span whose text is actually an ingredient synonym still resolves as an ingredient."""
    monkeypatch.setattr(
        extract_bert, "predict_entities_bert_with_confidence", lambda text: [entity("ไก่", ent_type="HEALTH")]
    )
    result = extract_bert.extract_bert("x")
    assert result["ingredients"] == ["chicken"]
    assert result["health_tags"] == []


def test_unresolvable_entity_is_dropped_not_invented(monkeypatch, label_config):
    monkeypatch.setattr(
        extract_bert, "predict_entities_bert_with_confidence", lambda text: [entity("zzzqqqnotaword")]
    )
    result = extract_bert.extract_bert("x")
    assert result == {"ingredients": [], "health_tags": [], "excluded": [], "unknown": ["zzzqqqnotaword"]}


def test_duplicate_entities_are_not_repeated(monkeypatch, label_config):
    monkeypatch.setattr(
        extract_bert,
        "predict_entities_bert_with_confidence",
        lambda text: [entity("ไก่"), entity("ไก่")],
    )
    result = extract_bert.extract_bert("x")
    assert result["ingredients"] == ["chicken"]


# ---------------------------------------------------------------------------
# Contract: the three keys of nlp.extract.extract(), plus "unknown"
# ---------------------------------------------------------------------------

def test_extract_bert_returns_the_three_agreed_keys(monkeypatch, label_config):
    monkeypatch.setattr(extract_bert, "predict_entities_bert_with_confidence", lambda text: [])
    monkeypatch.setattr(extract_bert, "predict_entities_llm", lambda text: [])

    result = extract_bert.extract_bert("")
    assert set(result.keys()) == {"ingredients", "health_tags", "excluded", "unknown"}
    assert all(isinstance(v, list) for v in result.values())


def test_health_tags_are_unaffected_by_a_negation_cue_in_their_window():
    """Documented scope limit: HEALTH is never routed to excluded, cue or not."""
    text = "ไม่เอาคลีน"
    entities = extract_bert.apply_negation_cues(text, [entity_in(text, "คลีน", ent_type="HEALTH")])
    result = extract_bert._resolve_entities(entities)
    assert result["health_tags"] == ["clean"]
    assert result["excluded"] == []


# ---------------------------------------------------------------------------
# apply_negation_cues() -- NegEx-style rule-based negation, no model involved
# ---------------------------------------------------------------------------

def test_negated_ingredient_is_routed_to_excluded():
    text = "ไม่เอาหมูนะ"
    entities = extract_bert.apply_negation_cues(text, [entity_in(text, "หมู")])
    result = extract_bert._resolve_entities(entities)
    assert result["excluded"] == ["pork"]
    assert result["ingredients"] == []


def test_mixed_sentence_splits_include_and_exclude_correctly():
    text = "มีข้าวอยู่ แต่ไม่เอาหมูนะ"
    entities = extract_bert.apply_negation_cues(
        text, [entity_in(text, "ข้าว"), entity_in(text, "หมู")]
    )
    result = extract_bert._resolve_entities(entities)
    assert result["ingredients"] == ["rice"]
    assert result["excluded"] == ["pork"]


def test_negation_window_does_not_cross_into_the_previous_entity():
    """The 'ไม่' that negates หมู must not also negate ไก่ right after it."""
    text = "ไม่เอาหมู เอาไก่แทน"
    entities = extract_bert.apply_negation_cues(
        text, [entity_in(text, "หมู"), entity_in(text, "ไก่")]
    )
    result = extract_bert._resolve_entities(entities)
    assert result["excluded"] == ["pork"]
    assert result["ingredients"] == ["chicken"]


def test_no_cue_at_all_is_not_a_false_positive():
    text = "มีหมูอยู่"
    entities = extract_bert.apply_negation_cues(text, [entity_in(text, "หมู")])
    result = extract_bert._resolve_entities(entities)
    assert result["ingredients"] == ["pork"]
    assert result["excluded"] == []


def test_negation_applies_after_whichever_path_won(monkeypatch, label_config, llm_enabled):
    """End-to-end through extract_bert(): the fallback's entities get the same negation pass."""
    monkeypatch.setattr(extract_bert, "predict_entities_bert_with_confidence", lambda text: [])
    monkeypatch.setattr(
        extract_bert, "predict_entities_llm", lambda text: [entity_in(text, "หมู")]
    )
    result = extract_bert.extract_bert("ไม่เอาหมูนะ")
    assert result["excluded"] == ["pork"]
    assert result["ingredients"] == []


def test_a_key_negated_and_affirmed_in_the_same_message_ends_up_excluded_only():
    """Mirrors nlp.extract.extract()'s own rule: excluded wins, never both lists."""
    text = "มีหมู ไม่เอาหมู"
    # entity_in() only finds the FIRST occurrence of a value, and this text
    # mentions "หมู" twice, so both spans are built explicitly here instead.
    first = text.find("หมู")
    second = text.find("หมู", first + 1)
    entities = extract_bert.apply_negation_cues(
        text,
        [
            {"type": "ING", "start": first, "end": first + 3, "value": "หมู", "confidence": 0.99},
            {"type": "ING", "start": second, "end": second + 3, "value": "หมู", "confidence": 0.99},
        ],
    )
    result = extract_bert._resolve_entities(entities)
    assert result["excluded"] == ["pork"]
    assert result["ingredients"] == []


# ---------------------------------------------------------------------------
# BERT's own BIO decode logic (no mocking of predict_entities_bert_with_confidence)
# ---------------------------------------------------------------------------

def test_bio_decode_merges_consecutive_i_tags_into_one_span(monkeypatch):
    """
    Fake tokenizer/model output standing in for a real WangchanBERTa forward
    pass, to exercise the ported BIO-flush logic itself (offsets, B-/I-
    merging, confidence averaging) without needing real weights.
    """
    import torch

    text = "พริกแกงเขียวหวาน"
    fake_config = {
        "id2label": {0: "O", 1: "B-ING", 2: "I-ING", 3: "B-HEALTH", 4: "I-HEALTH"},
    }

    class FakeTokenizer:
        def __call__(self, text, return_tensors, truncation, max_length, return_offsets_mapping):
            # [CLS] + one token spanning the whole word + [SEP]
            offsets = torch.tensor([[[0, 0], [0, len(text)], [0, 0]]])
            return {
                "input_ids": torch.zeros((1, 3), dtype=torch.long),
                "attention_mask": torch.ones((1, 3), dtype=torch.long),
                "offset_mapping": offsets,
            }

    class FakeModel:
        device = "cpu"

        def __call__(self, **kwargs):
            # 5 labels; token 1 (the real span) predicted as B-ING confidently.
            logits = torch.tensor(
                [[[10.0, 0, 0, 0, 0], [0, 10.0, 0, 0, 0], [10.0, 0, 0, 0, 0]]]
            )
            return type("Out", (), {"logits": logits})()

    monkeypatch.setattr(
        extract_bert, "_get_model_and_config", lambda: (FakeModel(), FakeTokenizer(), fake_config)
    )

    entities = extract_bert.predict_entities_bert_with_confidence(text)
    assert len(entities) == 1
    assert entities[0]["value"] == text
    assert entities[0]["type"] == "ING"
    assert 0.0 <= entities[0]["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# "unknown": spans the model labelled ING that no dictionary key covers
# ---------------------------------------------------------------------------

def test_unresolvable_ing_span_is_reported_as_unknown_and_resolved_ones_are_not(monkeypatch, label_config):
    monkeypatch.setattr(
        extract_bert,
        "predict_entities_bert_with_confidence",
        lambda text: [entity("มังคุด"), entity("ไก่")],
    )
    result = extract_bert.extract_bert("x")
    assert result["ingredients"] == ["chicken"]
    assert result["unknown"] == ["มังคุด"]


def test_unknown_is_deduplicated_stripped_and_ignores_health_spans(monkeypatch, label_config):
    monkeypatch.setattr(
        extract_bert,
        "predict_entities_bert_with_confidence",
        lambda text: [entity(" มังคุด "), entity("มังคุด"), entity("zzzqqq", ent_type="HEALTH")],
    )
    result = extract_bert.extract_bert("x")
    assert result["unknown"] == ["มังคุด"]      # once, stripped; the unresolved HEALTH span is not an ingredient
    assert result["health_tags"] == []


def test_a_negated_unknown_word_is_still_reported(monkeypatch, label_config):
    text = "ไม่เอามังคุด"
    monkeypatch.setattr(
        extract_bert, "predict_entities_bert_with_confidence", lambda t: [entity_in(text, "มังคุด")]
    )
    result = extract_bert.extract_bert(text)
    assert result["unknown"] == ["มังคุด"] and result["excluded"] == []


def test_the_keyword_fallback_never_reports_unknown(monkeypatch):
    """Unresolved keyword tokens are not known to be ingredients, so unknown stays []."""

    def _no_model():
        raise FileNotFoundError("no model here")

    monkeypatch.setattr(extract_bert, "_get_model_and_config", _no_model)
    monkeypatch.setattr(extract_bert, "_warned", set())
    result = extract_bert.extract_bert("มีมังคุดกับไก่")
    assert result["unknown"] == []
    assert result["ingredients"] == ["chicken"]


# ---------------------------------------------------------------------------
# predict_entities_llm(): a valid [] is "no entities"; unusable output raises
# so extract_bert() can degrade to the keyword path
# ---------------------------------------------------------------------------

class _FakeLLM:
    def __init__(self, text):
        self.text, self.calls = text, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text=self.text)])


def test_llm_valid_empty_list_means_no_entities(monkeypatch):
    monkeypatch.setattr(extract_bert, "_get_client", lambda: _FakeLLM("[]"))
    assert extract_bert.predict_entities_llm("x") == []


@pytest.mark.parametrize("bad", ["nope", "", "{}", '["ไก่"]'])
def test_llm_unusable_output_raises(monkeypatch, bad):
    monkeypatch.setattr(extract_bert, "_get_client", lambda: _FakeLLM(bad))
    with pytest.raises(extract_bert._BadLLMResponse):
        extract_bert.predict_entities_llm("ไก่")


def test_llm_call_uses_the_configured_extraction_model(monkeypatch):
    fake = _FakeLLM("[]")
    monkeypatch.setattr(extract_bert, "_get_client", lambda: fake)
    monkeypatch.setattr(web_config, "EXTRACTION_LLM_MODEL", "some-account-model-id")
    extract_bert.predict_entities_llm("x")
    assert fake.calls[0]["model"] == "some-account-model-id"


# ---------------------------------------------------------------------------
# bert_status() for /health: never loads anything
# ---------------------------------------------------------------------------

def test_bert_status_reports_unavailable_pending_and_loaded(monkeypatch, tmp_path):
    monkeypatch.setattr(extract_bert, "_model", None)
    monkeypatch.setattr(extract_bert, "_load_failure", None)

    monkeypatch.setattr(extract_bert, "_model_path", lambda: tmp_path / "missing")
    assert extract_bert.bert_status() == "unavailable"

    monkeypatch.setattr(extract_bert, "_model_path", lambda: tmp_path)
    (tmp_path / "label_config.json").write_text("{}", encoding="utf-8")
    assert extract_bert.bert_status() == "unavailable"          # config only, no weights (what git has)
    (tmp_path / "model.safetensors").write_bytes(b"")
    assert extract_bert.bert_status() == "pending"

    monkeypatch.setattr(extract_bert, "_load_failure", RuntimeError("corrupt"))
    assert extract_bert.bert_status() == "unavailable"

    monkeypatch.setattr(extract_bert, "_model", object())
    assert extract_bert.bert_status() == "loaded"


# ---------------------------------------------------------------------------
# Stray one-character "unknown" spans: a bare sentencepiece word-boundary "▁" token
# is given the offset of the first CHARACTER of the next word and is tagged B-ING.
# It used to decode into an extra entity ("ไ", "ห", "ถ"...) next to the real word.
# ---------------------------------------------------------------------------

O, B_ING, I_ING = 0, 1, 2


def install_fake_bert(monkeypatch, tokens):
    """
    Fake tokenizer + model that emit exactly `tokens` = [(start, end, label_id), ...] between
    <s> and </s> (offset (0, 0), like the real tokenizer). Every label gets a one-hot logit, so
    every confidence is ~1.0 and extract_bert() never falls back to the LLM.
    """
    import torch

    seq = [(0, 0, O), *tokens, (0, 0, O)]
    config = {
        "LABEL_LIST": ["O", "B-ING", "I-ING", "B-HEALTH", "I-HEALTH"],
        "id2label": {0: "O", 1: "B-ING", 2: "I-ING", 3: "B-HEALTH", 4: "I-HEALTH"},
        "confidence_threshold": THRESHOLD,
    }

    class FakeTokenizer:
        def __call__(self, text, return_tensors, truncation, max_length, return_offsets_mapping):
            return {
                "input_ids": torch.zeros((1, len(seq)), dtype=torch.long),
                "attention_mask": torch.ones((1, len(seq)), dtype=torch.long),
                "offset_mapping": torch.tensor([[[s, e] for s, e, _ in seq]]),
            }

    class FakeModel:
        device = "cpu"

        def __call__(self, **kwargs):
            logits = torch.zeros((1, len(seq), 5))
            for i, (_, _, label) in enumerate(seq):
                logits[0, i, label] = 10.0
            return type("Out", (), {"logits": logits})()

    monkeypatch.setattr(
        extract_bert, "_get_model_and_config", lambda: (FakeModel(), FakeTokenizer(), config)
    )


def test_a_bare_word_boundary_token_makes_no_stray_entity(monkeypatch):
    text = "ไก่ ไข่"
    install_fake_bert(
        monkeypatch, [(0, 1, B_ING), (0, 3, B_ING), (4, 5, B_ING), (4, 7, B_ING)]   # "▁" "ไก่" "▁" "ไข่"
    )
    entities = extract_bert.predict_entities_bert_with_confidence(text)
    assert [(e["start"], e["end"], e["value"]) for e in entities] == [(0, 3, "ไก่"), (4, 7, "ไข่")]

    result = extract_bert.extract_bert(text)
    assert result["ingredients"] == ["chicken", "egg"]
    assert result["unknown"] == []


def test_multi_token_words_still_merge_after_a_skipped_boundary_token(monkeypatch):
    text = "ไส้กรอก ถั่วแปบ"
    install_fake_bert(
        monkeypatch,
        [(0, 1, B_ING), (0, 7, B_ING), (8, 9, B_ING), (8, 12, B_ING), (12, 14, I_ING), (14, 15, I_ING)],
    )
    entities = extract_bert.predict_entities_bert_with_confidence(text)
    assert [e["value"] for e in entities] == ["ไส้กรอก", "ถั่วแปบ"]


def test_a_boundary_token_still_ends_the_previous_entity_before_an_i_tag(monkeypatch):
    """Same grouping as before the fix: an I- tag right after a boundary token does not extend the word before it."""
    text = "พริก ไทย"
    install_fake_bert(monkeypatch, [(0, 4, B_ING), (5, 6, B_ING), (5, 8, I_ING)])
    entities = extract_bert.predict_entities_bert_with_confidence(text)
    assert [e["value"] for e in entities] == ["พริก", "ไทย"]


def test_a_real_unknown_word_is_still_reported_alone(monkeypatch):
    text = "ไก่ มังคุด"
    install_fake_bert(monkeypatch, [(0, 3, B_ING), (4, 5, B_ING), (4, 10, B_ING)])   # "ไก่" "▁" "มังคุด"
    result = extract_bert.extract_bert(text)
    assert result["ingredients"] == ["chicken"]
    assert result["unknown"] == ["มังคุด"]


def test_a_token_that_merely_touches_the_next_one_is_not_skipped(monkeypatch):
    """Adjacent, non-overlapping tokens are ordinary pieces of a word, never dropped."""
    text = "ไก่ไข่"
    install_fake_bert(monkeypatch, [(0, 3, B_ING), (3, 6, B_ING)])
    entities = extract_bert.predict_entities_bert_with_confidence(text)
    assert [e["value"] for e in entities] == ["ไก่", "ไข่"]


# ---- the same inputs against the REAL local model (skipped where the git-ignored weights are absent)

needs_real_model = pytest.mark.skipif(
    extract_bert.bert_status() == "unavailable", reason="BERT weights are not on this machine"
)


@pytest.fixture
def real_bert():
    """Use the real model for one test, then put the module back the way the other tests expect it."""
    saved = (extract_bert._model, extract_bert._tokenizer, extract_bert._label_config, extract_bert._load_failure)
    yield
    (extract_bert._model, extract_bert._tokenizer, extract_bert._label_config, extract_bert._load_failure) = saved


def bert_only(text):
    """BERT decode + negation + resolution, no LLM/keyword fallback in between (asserts BERT is confident)."""
    _, _, config = extract_bert._get_model_and_config()
    entities = extract_bert.predict_entities_bert_with_confidence(text)
    assert entities and all(e["confidence"] >= config["confidence_threshold"] for e in entities), (
        "BERT is unsure about this input, so the app would use the LLM fallback instead"
    )
    return extract_bert._resolve_entities(extract_bert.apply_negation_cues(text, entities))


@needs_real_model
@pytest.mark.parametrize(
    "text",
    ["ไก่ ไข่", "ไส้กรอก ถั่วแปบ", "ไข่", "หมู", "ไม่เอาไก่ ใส่ไข่"],
)
def test_real_model_recognised_words_leave_no_unknown(real_bert, text):
    assert bert_only(text)["unknown"] == []


@needs_real_model
def test_real_model_reports_only_the_real_unknown_word(real_bert):
    assert bert_only("ไก่ มังคุด")["unknown"] == ["มังคุด"]
    negated = bert_only("ไม่ใช่ไก่ แต่เป็นมังคุด")
    assert negated["unknown"] == ["มังคุด"]
    assert negated["ingredients"] == ["chicken"]


@needs_real_model
def test_real_model_a_dish_name_the_dictionary_lacks_is_a_genuine_unknown(real_bert):
    """"ไข่เจียว" (omelette) is a dish name, not an ingredient key: it is reported, the ingredient next to it is kept."""
    result = bert_only("ไข่เจียว หมูสับ")
    assert result["ingredients"] == ["minced_meat"]
    assert result["unknown"] == ["ไข่เจียว"]


@needs_real_model
def test_real_model_no_case_ever_reports_a_one_character_unknown(real_bert):
    for text in ["ไก่ ไข่", "หมู", "ไก่ มังคุด", "ไข่เจียว หมูสับ", "ไส้กรอก ถั่วแปบ"]:
        assert all(len(word) > 1 for word in bert_only(text)["unknown"]), text


@needs_real_model
def test_real_model_punctuated_list_goes_through_extract_bert_without_a_stray_unknown(real_bert):
    """BERT tags the comma with low confidence here, so this input takes the fallback path (keyword extract, no key in tests)."""
    result = extract_bert.extract_bert("ไก่, ไข่ และ หมู")
    assert sorted(result["ingredients"]) == ["chicken", "egg", "pork"]
    assert result["unknown"] == []
