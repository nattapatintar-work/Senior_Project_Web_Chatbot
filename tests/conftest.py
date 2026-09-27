"""
tests/conftest.py
=================
Shared safety net: no test may reach the real Anthropic API.

.env can hold a real ANTHROPIC_API_KEY, which would silently switch /confirm
from the keyword classifier to a paid network call, and would let
/extract_bert's fallback silently reach Claude Sonnet 5. This autouse
fixture blanks the key and makes both modules' _get_client() blow up if
anything reaches for it. Tests that exercise an LLM path override these
explicitly (tests/test_intent_llm.py, tests/test_extract_bert.py).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _no_real_anthropic_calls(monkeypatch):
    from api import intent, web_config
    from nlp import extract_bert

    def _forbidden():
        raise AssertionError("a test tried to build a real Anthropic client")

    monkeypatch.setattr(web_config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(intent, "_get_client", _forbidden)
    monkeypatch.setattr(extract_bert, "_get_client", _forbidden)
