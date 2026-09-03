"""
Regression on the iraq_constitution real paired corpus.

Corpus
------
``tests/fixtures/real_pdf_narrative/``
  - ``iraq_constitution_original.txt`` — manual gold reference (UTF-8, Arabic narrative)
  - ``iraq_constitution.pdf``          — the original downloaded PDF document

What we assert (and what we do not)
-----------------------------------
* **Gate (must hold):** Letters-only CER (ignoring spaces, digits, and punctuation)
  is near-perfect (< 2%).
* **Content/Full CER:** Stays below 18% (accounting for the PDF's inherent
  spacing noise).
* **Stages/Defects:** Diagnosis detects PRESENTATION_FORMS and VISUAL_ORDER,
  and applies NORMALIZE and REORDER.
* **Documented ceilings:** Headroom is provided for platforms and future minor spacing improvements.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arafix import (
    Defect,
    EvalConfig,
    Stage,
    evaluate_text,
    extract_pdf,
)
from arafix.evaluate import wer
from arafix.extractors import PyMuPDFExtractor

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "real_pdf_narrative"
PDF_PATH = FIXTURE_DIR / "iraq_constitution.pdf"
TRUTH_PATH = FIXTURE_DIR / "iraq_constitution_original.txt"

_FULL_CER_CEILING = 0.05
_CONTENT_CER_CEILING = 0.05
_LETTERS_ONLY_CER_CEILING = 0.02
_WER_CEILING = 0.16
_MIN_CONFIDENCE = 0.80

pytestmark = [
    pytest.mark.skipif(
        not PyMuPDFExtractor.available(),
        reason="PyMuPDF not installed (arafix[pdf])",
    ),
    pytest.mark.skipif(
        not PDF_PATH.is_file() or not TRUTH_PATH.is_file(),
        reason=f"fixture missing under {FIXTURE_DIR}",
    ),
]


# ── helpers ─────────────────────────────────────────────────────────────


def _clean_letters_only(s: str) -> str:
    """Strips all spaces, digits, punctuation, and diacritics to focus on pure letter recovery."""
    return "".join(c for c in s if c.isalnum() and c not in "0123456789٠١٢٣٤٥٦٧٨٩")


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def truth() -> str:
    return TRUTH_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def doc():
    return extract_pdf(str(PDF_PATH))


@pytest.fixture(scope="module")
def hyp(doc) -> str:
    return doc.text


# ── diagnosis & pipeline contracts ──────────────────────────────────────


class TestIraqDiagnosisOnRealExport:
    def test_detects_presentation_forms_and_visual_order(self, doc):
        defects = set()
        for page in doc.pages:
            defects.update(page.repair.diagnosis.defects)
        assert Defect.PRESENTATION_FORMS in defects
        assert Defect.VISUAL_ORDER in defects

    def test_applies_normalize_and_reorder(self, doc):
        stages = set()
        for page in doc.pages:
            stages.update(page.repair.stages_applied)
        assert Stage.NORMALIZE in stages
        assert Stage.REORDER in stages

    def test_document_confidence_above_floor(self, doc):
        assert doc.confidence >= _MIN_CONFIDENCE, (
            f"confidence={doc.confidence:.3f} < {_MIN_CONFIDENCE}"
        )


# ── quantitative gates (evaluate) ───────────────────────────────────────


class TestIraqMeasuredCeilings:
    def test_full_string_cer_has_a_ceiling(self, truth, hyp):
        rep = evaluate_text(truth, hyp, label="full", config=EvalConfig())
        assert rep.cer.rate < _FULL_CER_CEILING, (
            f"full CER={rep.cer.rate:.2%} ≥ {_FULL_CER_CEILING:.0%}"
        )

    def test_content_string_cer_has_a_ceiling(self, truth, hyp):
        cfg = EvalConfig(
            collapse_whitespace=True,
            ignore_diacritics=True,
            ignore_punctuation=False,
            ignore_orthographic_variants=False,
        )
        rep = evaluate_text(truth, hyp, label="content", config=cfg)
        assert rep.cer.rate < _CONTENT_CER_CEILING, (
            f"content CER={rep.cer.rate:.2%} ≥ {_CONTENT_CER_CEILING:.0%}"
        )

    def test_letters_only_cer_near_perfect(self, truth, hyp):
        """Pure letter recovery and spelling correctness must be exceptionally high."""
        clean_truth = _clean_letters_only(truth)
        clean_hyp = _clean_letters_only(hyp)
        rep = evaluate_text(clean_truth, clean_hyp, label="letters_only")
        assert rep.cer.rate < _LETTERS_ONLY_CER_CEILING, (
            f"letters-only CER={rep.cer.rate:.2%} ≥ {_LETTERS_ONLY_CER_CEILING:.1%}"
        )

    def test_wer_has_a_ceiling(self, truth, hyp):
        rate = wer(truth, hyp).rate
        assert rate < _WER_CEILING, (
            f"full WER={rate:.2%} ≥ {_WER_CEILING:.0%}"
        )


# ── linguistic layers ───────────────────────────────────────────────────


class TestIraqLettersAndWords:
    def test_key_sections_and_phrases_survive(self, truth, hyp):
        # Test authentic phrases with real word boundaries and spacing
        for phrase in (
            "حقوق الإنسان في الدستور العراقي",
            "أنواع الحقوق",
            "الحقوق الاقتصادية والاجتماعية والثقافية",
            "الحريات العامة",
            "قواعد العدالة الاجتماعية",
            "أو الاجتماعي",
            "١- الحقوق",
            "٢: ",
            "١٤-١٥-١٦",
        ):
            assert phrase in hyp, f"missing key phrase with spaces: {phrase!r}"

    def test_constitutional_years_survive(self, hyp):
        # Iraqi constitution year 2005 (in Eastern Arabic numerals: ٢٠٠٥)
        assert "٢٠٠٥" in hyp, "Constitutional year ٢٠٠٥ was lost or altered"
