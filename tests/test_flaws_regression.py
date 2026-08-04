"""
Regression suite for documented FLAW cases (tests/fixtures/flaws).

Phase B (02, 07), C (01, 03, 08), and D (04) must all pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arafix import PipelineConfig, diagnose, repair_blocks, repair_text
from arafix.diagnose import detect_mojibake
from arafix.normalize import (
    NormalizeConfig,
    strip_tatweel_among_presentation_forms,
)
from arafix.order import (
    normalize_page_ranges,
    relocate_sentence_punctuation,
    repair_inverted_ltr_parens,
    reverse_visual_line,
)
from arafix.types import Defect, Stage

FIXTURES = Path(__file__).parent / "fixtures" / "flaws" / "manifest.json"


def _load_cases() -> list[dict]:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return list(data["cases"])


def _by_id(fid: str) -> dict:
    for c in _load_cases():
        if c["id"] == fid:
            return c
    raise KeyError(fid)


# ── Phase C: page ranges / currency / sentence punct ───────────────────


class TestFlaw01PageRanges:
    def test_page_range_normalized_ascending(self):
        c = _by_id("FLAW_01")
        assert reverse_visual_line(c["input"]) == c["expected"]

    def test_normalize_helper_standalone(self):
        assert normalize_page_ranges("انظر (ص. 30-12)") == "انظر (ص. 12-30)"
        assert normalize_page_ranges("pp. 40-10") == "pp. 10-40"
        assert normalize_page_ranges("ص 5-5") == "ص 5-5"


class TestFlaw03CurrencyParens:
    def test_accounting_amount_with_parens(self):
        c = _by_id("FLAW_03")
        assert reverse_visual_line(c["input"]) == c["expected"]

    def test_inverted_paren_repair_helper(self):
        assert (
            repair_inverted_ltr_parens("الصافي )-USD 1,250.00(")
            == "الصافي (-USD 1,250.00)"
        )

    def test_percent_and_dollar_edges(self):
        assert reverse_visual_line("3.5% ماع") == "عام 3.5%"
        assert reverse_visual_line("$100 ماع") == "عام $100"


class TestFlaw08SentencePunct:
    def test_period_moves_after_year(self):
        c = _by_id("FLAW_08")
        out = reverse_visual_line(c["input"])
        assert out == c["expected"]
        assert out.endswith("2024.")
        assert not out.startswith(".")
        assert "عام" in out

    def test_relocate_helper(self):
        assert relocate_sentence_punctuation("في عام .2024") == "في عام 2024."
        assert relocate_sentence_punctuation("نهاية..") == "نهاية."


# ── Phase B: must pass ─────────────────────────────────────────────────


class TestFlaw02LamAlefLexicon:
    def test_repair_text_uses_core_lexicon(self):
        c = _by_id("FLAW_02")
        r = repair_text(c["input"])
        assert r.text == c["expected"]
        assert Stage.REPAIR_LAM_ALEF in r.stages_applied

    def test_repair_text_without_core_leaves_ambiguous(self):
        c = _by_id("FLAW_02")
        r = repair_text(c["input"], PipelineConfig(use_core_lexicon=False))
        assert r.text == c["input"]

    def test_repair_blocks_matches_repair_text(self):
        c = _by_id("FLAW_02")
        t = repair_text(c["input"]).text
        b = repair_blocks([c["input"]]).texts[0]
        assert t == b == c["expected"]

    def test_user_lexicon_without_core(self):
        c = _by_id("FLAW_02")
        r = repair_text(
            c["input"],
            PipelineConfig(use_core_lexicon=False, lexicon={"المجلات"}),
        )
        assert r.text == c["expected"]


class TestFlaw07TatweelInPf:
    def test_repair_text_recovers_lillah(self):
        c = _by_id("FLAW_07")
        r = repair_text(c["input"])
        assert r.text == c["expected"]

    def test_strip_helper_removes_pf_adjacent_tatweel(self):
        c = _by_id("FLAW_07")
        stripped = strip_tatweel_among_presentation_forms(c["input"])
        assert "\u0640" not in stripped
        assert repair_text(stripped).text == c["expected"]

    def test_pf_strip_alone_suffices_when_global_tatweel_off(self):
        c = _by_id("FLAW_07")
        cfg = PipelineConfig(
            normalize=NormalizeConfig(
                strip_tatweel=False,
                strip_tatweel_in_pf_runs=True,
            )
        )
        assert repair_text(c["input"], cfg).text == c["expected"]


class TestCoreLexiconModule:
    def test_lazy_load_and_size(self):
        from arafix.lexicon.core import (
            clear_core_lexicon_cache,
            core_lexicon_size,
            get_core_lexicon,
        )

        clear_core_lexicon_cache()
        lex = get_core_lexicon()
        assert "المجلات" in lex
        assert core_lexicon_size() >= 1000
        assert get_core_lexicon() is lex  # cached frozenset identity via lru


# ── Phase D: hybrid mojibake ───────────────────────────────────────────


class TestFlaw04HybridMojibake:
    def test_detected_as_mojibake(self):
        c = _by_id("FLAW_04")
        dg = diagnose(c["input"])
        assert Defect.MOJIBAKE in dg.defects

    def test_repair_recovers_arabic_prefix(self):
        c = _by_id("FLAW_04")
        r = repair_text(c["input"])
        assert "الم" in r.text
        assert "Customer Report" in r.text
        assert "Ø" not in r.text

    def test_pure_mojibake_still_works(self):
        ok, rec, _ = detect_mojibake("Ø§Ù„Ø³Ù„Ø§Ù…")
        assert ok and rec == "السلام"

    def test_arabic_plus_mojibake_island(self):
        ok, rec, _ = detect_mojibake("دراسة Ø§Ù„Ù…ØªÙˆØ³Ø· مقارنة")
        assert ok and rec == "دراسة المتوسط مقارنة"

    def test_cp1256_misread_recovered(self):
        truth = "مرحبا بالعالم"
        mis = truth.encode("cp1256").decode("latin-1")
        ok, rec, _ = detect_mojibake(mis)
        assert ok and rec == truth

    def test_latin_accents_not_false_positive(self):
        for s in ("café", "résumé", "naïve", "hello"):
            ok, rec, _ = detect_mojibake(s)
            assert not ok and rec is None


def test_manifest_covers_expected_ids():
    ids = {c["id"] for c in _load_cases()}
    assert ids >= {
        "FLAW_01",
        "FLAW_02",
        "FLAW_03",
        "FLAW_04",
        "FLAW_07",
        "FLAW_08",
    }
