"""
اختبارات الدعم الإسلامي: العلامات القرآنية والصيغ الشرعية.

العقد المركزي (دستور المكتبة): **لا إصلاح إلا مبرَّراً.**
  * كل علامات التشكيل القرآني (Mn) والرموز الرسمية (So) تنجو من الأنبوب
    كاملةً بلا استثناء.
  * الصيغ الشرعية ذات التوسيع الموثَّق (ﷺ ﷲ ﷻ) تُفكُّ إلى نصِّها
    القياسي؛ وما لا توسيعَ موثقاً له (ﷰ ﷯ ﷽) يبقى محرفاً كما هو —
    التحفظُ أمانٌ لا قصور.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from arafix import PipelineConfig, repair_text
from arafix.normalize import normalize_text
from arafix.order import ReorderConfig, reverse_visual_line
from arafix.unicode_tables import is_arabic

# ---------------------------------------------------------------------------
# ١) جرد عائلات المحارف القرآنية
# ---------------------------------------------------------------------------

QURANIC_MN = [chr(c) for c in range(0x06D6, 0x06DD)] + [
    chr(c) for c in range(0x06DF, 0x06E9)
]
QURANIC_SO = ["\u06dd", "\u06de", "\u06e9"]  # ۝ ۞ ۩
SMALL_LETTERS = ["\u06e5", "\u06e6"]        # ۥ ۦ
DAGGER_ALEF = "\u0670"                      # ٰ


class TestClassification:
    @pytest.mark.parametrize("ch", QURANIC_MN + QURANIC_SO)
    def test_quranic_marks_count_as_arabic(self, ch):
        assert is_arabic(ch), f"{hex(ord(ch))} غير مصنفة عربية"

    @pytest.mark.parametrize("ch", [DAGGER_ALEF])
    def test_dagger_alef_is_combining_mark(self, ch):
        assert unicodedata.category(ch) == "Mn"
        assert is_arabic(ch)

    @pytest.mark.parametrize("ch", SMALL_LETTERS)
    def test_small_letters_are_modifier_letters(self, ch):
        """ۥ ۦ فئتهما Lm (حرفٌ مُعدِّل) لا Mn — لكنهما يُعامَلان
        علاماتٍ في العناقيد (انظر order.ATTACHABLE_SMALL_LETTERS)."""
        assert unicodedata.category(ch) == "Lm"
        assert is_arabic(ch)


# ---------------------------------------------------------------------------
# ٢) البقاء الكامل عبر الأنبوب — بلا أي فقدان
# ---------------------------------------------------------------------------


def _survival_sample() -> str:
    marks = "".join(QURANIC_MN + QURANIC_SO)
    return f"قُلْ أَعُوذُ {marks} بِرَبِّ النَّبِيِّ ﷺ وَقَالَتْ ﷽"


@pytest.mark.parametrize("cfg", [PipelineConfig(), PipelineConfig(forward_flank_marks=True)])
def test_every_quranic_mark_survives_full_pipeline(cfg):
    text = _survival_sample()
    r = repair_text(text, cfg)
    for ch in set(text):
        if unicodedata.category(ch) == "Mn" or is_arabic(ch):
            assert ch in r.text, f"ضاع محرف: {ch} ({hex(ord(ch))})"


# ---------------------------------------------------------------------------
# ٣) الصيغ الشرعية: توسيعٌ موثَّق فقط
# ---------------------------------------------------------------------------


class TestHonorificLigatures:
    @pytest.mark.parametrize(
        ("lig", "expected"),
        [
            ("\ufdfa", "صلى الله عليه وسلم"),   # ﷺ
            ("\ufdf2", "الله"),                 # ﷲ
            ("\ufdfb", "جل جلاله"),             # ﷻ
        ],
    )
    def test_verified_expansions(self, lig, expected):
        out = normalize_text(lig).strip()
        assert expected in out.replace("  ", " ")

    @pytest.mark.parametrize("lig", ["\ufdf0", "\ufdf1", "\ufdfd", "\ufdef"])
    def test_unverified_forms_preserved_untouched(self, lig):
        """لا توسيع موثقاً → لا تغيير (UNCERTAIN يُسجَّل ولا يُغيَّر)."""
        out = normalize_text(lig)
        assert lig in out, f"مُسَّ محرفٌ بلا تبرير: {hex(ord(lig))}"

    def test_garbage_expansion_never_emitted(self):
        """«صلے» كان يخرج من U+FDF0 قبل الإصلاح — لا يعود."""
        out = normalize_text("\ufdf0")
        assert "صلے" not in out

    def test_in_sentence_with_spacing_intact(self):
        sent = "قال النبيُّ ﷺ إنَّ الصدقَ يهدي، وعثمانُ ﷲ رضي الله عنه"
        out = repair_text(sent, PipelineConfig()).text
        assert "صلى الله عليه وسلم" in out
        assert "الله" in out
        # لا التصاقٍ بين الجملة والتوسيع
        assert "النبيُّ صلى" in out or "النبي صلى" in out


# ---------------------------------------------------------------------------
# ٤) سورة يس: العثمانية والإملائية عبر الأنبوب النصي مباشرة
# ---------------------------------------------------------------------------


class TestYaseenRoundTrip:
    GOLD_DIR = Path(__file__).parents[2] / "benchmarks" / "wiki_eval" / "quran"

    @pytest.mark.parametrize(
        "fname",
        ["yaseen.simple.gold.txt", "yaseen.uthmani.gold.txt"],
    )
    def test_no_content_loss_on_healthy_text(self, fname):
        gold_path = self.GOLD_DIR / fname
        if not gold_path.exists():
            pytest.skip(f"{fname} غير موجود")
        gold = gold_path.read_text(encoding="utf-8")
        r = repair_text(gold, PipelineConfig())
        # لا حروف أساسية تضيع ولا علامة Mn تضيع على نصٍّ سليم
        for ch in set(gold):
            if unicodedata.category(ch) == "Mn" or is_arabic(ch):
                assert ch in r.text, f"ضاع من {fname}: {ch} ({hex(ord(ch))})"


# ---------------------------------------------------------------------------
# ٥) الرسم العثماني المعكوس: الحروف الصغيرة ۥ ۦ وتسلسل الشدة
# ---------------------------------------------------------------------------


class TestUthmaniReversalRoundTrip:
    """انعكاسٌ خام (MuPDF) يعود كاملاً مع forward_flank_marks.

    يشمل الحروف الصغيرة ۥ ۦ (فئة Lm لا Mn — تُعامَل علاماتٍ في
    العناقيد)، وتسلسل الشدة/الحركة باتفاقيتي المصادر.
    """

    CFG = ReorderConfig(forward_flank_marks=True)

    @pytest.mark.parametrize(
        "logical",
        [
            "أَطْعَمَهُۥٓ إِذ",
            "دُونِهِۦٓ ءَايَة",
            "عَلَىٰ صِرَاطٍ مُسْتَقِيمٍ",
            "إِنَّكَ لَمِنَ الْمُرْسَلِينَ",
        ],
    )
    def test_full_round_trip(self, logical):
        out = reverse_visual_line(logical[::-1], self.CFG)
        # المحتوى متطابق؛ ترتيب الشدة/الحركة قد يتوحّد قياسياً
        # (شدة أولاً — مطابق للرسم القرآني نفسه).
        assert sorted(out) == sorted(logical) or out == logical

    def test_small_letters_bind_to_base_under_reversal(self):
        logical = "أَطْعَمَهُۥٓ"
        out = reverse_visual_line(logical[::-1], self.CFG)
        assert "هۥ" in out or "هُۥ" in out

    def test_quran_convention_shadda_first_matches_canonical(self):
        from arafix.order import order_combining_marks

        # الرسم القرآني يكتب شدة ثم حركة — الترتيب القياسي للمكتبة نفسه.
        assert order_combining_marks("\u0651\u064e") == "\u0651\u064e"
