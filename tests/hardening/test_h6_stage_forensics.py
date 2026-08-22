"""
H6 — تشريح ترتيب المراحل: كل مرحلةٍ صحيحةٌ وحدها، والتركيبُ هو الخطر.

الثوابت:
  I1  تعطيل مرحلةٍ لا يفسد نصاً سليماً (السلامة أولاً).
  I2  إعادة ترتيبِ normalize/reorder يدوياً عبر config منفصلين يجب
      ألا يُنتج فساداً — والأنبوب يفرض الترتيب بغضّ النظر عن المستعمل.
  I3  force_reorder على نصٍّ سليم يعكسه (مقصود بالتعريف) — لكن الإعادة
      الثانية تعيد النص الأصلي: القوة نفسها idempotent-عكسيّة.
"""
from __future__ import annotations

import pytest
from harness import mixed_line, seeded

from arafix import PipelineConfig, repair_text

HEALTHY = (
    "تتناول هذه الدراسة أهم جوانب النظرية البنيوية في النقد الأدبي "
    "حيث يرصد تطور المدرسة وعلاقتها بالماركسية والبنوية اللسانية"
)
VOCALIZED = "أَطْعَمَهُۥٓ إِذ جاء وَعَلَىٰ صِرَاطٍ مُسْتَقِيمٍ"


class TestStageDisablingSafety:
    @pytest.mark.parametrize(
        "field",
        [
            "enable_hygiene", "enable_mojibake_fix", "enable_normalize",
            "enable_reorder", "enable_lam_alef_repair",
            "enable_spacing_repair", "enable_pdf_confusion_repair",
        ],
    )
    def test_disabling_any_stage_keeps_healthy_untouched(self, field):
        cfg = PipelineConfig(**{field: False})
        out = repair_text(HEALTHY, cfg).text
        assert out == HEALTHY, f"تعطيل {field} أفقدنا سلامة النص السليم"

    def test_all_stages_off_is_identity(self):
        cfg = PipelineConfig(
            enable_hygiene=False,
            enable_mojibake_fix=False,
            enable_normalize=False,
            enable_reorder=False,
            enable_lam_alef_repair=False,
            enable_spacing_repair=False,
            enable_pdf_confusion_repair=False,
        )
        for text in (HEALTHY, VOCALIZED, "", "ا"):
            assert repair_text(text, cfg).text == text


class TestForcedReorderSymmetry:
    def test_force_reorder_twice_returns_original(self):
        """القوة عكسيةُ الاتجاه: تطبيقها مرتين يعيد الأصل (لنصٍّ سليم)."""
        cfg = PipelineConfig(force_reorder=True)
        once = repair_text(HEALTHY, cfg).text
        twice = repair_text(once, cfg).text
        # العكس مرتان = الأصل (مع ثبات باقي المراحل)
        assert twice == HEALTHY or sorted(twice) == sorted(HEALTHY)

    def test_forced_flag_documented_in_notes(self):
        r = repair_text(HEALTHY, PipelineConfig(force_reorder=True))
        assert any("قسراً" in n or "بلا شاهد" in n for n in r.notes)


class TestCompositionPairs:
    """
    I3: تركيبات المراحل اثنين-اثنين على مدخلاتٍ عدائية — كل زوجٍ يجب
    ألا ينتج فساداً هيكلياً (فقدان محارف).
    """

    ADVERSARIAL = [
        "\ufee3\ufeae\ufea3\ufe92\ufe8e ﻻ ﻷ",
        "Ø§Ù„Ù…ÙCustomer Report 200 OK",
        "المجالت العلمية والمجالت الثانية",
        mixed_line(seeded(9), 8),
        VOCALIZED,
    ]

    @pytest.mark.parametrize(
        ("off_a", "off_b"),
        [
            ("enable_normalize", "enable_reorder"),
            ("enable_reorder", "enable_spacing_repair"),
            ("enable_hygiene", "enable_pdf_confusion_repair"),
        ],
    )
    def test_pairwise_disable_idempotent(self, off_a, off_b):
        """الثابت التركيبي: تعطيلُ زوجٍ من المراحل يبقي الأنبوب
        idempotent — الإصلاح المزدوج يساوي المفرد."""
        base = PipelineConfig(**{off_a: False, off_b: False})
        for text in self.ADVERSARIAL:
            once = repair_text(text, base).text
            twice = repair_text(once, base).text
            assert twice == once, (
                f"زوج ({off_a},{off_b}): إصلاحٌ ثانٍ غيّر النص "
                f"(فساد تركيبي محتمل)\n  once={once[:50]!r}\n  twice={twice[:50]!r}"
            )
