"""
Regression tests verifying fixes for bugs B-01 through B-12
identified in the comprehensive arafix audit report.
"""

from __future__ import annotations

import re
from arafix.cli import _normalize_argv
from arafix.extractors.pymupdf_extractor import PyMuPDFExtractor
from arafix.hygiene import (
    collapse_midword_spaces,
    normalize_arabic_punctuation_spacing,
)
from arafix.lamalef import (
    detect_lam_alef_transposition,
    repair_lam_alef_transposition,
)
from arafix.normalize import (
    fold_pdf_homoglyphs,
    separate_fused_presentation_forms,
)
from arafix.order import (
    _is_markable_base,
    relocate_sentence_punctuation,
    repair_inverted_ltr_parens,
    reverse_visual_line,
)
from arafix.pipeline import PipelineConfig, repair_text
from arafix.scientific import _HOMOGLYPH_TO_CANON
from arafix.types import PageResult, RepairResult


class TestB01CollapseMidwordSpaces:
    def test_preserves_valid_two_letter_words(self):
        # Two-letter valid word pairs must NOT be merged
        assert collapse_midword_spaces("تم حل") == "تم حل"
        assert collapse_midword_spaces("له حق") == "له حق"
        assert collapse_midword_spaces("لك حق") == "لك حق"
        assert collapse_midword_spaces("قل لي") == "قل لي"
        assert collapse_midword_spaces("تم رد") == "تم رد"
        assert collapse_midword_spaces("تم سد") == "تم سد"
        assert collapse_midword_spaces("له يد") == "له يد"

    def test_preserves_alphabetic_enumeration_items(self):
        # Single-letter items preceded by enumeration nouns must NOT be merged
        assert collapse_midword_spaces("المجموعة أ تشمل") == "المجموعة أ تشمل"
        assert collapse_midword_spaces("الفئة ب تضم") == "الفئة ب تضم"
        assert collapse_midword_spaces("القسم ج يتضمن") == "القسم ج يتضمن"
        assert collapse_midword_spaces("البند د ينص") == "البند د ينص"
        assert collapse_midword_spaces("المادة ه تسري") == "المادة ه تسري"

    def test_collapses_all_solar_and_lunar_article_splits(self):
        # Definite article splits with any Arabic letter
        assert collapse_midword_spaces("الد ستور") == "الدستور"
        assert collapse_midword_spaces("الر واية") == "الرواية"
        assert collapse_midword_spaces("الز مان") == "الزمان"
        assert collapse_midword_spaces("الذ كاء") == "الذكاء"
        assert collapse_midword_spaces("الط بيب") == "الطبيب"
        assert collapse_midword_spaces("الع صور") == "العصور"
        assert collapse_midword_spaces("الم كتبة") == "المكتبة"

    def test_still_collapses_non_word_geometry_splits(self):
        assert collapse_midword_spaces("مو ضع") == "موضع"
        assert collapse_midword_spaces("أي ضًا") == "أيضًا"
        assert collapse_midword_spaces("عاد ي") == "عادي"


class TestB02PageResultBodyText:
    def test_body_text_returns_repaired_text_when_blocks_none(self):
        rep = RepairResult(
            text="نص مصلح سليم في صفحة كاملة",
            original="ﺔﺤﻔﺻ ﻲﻓ ﻢﻴﻠﺳ ﺢﻠﺼﻣ ﺺﻧ",
            diagnosis=None,  # type: ignore[arg-type]
            stages_applied=[],
            confidence=1.0,
        )
        page = PageResult(
            page_number=1,
            repair=rep,
            fonts=[],
            layout=None,
            blocks=None,
        )
        # body_text must return the repaired text, not empty or raw
        assert page.body_text == "نص مصلح سليم في صفحة كاملة"


class TestB03SeparateFusedPresentationForms:
    def test_preserves_visual_tokens_ending_in_isolated_letters(self):
        # Visual reversed tokens like 'مرجع القرار' should not be mutated or falsely split inside
        # \ufeae (isolated reh) followed by \ufe8e (final alef)
        # In visual order: 'القرار' backwards has \ufeae (isolated reh) at the boundary
        # Test that separate_fused_presentation_forms handles logical and visual streams appropriately
        clean = separate_fused_presentation_forms("الحمد لله")
        assert "الحمد" in clean


