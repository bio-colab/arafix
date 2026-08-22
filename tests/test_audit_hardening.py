"""
انحدارات الفحص الجراحي (أغسطس ٢٠٢٦) — كل حالة هنا كانت تُفشل أو تُبطئ
قبيل الإصلاح، ومُثبَتة الآن بقياسٍ لا بالحدس.

المرجع: تقرير الفحص الداخلي قبل الإصدار ١.٠.٢.
"""

from __future__ import annotations

import time

import pytest

from arafix import diagnose
from arafix.cmap import decode_glyph_name
from arafix.hygiene import collapse_midword_spaces
from arafix.lamalef import repair_lam_alef_transposition
from arafix.order import grapheme_clusters, reverse_visual_line
from arafix.unicode_tables import is_presentation_form

# ---------------------------------------------------------------------------
# الأداء: التربيعية المُقاسة سابقاً ×4 لكل مضاعفة حجم
# ---------------------------------------------------------------------------

def _timed_ms(fn, text: str) -> float:
    t0 = time.perf_counter()
    fn(text)
    return (time.perf_counter() - t0) * 1000.0


class TestQuadraticHotPaths:
    """كانت 19.9s و4.4s عند n=20k؛ يجب أن تبقى خطية (أقل من ثانية)."""

    @pytest.mark.parametrize("n", [20_000])
    def test_ta_marbuta_collapse_is_linear(self, n):
        text = "ب" * n + " " + "ب" + "ً" * n
        assert _timed_ms(collapse_midword_spaces, text) < 1000.0

    @pytest.mark.parametrize("n", [20_000])
    def test_ltr_run_rescan_is_linear(self, n):
        text = "1 " * n + "%" * n + "ا"
        assert _timed_ms(reverse_visual_line, text) < 1000.0

    def test_outputs_unchanged_by_speed_fixes(self):
        # نفس مخرجات ما قبل الإصلاح — السرعة لا تُغيّر الدلالة.
        assert collapse_midword_spaces("مقدم ة") == "مقدمة"
        assert collapse_midword_spaces("صلّى الله") == "صلّى الله"
        assert reverse_visual_line("(140-125 .ص) ثحبلا عجرم") == (
            "مرجع البحث (ص. 125-140)"
        )
        assert reverse_visual_line("%5.3") == "3.5%"
        assert reverse_visual_line("3.5%") == "3.5%"


# ---------------------------------------------------------------------------
# lam-alef: الرسم القرآني كان يُفشل بصمت
# ---------------------------------------------------------------------------

class TestLamAlefWordSpan:
    def test_wasla_word_is_whole(self):
        # U+0671 ألف الوصل كانت تقطّع الكلمة فيفشل إصلاح المعجم.
        r = repair_lam_alef_transposition("ٱلمجالت", {"ٱلمجلات"})
        assert r.fixed_by_lexicon == 1
        assert r.suspects_left == 0

    def test_superscript_alef_stays_in_word(self):
        from arafix.lamalef import _WORD

        assert _WORD.findall("علَىٰ") == ["علَىٰ"]


# ---------------------------------------------------------------------------
# cmap: البدائل المعزولة والسلاسل المركّبة
# ---------------------------------------------------------------------------

class TestCmapHardening:
    def test_lone_surrogate_name_is_dropped_not_emitted(self):
        # uniD800 كانت تعود بمحرف بديل معزول يكسر UTF-8 لاحقاً.
        assert decode_glyph_name("uniD800") is None

    def test_beyond_unicode_ceiling_is_dropped(self):
        assert decode_glyph_name("u110000") is None
        assert decode_glyph_name("uniFFFF") == "\uffff"  # السقف نفسه مقبول

    def test_valid_names_still_decode(self):
        from arafix.cmap import decode_glyph_name as d

        assert d("uni0645") == "م"
        assert d("uni06450631") == "مر"
        assert d("cid1234") is None


# ---------------------------------------------------------------------------
# U+FEFF ليس شكلاً رسومياً عربياً
# ---------------------------------------------------------------------------

class TestFeffNotPresentationForm:
    def test_feff_excluded(self):
        assert not is_presentation_form("\ufeff")

    def test_bom_run_diagnosis_has_no_spurious_defect(self):
        dg = diagnose("\ufeff" * 10)
        names = [d.value for d in dg.defects]
        assert "presentation_forms" not in names


