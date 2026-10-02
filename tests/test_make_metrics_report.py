"""
tests/test_make_metrics_report.py
=================================
Runs tools/make_metrics_report.py on the stored eval JSON and checks the key numbers and
sections. Offline and fast: no recommender, no network, no LLM.

Run with:
    pytest tests/test_make_metrics_report.py -v
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import make_metrics_report as mmr

REQUIRED_SECTIONS = (
    "## 1. How to read these numbers",
    "### The three variants",
    "## 2. Headline",
    "## 3. Per group",
    "## 4. Other metrics",
    "## 5. Known limitations",
    "## 6. How to quote these numbers",
)


@pytest.fixture(scope="module")
def report() -> str:
    return mmr.generate()


@pytest.fixture(scope="module")
def stored() -> dict:
    return json.loads(mmr.NEW_PATH.read_text(encoding="utf-8"))


def test_has_every_required_section(report):
    for heading in REQUIRED_SECTIONS:
        assert heading in report


def test_names_all_three_variants(report):
    for variant in mmr.VARIANTS:
        assert variant in report


def test_group_e_capped_and_uncapped_numbers_appear(report, stored):
    capped = stored["groups"]["E"]["variants"]["total_capped"]["lenient"]["precision_at_3"]
    uncapped = stored["groups"]["E"]["variants"]["total_uncapped"]["lenient"]["precision_at_3"]
    assert mmr._f(capped) == "0.445" and mmr._f(uncapped) == "0.944"
    assert "capped lenient P@3 0.445" in report
    assert "uncapped lenient P@3 0.944" in report


def test_overall_headline_numbers_appear(report, stored):
    overall = stored["overall"]["variants"]["total_capped"]["lenient"]
    assert mmr._f(overall["precision_at_3"]) == "0.767"
    assert "| total_capped | lenient (>= 3) | 0.767 | 0.767 |" in report
    assert "| total_uncapped | lenient (>= 3) | 0.967 | 0.967 |" in report


def test_states_old_and_new_are_identical(report):
    assert "**Old and new are identical**" in report


def test_explains_why_a_capped_dessert_cannot_pass(report, stored):
    c = stored["constants"]
    assert c["DESSERT_TOTAL_CAP"] < c["PASS_LENIENT"] < c["PASS_STRICT"]
    assert "fails capped lenient and capped strict" in report


def test_group_descriptors_do_not_invent_intent(report):
    assert "UNVERIFIED" in report
    assert "| E | E1, E2, E3, E4, E5, E6 |" in report


def test_output_is_deterministic(report):
    assert mmr.generate() == report