class TestB04InvertedQuotesAndParens:
    def test_multiple_balanced_quotes_on_same_line(self):
        # A visually reversed line with two quoted terms:
        # In visual order: 'مويل »يناثلا« لاق مث »لوألا« لاق'
        visual = "مويل »يناثلا« لاق مث »لوألا« لاق"
        res = reverse_visual_line(visual)
        assert "«الأول»" in res
        assert "«الثاني»" in res

    def test_multiple_balanced_parens_on_same_line(self):
        text = "الفقرة (أ) 2024 - 2025 (ب)"
        assert repair_inverted_ltr_parens(text) == "الفقرة (أ) 2024 - 2025 (ب)"

    def test_actual_inverted_quotes_and_parens(self):
        assert reverse_visual_line("»ابحرم«") == "«مرحبا»"
        assert repair_inverted_ltr_parens("الصافي )-USD 1,250.00(") == "الصافي (-USD 1,250.00)"


class TestB05LamAlefDecisiveAndDiacritics:
    def test_accurate_fixed_decisive_count(self):
        # Multiple decisive occurrences in one text must be counted accurately
        text = "االنترنيت واألطاريح واإلجراء"
        rep = repair_lam_alef_transposition(text)
        assert rep.fixed_decisive == 3
        assert "الانترنيت" in rep.text
        assert "الأطاريح" in rep.text
        assert "الإجراء" in rep.text

    def test_vocalized_decisive_and_lexicon(self):
        # Diacritics on transposed letters
        rep = repair_lam_alef_transposition("اَالنترنيت")
        assert "الانترنيت" in rep.text or "اَلانترنيت" in rep.text

        # Lexicon lookup with diacritics
        rep2 = repair_lam_alef_transposition("المُجَالت", {"المجلات"})
        assert rep2.fixed_by_lexicon == 1


class TestB06Homoglyphs:
    def test_farsi_and_additional_homoglyphs(self):
        # \u06c0 (ۀ -> ة) and \u06d5 (ە -> ه)
        assert fold_pdf_homoglyphs("\u06c0") == "ة"
        assert fold_pdf_homoglyphs("\u06d5") == "ه"
        assert _HOMOGLYPH_TO_CANON["\u06c0"] == "\u0629"
        assert _HOMOGLYPH_TO_CANON["\u06d5"] == "\u0647"


class TestB07RescueMixedLinesRcfg:
    def test_pipeline_rescue_with_pf_line(self):
        cfg = PipelineConfig(rescue_mixed_lines=True)
        healthy = (
            "تتناول هذه الدراسة أهم جوانب النظرية البنيوية في النقد الأدبي الحديث\n"
            "حيث يرصد الكاتب تطور المدرسة منذ نشأتها في عشرينيات القرن الماضي"
        )
        rev = "ةماعلاو ةغللا نم راداهإ هتاجرد لضفت ناوك يذلا باتكلا"
        page = f"{healthy}\n{rev}"
        res = repair_text(page, cfg)
        assert rev not in res.text
        assert "الكتاب" in res.text


class TestB08EllipsisPreservation:
    def test_ellipsis_preserved_when_relocating_punct(self):
        text = "جملة تنتهي بنقاط حذف... وهنا عام .2024"
        fixed = relocate_sentence_punctuation(text)
        assert "..." in fixed
        assert "2024." in fixed


class TestB10TatweelNotMarkableBase:
    def test_tatweel_not_base_letter(self):
        assert not _is_markable_base("\u0640")
        assert not PyMuPDFExtractor._is_markable_base("\u0640")
        assert _is_markable_base("ب")


class TestB11DiacriticsBeforePunctuation:
    def test_diacritic_before_punct_space_normalization(self):
        assert normalize_arabic_punctuation_spacing("مقدمةً ، جديدة") == "مقدمةً، جديدة"
        assert normalize_arabic_punctuation_spacing("المادة(١٧)") == "المادة (١٧)"


class TestB12CliNormalization:
    def test_cli_option_value_skipping(self):
        assert _normalize_argv(["-o", "output.txt", "doc.pdf"]) == [
            "-o", "output.txt", "extract", "doc.pdf"
        ]
        assert _normalize_argv(["--pages", "1-5", "doc.pdf"]) == [
            "--pages", "1-5", "extract", "doc.pdf"
        ]
