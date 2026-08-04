"""
Smoke + gate tests for the ultra-complex stress corpus.

Full performance (10k lines) is exercised by ``scripts/stress_test_report.py``;
CI runs with ``--skip-ultra`` equivalent for speed while still enforcing FPR=0
and high RAR on functional packages.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from stress_test_report import evaluate_corpus  # noqa: E402

CORPUS = ROOT / "tests" / "fixtures" / "stress" / "ultra_complex_corpus.json"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def stress_report(corpus: dict):
    # Skip only the 10k-line package in unit tests; keep 100/1000/safe volume.
    return evaluate_corpus(corpus, skip_ultra=True)


def test_corpus_has_fifty_packages(corpus: dict):
    assert len(corpus["cases"]) == 50
    by_axis = {a: 0 for a in range(1, 7)}
    for c in corpus["cases"]:
        by_axis[c["axis"]] += 1
    assert sum(by_axis.values()) == 50
    assert by_axis[4] >= 12  # FPR axis density


def test_fpr_is_zero(stress_report):
    assert stress_report.fpr_pass
    assert stress_report.false_positives == 0
    assert stress_report.fpr == 0.0


def test_rar_meets_release_gate(stress_report):
    assert stress_report.rar_pass
    assert stress_report.rar >= 0.98


def test_decision_approved(stress_report):
    assert stress_report.decision.startswith("APPROVED")


def test_axis4_safe_cases_untouched(corpus: dict):
    from arafix import repair_text

    for case in corpus["cases"]:
        if case["axis"] != 4:
            continue
        assert repair_text(case["input"]).text == case["input"]
