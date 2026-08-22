"""
H5 — Bidi Fuzzing: توليد permutations وقياس الطمرات غير المتوقعة.

حالة 2026-08-22: الـfuzzing (360 حالة × 3 بذور) كشف ست فئات ثغرات
كامنة (GAP-1..6 أدناه) لم تغطها الـ1000 حالة الموثقة سابقاً.

دلالتان مهمتان للاختبارات:
  * ``fix_order`` محوّل اتجاهيّ **غير مشروط**: تطبيقُه مرتين يعيد
    الأصل على الخطوط أحادية الاتجاه (انعكاسية، لا idempotence).
  * قانون Idempotence ينطبق على البوابات المغلقة: ``repair_text``
    (التي تسأل الشواهد قبل العكس).
"""
from __future__ import annotations

import random

import pytest
from harness import seeded

from arafix import PipelineConfig, fix_order, repair_text

SEGMENTS_ARABIC = ["النسبية", "العامة", "دراسة", "المشروع", "التقرير", "الكتاب"]
SEGMENTS_GAPS = [
    "GDP", "Report", "user@site.com", "https://example.com/a?b=1",
    "«اقتباس»", "(ص. 12)",
]


def build_cases(rng: random.Random, count: int) -> list[str]:
    cases = []
    for _ in range(count):
        k = rng.randint(2, 6)
        segs = [rng.choice(SEGMENTS_ARABIC) for _ in range(k)]
        line = rng.choice([" ", " ", "، ", " - ", " / "]).join(segs)
        cases.append(line)
    return cases


def skeleton(t: str) -> str:
    return "".join(c for c in t if not c.isspace())


class TestGuaranteedCoreArabicOnly:
    """العربي الخالص المعكوس خاماً يعود كاملاً — أقوى قدرة مثبتة."""

    @pytest.mark.parametrize("seed", [11, 22, 33])
    def test_zero_mutations(self, seed):
        rng = seeded(seed)
        for case in build_cases(rng, 60):
            out = fix_order(case[::-1])
            assert skeleton(out) == skeleton(case), case[:40]

    def test_reverser_is_involution_on_uniform_lines(self):
        """R(R(x)) == x على أسطرٍ أحادية الاتجاه — خاصية المحول."""
        rng = seeded(55)
        for case in build_cases(rng, 30):
            once = fix_order(case[::-1])
            assert fix_order(once[::-1]) == case


class TestSolidLtrInline:
    CASES = [
        "دراسة عامة عن النسبية 2024 والمشروع",
        "التقرير النهائي 125-140 والنسبية العامة",
        "المشروع v1.2.3 والتقرير النهائي للنسبية",
    ]

    @pytest.mark.parametrize("case", CASES)
    def test_inline_solid_patterns_restored(self, case):
        out = fix_order(case[::-1])
        assert skeleton(out) == skeleton(case), case


class TestResolvedGaps:
    """فئات كانت ثغراتٍ وأُغلقت بتحسينات العناقيد وجريان العلامات."""

    def test_gap4_short_latin_now_restored(self):
        case = "GDP Report النسبية"
        out = fix_order(case[::-1])
        assert "GDP" in out and "Report" in out

    def test_gap6_wrapped_parens_now_restored(self):
        case = "(دراسة / $1,250.00 / المشروع / 3.5%)"
        out = fix_order(case[::-1])
        assert out.startswith("(") and "3.5%" in out


@pytest.mark.xfail(
    reason=(
        "GAP-1 URL معكوسة؛ GAP-2 مرآة الاقتباس المزدوجة؛ GAP-3 أرقام "
        "في أقواس معكوسة؛ GAP-5 رمز LTR عند حدّي السطر — قرارات "
        "تصميمية مؤجلة لجلسة مخصصة"
    ),
    strict=True,
)
class TestKnownGapClassesStillFailing:
    """الفئات الباقية مفتوحة — كل واحد يثبت وجود ثغرته تحديداً."""

    def test_gap1_url(self):
        case = "(https://example.com/a?b=1 النسبية)"
        assert "example.com" in fix_order(case[::-1])

    def test_gap2_guillemets(self):
        case = "دراسة «اقتباس»"
        assert "«اقتباس»" in fix_order(case[::-1])

    def test_gap3_digits_in_parens(self):
        case = "(ص. 12) دراسة"
        out = fix_order(case[::-1])
        assert "12" in out and "21" not in out

    def test_gap5_boundary_token(self):
        case = "+966501234567 v1.2.3 العامة التقرير المشروع"
        assert fix_order(case[::-1].strip() + " ").startswith("+966501234567")


# ---------------------------------------------------------------------------
# قانون Idempotence عبر البوابة المغلقة (repair_text) — الصحيح معماريّاً
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "(https://example.com/a?b=1 النسبية)",
        "دراسة «اقتباس»",
        "(ص. 12) دراسة",
        "GDP Report النسبية",
        "المشروع / 2024 / دراسة / +966501234567 / النسبية",
    ],
)
def test_gated_pipeline_idempotent(case):
    cfg = PipelineConfig(forward_flank_marks=True)
    once = repair_text(case[::-1], cfg).text
    twice = repair_text(once, cfg).text
    assert twice == once