# ---------------------------------------------------------------------------
# الحركات المركّبة (U+0653–U+0655) تلزم حرفها كغيرها
# ---------------------------------------------------------------------------

class TestDecomposedHamzaMarks:
    def test_space_before_hamza_above_glues(self):
        # بر ٔزق: المسافة كانت تبقى رغم أن U+0654 علامة تركيب.
        assert collapse_midword_spaces("بر \u0654زق") == "برٔزق"

    def test_maddah_above_treated_as_mark(self):
        assert collapse_midword_spaces("بر \u0653زق") == "برٓزق"


# ---------------------------------------------------------------------------
# عناقيد الرسم: الاتفاقية العنقودية موثَّقة ومثبَّتة
# ---------------------------------------------------------------------------

class TestClusterConvention:
    def test_internal_mark_between_bases_binds_backward(self):
        # 'لَب' تحت الاتفاقية العنقودية هي انعكاسُ 'بلَ' المنطقية —
        # الغموض بين الاتفاقيتين موثَّق في docstring الدالة، والربط
        # الخلفي هو الملتزَم به حتى لا نُفسد مصادر الاتفاقية العنقودية.
        assert grapheme_clusters("لَب") == ["لَ", "ب"]
        assert reverse_visual_line("لبَ") == "بَل"

    def test_pending_mark_after_space_still_forward_binds(self):
        # المسافة وحدةٌ محفوظة؛ العلامة تلزم الباء التالية لا الفراغ.
        assert reverse_visual_line(" \u064e\u0628") == "بَ "


# ---------------------------------------------------------------------------
# CLI: حواجز الاستعمال الخاطئ
# ---------------------------------------------------------------------------

class TestCliGuards:
    def _parser_main(self, argv, monkeypatch, tmp_path):
        import sys

        from arafix import cli

        monkeypatch.setattr(sys, "argv", ["arafix", *argv])
        return cli

    def test_negative_pages_rejected(self, capsys):
        from arafix.cli import build_parser

        with pytest.raises(SystemExit):
            build_parser().parse_args(["diagnose", "x.pdf", "-n", "-5"])

    def test_zero_and_positive_pages_accepted(self):
        from arafix.cli import build_parser

        args = build_parser().parse_args(["diagnose", "x.pdf", "-n", "0"])
        assert args.pages == 0
        args = build_parser().parse_args(["diagnose", "x.pdf", "-n", "3"])
        assert args.pages == 3

    def test_output_same_as_input_refused(self, tmp_path, monkeypatch, capsys):
        """arafix extract x.pdf -o x.pdf كان يمحو الـ PDF الأصلي."""
        from arafix import cli

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 minimal")

        def fake_extract(path, cfg=None):
            class Doc:
                text = "نص"
                confidence = 0.9
                pages = []
                metadata = {}
                all_tables = []

            return Doc()

        monkeypatch.setattr(cli, "extract_pdf", fake_extract)
        rc = cli.main(["extract", str(pdf), "-o", str(pdf)])
        assert rc == 1  # main() تلتقط RuntimeError وتطبعها على stderr
        err = capsys.readouterr().err
        assert "المخرج يطابق الملف المصدر" in err
        assert pdf.read_bytes() == b"%PDF-1.4 minimal"

    def test_stdio_reconfigure_is_safe_without_streams(self):
        """reconfigure غائبة (بيئات مضمومة) — لا انهيار."""
        import io
        import sys

        from arafix.cli import _ensure_utf8_stdio

        old = sys.stdin, sys.stdout, sys.stderr
        try:
            sys.stdin = io.StringIO()
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            _ensure_utf8_stdio()  # يجب أن يعود صامتاً
        finally:
            sys.stdin, sys.stdout, sys.stderr = old

    def test_stdio_reconfigured_to_utf8_when_piped(self):
        import io
        import sys

        from arafix.cli import _ensure_utf8_stdio

        buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            _ensure_utf8_stdio()
            assert buf.encoding.lower().startswith("utf")
        finally:
            sys.stdout = old_stdout
            buf.detach()


# ---------------------------------------------------------------------------
# normalize_result: الثقة لم تعد ternary ميتاً (سلوكٌ محفوظ)
# ---------------------------------------------------------------------------

class TestNormalizeResult:
    def test_confidence_is_one_either_way(self):
        from arafix.normalize import normalize_result

        assert normalize_result("ﺎﺒﺣﺮﻣ").confidence == 1.0
        assert normalize_result("سليم").confidence == 1.0
