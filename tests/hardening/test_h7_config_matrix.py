"""
H7 — مصفوفة الإعدادات: القاعدة الذهبية
«أي خيارٍ جديد يجب ألا يغيّر النص إذا لم يكن مسؤولاً عن ذلك التغيير».

التنفيذ: لكل متغير إعدادات، نقارن مخرجه على corpus ثابت مقابل الافتراضي:
  * الفروق مسموحة فقط للمتغيرات ذات الدلالة النصية المعروفة
    (forward_flank_marks يملك العلامات، confidence_mode لا يملك نصاً…).
  * المتغيرات «الصامتة» (audit_mode, confidence_mode, rescue_mixed_lines
    على غير المختلط) يجب أن تكون identity حرفياً.
"""
from __future__ import annotations

import pytest
from harness import CONFIG_MATRIX, ConfigVariant, mixed_line, seeded

from arafix import PipelineConfig, repair_text

CORPUS = [
    "المجالت العلمية والمجالت الثانية والسؤال عن التعاليم",
    mixed_line(seeded(5), 10),
    mixed_line(seeded(6), 12),
    "درس الطالب درسه في المكتبة العامة وكتب التقرير",
]

# من يملك حق تغيير النص؟
TEXT_MUTATING = {
    "forward-marks",       # يملك ربط الحركات الأمامي كله
    "no-spacing",          # تعطيل مرحلة الفراغات يبقي ما كانت تصلحه/تكسره
    "no-confusions",       # تعطيل قائمة الالتباسات يبقي أخطاءها
    "no-lamalef",          # بلا معجم تبقى المجالت كما هي
    "no-normalize",        # بلا تطبيع تبقى الأشكال
    "no-reorder",          # بلا عكس يبقى الاتجاه
    "no-mojibake",         # بلا فكّ يبقى الموجيبيك
}

# صامتة نصياً على corpus عام (قد تتغير فقط في حالاتٍ هامشية موثقة)
SILENT_ON_GENERIC = {"audit-full", "density"}


def variant_by_name(name: str) -> ConfigVariant:
    return next(v for v in CONFIG_MATRIX if v.name == name)


class TestGoldenRule:
    @pytest.mark.parametrize("name", sorted(SILENT_ON_GENERIC))
    def test_silent_variants_are_identity(self, name):
        v = variant_by_name(name)
        cfg = PipelineConfig(**v.overrides)
        for text in CORPUS:
            base_out = repair_text(text, PipelineConfig()).text
            var_out = repair_text(text, cfg).text
            assert var_out == base_out, (
                f"المتغير الصامت {name} غيّر النص!\n"
                f"  base={base_out[:60]!r}\n  var ={var_out[:60]!r}"
            )

    def test_text_mutating_only_changes_when_its_domain_exists(self):
        """no-lamalef مثلاً لا يغير نصاً خالياً من لام-ألف أصلاً."""
        clean = "درس الطالب درسه في المكتبة العامة"
        cfg = PipelineConfig(enable_lam_alef_repair=False)
        assert repair_text(clean, cfg).text == repair_text(clean).text

    def test_matrix_smoke_all_combinations_run(self):
        """كل تركيبة تنفّذ على كل corpus دون استثناء — بابُ دخانٍ شامل."""
        for v in CONFIG_MATRIX:
            cfg = PipelineConfig(**v.overrides)
            for text in CORPUS:
                out = repair_text(text, cfg)
                assert isinstance(out.text, str)
