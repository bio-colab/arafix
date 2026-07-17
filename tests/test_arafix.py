"""
حزمة الاختبارات.

مبدأ: كل اختبار يوثّق **قراراً** لا سطر كود. فإن كسرته يوماً، ستعرف
من اسمه أيّ قرارٍ كسرت ولماذا اتُّخذ أوّلاً.
"""

import pytest

from arafix import (
    Defect,
    NormalizeConfig,
    PipelineConfig,
    Stage,
    decode_glyph_name,
    detect_mojibake,
    detect_visual_order,
    diagnose,
    fix_order,
    fold_presentation_forms,
    normalize_text,
    repair_text,
    reverse_visual_line,
)
from arafix.unicode_tables import PF_JOINING_FORM, PF_TO_BASE, JoiningForm

# عيّنات: نبنيها بالأكواد الصريحة لا باللصق، كي لا يخدعنا المحرّر.
PF_MARHABA = "\ufee3\ufeae\ufea3\ufe92\ufe8e"   # مرحبا بالأشكال الرسومية
PLAIN_MARHABA = "مرحبا"
LAM_ALEF = "\ufefb"                              # لا مركّبة في محرف واحد
MOJIBAKE = "Ø§Ù„Ø³Ù„Ø§Ù…"                       # "السلام" بـ UTF-8/Latin-1


# ── الجداول ────────────────────────────────────────────────────────────

class TestTables:
    def test_tables_are_generated_not_hardcoded(self):
        """٧٠٠+ مدخلة مشتقّة من unicodedata — لا يد بشرية فيها."""
        assert len(PF_TO_BASE) > 600

    def test_lam_alef_decomposes_to_two_letters(self):
        """قرار: نحتفظ بالتفكيك سلسلةً، فلام-ألف حرفان لا حرف."""
        assert PF_TO_BASE[LAM_ALEF] == "لا"
        assert PF_TO_BASE["\ufef5"] == "لآ"

    def test_bom_excluded_from_tables(self):
        """U+FEFF يقع في النطاق صدفةً تاريخية وليس حرفاً — استُثني صراحةً."""
        assert "\ufeff" not in PF_TO_BASE

    def test_joining_forms_declared(self):
        assert PF_JOINING_FORM["\ufedf"] is JoiningForm.INITIAL   # لـ
        assert PF_JOINING_FORM["\ufee2"] is JoiningForm.FINAL     # ـم


# ── الدرجة ١: التطبيع ──────────────────────────────────────────────────

class TestNormalize:
    def test_folds_presentation_forms(self):
        assert fold_presentation_forms(PF_MARHABA) == PLAIN_MARHABA

    def test_lam_alef_becomes_two_chars(self):
        assert fold_presentation_forms(LAM_ALEF) == "لا"

    def test_strips_tatweel_by_default(self):
        assert normalize_text("مرحـــبا") == "مرحبا"

    def test_does_not_touch_latin_or_math(self):
        """قرار: تطبيع موجَّه لا NFKC عام — لئلا نخرّب الرموز والمراجع."""
        src = "R² = 0.87 ﬁle ①"
        assert normalize_text(src) == src  # NFKC كان سيحوّلها كلها

    def test_diacritics_kept_by_default(self):
        """قرار: مهمّة المكتبة الاسترجاع لا التعديل."""
        assert normalize_text("مُحَمَّد") == "مُحَمَّد"

    def test_diacritics_removed_on_request(self):
        cfg = NormalizeConfig(strip_diacritics=True)
        assert normalize_text("مُحَمَّد", cfg) == "محمد"

    def test_alef_unification_is_opt_in(self):
        assert normalize_text("أحمد") == "أحمد"
        assert normalize_text("أحمد", NormalizeConfig(unify_alef=True)) == "احمد"


# ── الدرجة ٢: الاتجاه ──────────────────────────────────────────────────

class TestOrder:
    def test_reverses_arabic(self):
        assert reverse_visual_line("ابحرم") == "مرحبا"

    def test_protects_digits(self):
        """الخطأ الشائع: text[::-1] يقلب 2024 إلى 4202. لا نفعل."""
        assert reverse_visual_line("2024 ماع") == "عام 2024"

    def test_protects_latin_words(self):
        assert "GDP" in reverse_visual_line("GDP رشؤم")

    def test_mirrors_brackets(self):
        out = reverse_visual_line("(ةمدقم)")
        assert out.startswith("(") and out.endswith(")")

    def test_per_line_independence(self):
        out = fix_order("ابحرم\nاعدو")
        assert out == "مرحبا\nودعا"


# ── الدرجة ٠: التشخيص ──────────────────────────────────────────────────

