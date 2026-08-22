"""
H2 — قانون Idempotence الشامل:  R(R(x)) == R(x)  لكل إعداداتٍ مهمة.

الأخطر هنا ليس crash بل **الفساد الصامت**: إصلاحٌ أول يصنع شكلاً يبدو
مدخلاً فاسداً جديداً فيغيّره الثاني.
"""
from __future__ import annotations

import pytest
from harness import CONFIG_MATRIX, ConfigVariant, mixed_line, seeded

from arafix import PipelineConfig, repair_text

CORPUS = [
    "المجالت العلمية والمجالت الثانية والثالثة",
    "\ufee3\ufeae\ufea3\ufe92\ufe8e ﻻ ﻷ ﻵ والنسبية العامة",
    "Ø§Ù„Ù…ÙCustomer Report 200 OK دراسة",
    mixed_line(seeded(1), 10),
    mixed_line(seeded(2), 14),
    "درس الطالب درسه القديم في المكتبة العامة وصلى على النبي",
    "أَطْعَمَهُۥٓ إِذ جاء وعَلَىٰ صِرَاطٍ مُسْتَقِيمٍ",
    "",
    "ا",
]


@pytest.mark.parametrize("variant", CONFIG_MATRIX, ids=[v.name for v in CONFIG_MATRIX])
@pytest.mark.parametrize("text", CORPUS)
def test_double_repair_equals_single(variant: ConfigVariant, text: str):
    cfg = PipelineConfig(**variant.overrides)
    once = repair_text(text, cfg).text
    twice = repair_text(once, cfg).text
    assert twice == once


@pytest.mark.parametrize("variant", CONFIG_MATRIX, ids=[v.name for v in CONFIG_MATRIX])
def test_audit_stabilizes_after_first_run(variant: ConfigVariant):
    """audit(R(x)) لا يولّد سلسلة إصلاحات جديدة عند الإعادة."""
    text = CORPUS[0]
    overrides = {k: v for k, v in variant.overrides.items() if k != "audit_mode"}
    cfg = PipelineConfig(audit_mode="summary", **overrides)
    first = repair_text(text, cfg)
    second = repair_text(first.text, cfg)
    events_second = len(second.audit.events) if second.audit else 0
    assert events_second == 0 or second.text != first.text  # أي حدث=تغيير، ولا تغيير متوقع


def test_evidence_extraction_stable_across_runs():
    """E(R(x)) == E(x): التشخيص بعد الإصلاح مستقر عند الإعادة."""
    from arafix.diagnose import diagnose

    for text in CORPUS:
        cfg = PipelineConfig()
        first = repair_text(text, cfg)
        d1 = diagnose(first.text)
        second = repair_text(first.text, cfg)
        d2 = diagnose(second.text)
        assert [d.value for d in d1.defects] == [d.value for d in d2.defects]
