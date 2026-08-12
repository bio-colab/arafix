"""
Regression on a **real** paired corpus (not the synthetic generator).

Corpus
------
``tests/fixtures/real_pdf_narrative/``
  - ``original.txt`` — authoring source (UTF-8, vocalized Arabic narrative)
  - ``file.pdf``     — the same document saved as PDF by the user

Why this exists
---------------
``test_integration_pdf`` proves the repair ladder on a PDF *we* broke with
``make_broken_pdf``. That is necessary but half the argument (generator
inverse of repairer). This module is the other half: a file the library did
not author, with a ground-truth text file.

What we assert (and what we do not)
-----------------------------------
* **Gate (must hold):** letter content after ignoring diacritics and folding
  PDF font lookalikes (Farsi Yeh / Heh Doachashmee) stays near-perfect; arafix
  beats raw MuPDF ``get_text()``; diagnosis + stages fire; key phrases and
  years survive; diacritic *inventory* and semantic punctuation counts hold.
* **Documented ceilings:** full-string CER is still high because harakat are
  preserved but often mis-attached — that is tracked, not papered over.
* **Aspirational (xfail):** exact vocalization, LTR islands (``13-7``, ship
  name), decorative underscores absent from the PDF text layer.

Every test name states a **decision**. Break one → you know which contract
regressed and why it was written.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
from arafix import (
    Defect,
    EvalConfig,
    Stage,
    evaluate_text,
    extract_pdf,
)
from arafix.extractors import PyMuPDFExtractor

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "real_pdf_narrative"
PDF_PATH = FIXTURE_DIR / "file.pdf"
TRUTH_PATH = FIXTURE_DIR / "original.txt"

# Measured on this corpus (arafix 0.9.0 + pymupdf geometric).
# Ceilings include modest headroom so platform float noise does not flake CI;
# they are still tight enough to catch real regressions.
# After P0+P1: full CER should sit near residual layout/LTR noise only.
_FULL_CER_CEILING = 0.03
_NO_DIAC_CER_CEILING = 0.03
_CONTENT_CER_CEILING = 0.025
_CONTENT_WER_CEILING = 0.02
_MIN_CONFIDENCE = 0.90

# Arabic tashkeel used in this corpus (and common Mn harakat).
_TASHKEEL = set(
    "\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0653\u0654\u0655\u0670"
)

# PDF fonts often encode Arabic yeh/heh as Farsi / Doachashmee codepoints.
# That is a ToUnicode/font choice, not a repair failure — fold only for the
# *letter-content* gate so CER measures Arabic recovery, not codepoint vanity.
_PDF_HOMOGLYPHS = str.maketrans(
    {
        "\u06cc": "\u064a",  # Farsi Yeh → Arabic Yeh
        "\u06cd": "\u064a",
        "\u0649": "\u064a",  # Alef Maksura → Yeh for loose content match
        "\u06be": "\u0647",  # Heh Doachashmee → Heh
        "\u06c1": "\u0647",
        "\u06a9": "\u0643",  # Keheh → Kaf
        "\u06c3": "\u0629",  # Teh Marbuta goal → Teh Marbuta
    }
)

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


def _fold_pdf_homoglyphs(text: str) -> str:
    return text.translate(_PDF_HOMOGLYPHS)


def _only_tashkeel(text: str) -> str:
    return "".join(c for c in text if c in _TASHKEEL)


def _strip_tashkeel(text: str) -> str:
    return "".join(c for c in text if c not in _TASHKEEL)


def _content_cfg() -> EvalConfig:
    """Letter / word recovery: ignore harakat, keep punctuation, collapse WS."""
    return EvalConfig(
        collapse_whitespace=True,
        ignore_diacritics=True,
        ignore_punctuation=False,
        ignore_orthographic_variants=False,
    )


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def truth() -> str:
    # utf-8-sig: original.txt may carry a BOM from Windows editors.
    return TRUTH_PATH.read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def doc():
    return extract_pdf(str(PDF_PATH))


@pytest.fixture(scope="module")
def hyp(doc) -> str:
    return doc.text


@pytest.fixture(scope="module")
def raw_mupdf_text() -> str:
    import fitz

    pages = fitz.open(str(PDF_PATH))
    return "\n".join(page.get_text() for page in pages)


# ── diagnosis & pipeline contracts ──────────────────────────────────────


class TestDiagnosisOnRealExport:
    def test_detects_presentation_forms_and_visual_order(self, doc):
        """
        Decision: a Word→PDF Arabic export of this kind is *not* healthy
        text — stages 1–2 must engage. Silent pass-through would be a bug.
        """
        defects = set()
        for page in doc.pages:
            defects.update(page.repair.diagnosis.defects)
        assert Defect.PRESENTATION_FORMS in defects
        assert Defect.VISUAL_ORDER in defects

    def test_applies_normalize_and_reorder(self, doc):
        """Decision: evidence without action is theatre — stages must run."""
        stages = set()
        for page in doc.pages:
            stages.update(page.repair.stages_applied)
        assert Stage.NORMALIZE in stages or Stage.DIAGNOSE in stages
        assert Stage.REORDER in stages

    def test_document_confidence_above_floor(self, doc):
        """
        Decision: this corpus is clean native text with strong order signals.
        Confidence below the floor means diagnosis or scoring regressed.
        """
        assert doc.confidence >= _MIN_CONFIDENCE, (
            f"confidence={doc.confidence:.3f} < {_MIN_CONFIDENCE}"
        )
        assert all(p.repair.confidence >= _MIN_CONFIDENCE for p in doc.pages)


# ── quantitative gates (evaluate) ───────────────────────────────────────


class TestMeasuredCeilings:
    def test_full_string_cer_has_a_ceiling(self, truth, hyp):
        """
        Full CER includes mis-attached harakat — high, but bounded.

        If this blows past the ceiling, something worse than known harakat
        drift landed (order collapse, mass deletions, etc.).
        """
        rep = evaluate_text(truth, hyp, label="full", config=EvalConfig())
        assert rep.cer.rate < _FULL_CER_CEILING, (
            f"full CER={rep.cer.rate:.2%} ≥ {_FULL_CER_CEILING:.0%}; "
            f"WER={rep.wer.rate:.2%}; worst={rep.worst_lines[:2]!r}"
        )

    def test_no_diacritic_cer_ceiling(self, truth, hyp):
        """
        Decision: ignoring harakat isolates letter+punct recovery.
        Homoglyphs (ی/ھ) still count here — so this is stricter than content.
        """
        rep = evaluate_text(
            truth, hyp, label="no_diac", config=EvalConfig(ignore_diacritics=True)
        )
        assert rep.cer.rate < _NO_DIAC_CER_CEILING, (
            f"no-diac CER={rep.cer.rate:.2%} ≥ {_NO_DIAC_CER_CEILING:.0%}"
        )

    def test_letter_content_cer_and_wer_near_perfect(self, truth, hyp):
        """
        **Primary quality gate for this corpus.**

        Fold PDF font lookalikes, drop harakat, collapse whitespace — then
        letter/word stream must match the source within tight bounds.
        Measured baseline ≈ CER 1.2% / WER 0.6% (underscores + LTR islands).
        """
        rep = evaluate_text(
            _fold_pdf_homoglyphs(truth),
            _fold_pdf_homoglyphs(hyp),
            label="content",
            config=_content_cfg(),
        )
        assert rep.cer.rate < _CONTENT_CER_CEILING, (
            f"content CER={rep.cer.rate:.2%} ≥ {_CONTENT_CER_CEILING:.1%}; "
            f"worst={rep.worst_lines[:3]!r}"
        )
        assert rep.wer.rate < _CONTENT_WER_CEILING, (
            f"content WER={rep.wer.rate:.2%} ≥ {_CONTENT_WER_CEILING:.1%}"
        )

    def test_beats_raw_mupdf_get_text_on_letter_content(
        self, truth, hyp, raw_mupdf_text
    ):
        """
        Decision: geometric extract + repair must beat the engine's default
        bidi dump on the same file — otherwise we should not be default.
        """
        cfg = _content_cfg()
        ara = evaluate_text(
            _fold_pdf_homoglyphs(truth),
            _fold_pdf_homoglyphs(hyp),
            label="arafix",
            config=cfg,
        )
        raw = evaluate_text(
            _fold_pdf_homoglyphs(truth),
            _fold_pdf_homoglyphs(raw_mupdf_text),
            label="raw_mupdf",
            config=cfg,
        )
        assert ara.cer.rate < raw.cer.rate, (
            f"arafix CER={ara.cer.rate:.2%} not better than raw={raw.cer.rate:.2%}"
        )
        # Large gap on this file historically (~1% vs ~9% CER; WER ~0.6% vs ~22%).
        assert ara.cer.rate * 3 < raw.cer.rate or ara.wer.rate * 5 < raw.wer.rate, (
            f"expected large gap; arafix CER/WER={ara.cer.rate:.2%}/{ara.wer.rate:.2%} "
            f"raw={raw.cer.rate:.2%}/{raw.wer.rate:.2%}"
        )


# ── linguistic layers ───────────────────────────────────────────────────


class TestLettersAndWords:
    def test_section_headers_and_title_survive(self, truth, hyp):
        """Decision: discourse landmarks must be recoverable unvocalized."""
        folded_hyp = _fold_pdf_homoglyphs(_strip_tashkeel(hyp))
        for phrase in (
            "هل خسرت إيران حرب الرواية؟",
            "غزة",
            "سوريا",
            "لبنان",
            "العراق",
            "إيران نفسها",
            "فما جوابك أنت؟",
            "الأسد الصاعد",
        ):
            needle = _fold_pdf_homoglyphs(_strip_tashkeel(phrase))
            assert needle in folded_hyp, f"missing content phrase: {phrase!r}"

    def test_years_and_digit_count_preserved(self, truth, hyp):
        """Decision: LTR protection must at least keep calendar years intact."""
        for year in ("2023", "2024", "2025", "2026"):
            assert year in hyp, f"year lost: {year}"
            assert year[::-1] not in re.findall(r"\d{4}", hyp) or year in hyp
        assert sum(c.isdigit() for c in hyp) == sum(c.isdigit() for c in truth)

    def test_word_multiset_overlap_after_fold(self, truth, hyp):
        """
        Decision: nearly every source word must appear (bag-of-words), even if
        a few LTR tokens shuffle. Catches mass word loss that CER can dilute.
        """
        def bag(s: str) -> Counter:
            return Counter(
                _fold_pdf_homoglyphs(_strip_tashkeel(w))
                for w in s.split()
            )

        ref_b, hyp_b = bag(truth), bag(hyp)
        common = sum((ref_b & hyp_b).values())
        overlap = common / max(sum(ref_b.values()), 1)
        assert overlap >= 0.98, f"word multiset overlap={overlap:.2%} < 98%"


class TestDiacritics:
    def test_tashkeel_inventory_is_preserved(self, truth, hyp):
        """
        Decision: we must not drop or invent harakat on this native PDF.
        """
        assert Counter(_only_tashkeel(truth)) == Counter(_only_tashkeel(hyp)), (
            f"ref={Counter(_only_tashkeel(truth))} hyp={Counter(_only_tashkeel(hyp))}"
        )

    def test_no_leading_tashkeel_words(self, truth, hyp):
        """
        P0 grapheme protection: after visual→logical reorder, no word may
        start with a haraka (source has zero; extract must match).
        """
        def leading_tashkeel_words(s: str) -> int:
            return sum(1 for w in s.split() if w and w[0] in _TASHKEEL)

        assert leading_tashkeel_words(truth) == 0
        n = leading_tashkeel_words(hyp)
        assert n == 0, f"{n} words still start with a haraka (e.g. َحرب)"

    def test_vocalized_words_mostly_match_after_homoglyph_fold(self, truth, hyp):
        """
        P0: among word pairs that align after folding PDF lookalikes and that
        carry tashkeel in the source, most must match exactly (marks on the
        correct base). Homoglyph-only differences are folded first.
        """
        from difflib import SequenceMatcher

        rw = [_fold_pdf_homoglyphs(_strip_tashkeel(w)) for w in truth.split()]
        hw = [_fold_pdf_homoglyphs(_strip_tashkeel(w)) for w in hyp.split()]
        rf, hf = truth.split(), hyp.split()
        sm = SequenceMatcher(None, rw, hw, autojunk=False)
        total = exact = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                continue
            for ii, jj in zip(range(i1, i2), range(j1, j2)):
                if not any(c in _TASHKEEL for c in rf[ii]):
                    continue
                total += 1
                if _fold_pdf_homoglyphs(rf[ii]) == _fold_pdf_homoglyphs(hf[jj]):
                    exact += 1
        assert total >= 50, "corpus should have many vocalized words"
        rate = exact / total
        assert rate >= 0.85, (
            f"vocalized word match={rate:.1%} ({exact}/{total}) < 85% — "
            f"grapheme protection regressed"
        )

    def test_full_cer_after_homoglyph_fold_under_ceiling(self, truth, hyp):
        """
        With diacritic attachment fixed, remaining full-string error is mostly
        PDF font lookalikes + LTR islands + missing underscores.
        """
        rep = evaluate_text(
            _fold_pdf_homoglyphs(truth),
            _fold_pdf_homoglyphs(hyp),
            label="full_fold",
            config=EvalConfig(),
        )
        assert rep.cer.rate < 0.05, (
            f"full CER after fold={rep.cer.rate:.2%} ≥ 5%; worst={rep.worst_lines[:2]!r}"
        )


class TestPunctuationAndWhitespace:
    def test_semantic_punctuation_counts_match(self, truth, hyp):
        """
        Decision: Arabic comma, period, question mark, quotes, colons, etc.
        must survive. Decorative underscores are *not* in the PDF layer.
        """
        semantic = "،.؟\"؛:—/()…–"
        for mark in semantic:
            assert truth.count(mark) == hyp.count(mark), (
                f"punct {mark!r}: truth={truth.count(mark)} hyp={hyp.count(mark)}"
            )

    def test_section_rule_underscores_absent_from_pdf_layer(
        self, truth, hyp, raw_mupdf_text
    ):
        """
        Decision: do not invent layout chrome. Underscores exist in the .txt
        only; raw extract also lacks them — arafix must not hallucinate.
        """
        assert "_" in truth
        assert "_" not in raw_mupdf_text
        assert "_" not in hyp

    def test_hyp_is_not_a_newline_explosion(self, hyp, raw_mupdf_text):
        """
        Decision: geometric join should produce fewer line breaks than the
        raw visual dump (soft wraps), without claiming .txt paragraph fidelity.
        """
        assert hyp.count("\n") < raw_mupdf_text.count("\n")


# ── aspirational / known gaps (xfail until fixed) ───────────────────────


class TestP1HomoglyphsAndLtr:
    """P1 hard gates: homoglyph fold + LTR islands on the real corpus."""

    def test_output_uses_standard_arabic_yeh_and_heh(self, hyp):
        assert "\u06cc" not in hyp  # Farsi Yeh
        assert "\u06be" not in hyp  # Heh Doachashmee
        assert hyp.count("ي") + hyp.count("ه") > 100

    def test_date_order_13_7(self, hyp):
        assert "13-7" in hyp
        assert "7-13" not in hyp

    def test_ship_name_ltr_order(self, hyp):
        flat = re.sub(r"\s+", " ", hyp)
        assert "M/V Ever" in flat
        # Lovely may soft-wrap to the next line; require contiguous phrase if present
        if "Lovely" in flat:
            assert "M/V Ever Lovely" in flat or "M/V Ever Lovely" in flat.replace(
                "\n", " "
            )

    def test_full_cer_under_three_percent(self, truth, hyp):
        """Homoglyph fold in output should land full CER near the content gate."""
        rep = evaluate_text(truth, hyp, label="full", config=EvalConfig())
        assert rep.cer.rate < 0.03, (
            f"full CER={rep.cer.rate:.2%} ≥ 3%; worst={rep.worst_lines[:2]!r}"
        )