class TestDiagnose:
    def test_detects_presentation_forms(self):
        assert diagnose(PF_MARHABA * 5).has(Defect.PRESENTATION_FORMS)

    def test_clean_text_is_clean(self):
        d = diagnose("هذه جملة عربية سليمة تماماً ولا علّة فيها البتة")
        assert d.healthy

    def test_detects_mojibake_algebraically(self):
        ok, recovered, _ = detect_mojibake(MOJIBAKE)
        assert ok and recovered == "السلام"

    def test_mojibake_is_not_broken_cmap(self):
        """تصحيحٌ لخطأ تشخيصي شائع: الموجيبيك علّة أنبوبك لا علّة الـ PDF."""
        d = diagnose(MOJIBAKE)
        assert d.has(Defect.MOJIBAKE)
        assert not d.has(Defect.BROKEN_CMAP)

    def test_detects_pua_as_broken_cmap(self):
        assert diagnose("\ue001\ue002\ue003 نص").has(Defect.BROKEN_CMAP)

    def test_empty_text_is_scan_candidate(self):
        assert diagnose("   \n  ").has(Defect.NO_TEXT_LAYER)

    def test_small_sample_refuses_order_judgment(self):
        """قرار: لا نحكم على عيّنةٍ دون عتبة الكفاية."""
        d = diagnose("مر")
        assert not d.has(Defect.VISUAL_ORDER)


class TestOrderDetection:
    def test_taa_marbuta_signal(self):
        """التاء المربوطة لا تقع إلا آخر الكلمة — قاعدة صلبة."""
        logical = "دراسة مقارنة حديثة في السياسة العامة والإدارة المحلية"
        visual = " ".join(w[::-1] for w in logical.split())
        assert detect_visual_order(logical)[0] < 0
        assert detect_visual_order(visual)[0] > 0

    def test_joining_forms_signal(self):
        visual_pf = PF_MARHABA[::-1] * 4
        assert detect_visual_order(visual_pf)[0] > 0

    def test_evidence_is_always_reported(self):
        _, ev = detect_visual_order("نص عربي طويل نسبياً لأجل الاختبار")
        assert {e.name for e in ev} == {
            "final_only_letters",
            "joining_forms",
            "definite_article",
        }


# ── الدرجة ٣ ───────────────────────────────────────────────────────────

class TestGlyphNames:
    @pytest.mark.parametrize(
        "name,expected",
        [("uni0645", "م"), ("u0631", "ر"), ("uni06450631", "مر")],
    )
    def test_decodes_standard_names(self, name, expected):
        assert decode_glyph_name(name) == expected

    @pytest.mark.parametrize("name", ["cid1234", "g55", "glyph7", ""])
    def test_refuses_meaningless_names(self, name):
        """قرار أخلاقي: cidNNN رقمٌ داخلي بلا دلالة. من يفكّه يخترع."""
        assert decode_glyph_name(name) is None


# ── الأنبوب ────────────────────────────────────────────────────────────

class TestPipeline:
    def test_normalizes_then_reports(self):
        r = repair_text(PF_MARHABA * 4)
        assert Stage.NORMALIZE in r.stages_applied
        assert r.text.startswith(PLAIN_MARHABA)

    def test_normalize_precedes_reorder(self):
        """
        القرار المعماري الأهم: الدرجة ١ تفتح عين الدرجة ٢.

        نصّ معكوس وبأشكال رسومية معاً: بلا تطبيعٍ أولاً، كاشف الاتجاه
        أعمى عن التاء المربوطة المخبوءة خلف شكلها.
        """
        logical = "دراسة مقارنة حديثة في السياسة المحلية والإدارة العامة"
        broken = "".join(
            {v: k for k, v in PF_TO_BASE.items() if len(v) == 1}.get(c, c)
            for c in logical
        )[::-1]
        r = repair_text(broken)
        assert Stage.NORMALIZE in r.stages_applied
        assert Stage.REORDER in r.stages_applied
        assert "دراسة" in r.text

    def test_does_not_touch_healthy_text(self):
        """أهم اختبار في الحزمة: المكتبة لا تعالج «احتياطاً»."""
        clean = "هذه دراسة مقارنة في السياسة العامة نُشرت عام 2024 بالعراق"
        r = repair_text(clean)
        assert r.text == clean
        assert not r.changed

    def test_mojibake_fixed_before_everything(self):
        r = repair_text(MOJIBAKE)
        assert "السلام" in r.text

    def test_broken_cmap_caps_confidence(self):
        """قرار: لا ثقة عالية في نصٍّ مصدره خريطة تالفة، مهما نظّفناه."""
        r = repair_text("\ue001\ue002\ue003 نص عربي مع رموز خاصة كثيرة هنا")
        assert r.confidence <= 0.3

    def test_reports_every_decision(self):
        r = repair_text(PF_MARHABA * 4)
        assert r.notes and r.diagnosis.evidence

    def test_force_reorder_lowers_confidence(self):
        """العكس القسري بلا شاهد يُصرَّح بثمنه: ثقة ٠٫٥."""
        cfg = PipelineConfig(force_reorder=True)
        r = repair_text("نص عربي سليم تماماً لا يحتاج عكساً البتة", cfg)
        assert Stage.REORDER in r.stages_applied
        assert r.confidence <= 0.5
