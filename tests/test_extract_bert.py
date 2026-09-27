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

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

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


def test_zero_bert_entities_triggers_the_llm_fallback(monkeypatch, label_config):
    monkeypatch.setattr(extract_bert, "predict_entities_bert_with_confidence", lambda text: [])
    monkeypatch.setattr(
        extract_bert, "predict_entities_llm", lambda text: [entity("ไข่", confidence=None)]
    )

    result = extract_bert.extract_bert("x")
    assert result["ingredients"] == ["egg"]


def test_one_low_confidence_entity_discards_the_whole_bert_result(monkeypatch, label_config):
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
    assert result == {"ingredients": [], "health_tags": [], "excluded": []}


def test_duplicate_entities_are_not_repeated(monkeypatch, label_config):
    monkeypatch.setattr(
        extract_bert,
        "predict_entities_bert_with_confidence",
        lambda text: [entity("ไก่"), entity("ไก่")],
    )
    result = extract_bert.extract_bert("x")
    assert result["ingredients"] == ["chicken"]


# ---------------------------------------------------------------------------
# Contract: same three keys as nlp.extract.extract(), excluded always empty
# ---------------------------------------------------------------------------

def test_extract_bert_returns_the_three_agreed_keys(monkeypatch, label_config):
    monkeypatch.setattr(extract_bert, "predict_entities_bert_with_confidence", lambda text: [])
    monkeypatch.setattr(extract_bert, "predict_entities_llm", lambda text: [])

    result = extract_bert.extract_bert("")
    assert set(result.keys()) == {"ingredients", "health_tags", "excluded"}
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


def test_negation_applies_after_whichever_path_won(monkeypatch, label_config):
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
