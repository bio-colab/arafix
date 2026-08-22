"""
H12 — بوابة أداء الانحدار: أي patch لا يجوز أن يرفع الزمن أكثر من X%
على corpus ثابت، مع ثبات المخرجات (التحسين لا يغيّر النص).

المنهجية:
  * corpus ثابت مضمّن في الملف.
  * لكل حالة: min من 3 تشغيلات (يقلل ضجيج البيئة).
  * خط الأساس مخزَّن في PERF_BASELINE (ثوانٍ) — قيم مرجعية مقيسة
    على جهاز التطوير؛ الهامش المسموح ×2.5 لامتصاص فروق الأجهزة.
  * الثابت المصاحب: مخرج الحالة ثابت عبر التكرارات (hash).
"""
from __future__ import annotations

import hashlib
import time

import pytest

from arafix import PipelineConfig, repair_text

# نسبة الرفع المسموح فوق خط الأساس المرجعي
_TOLERANCE = 2.5

PERF_BASELINE = {
    # ثوانٍ — قيم مرجعية مقيسة على جهاز التطوير (Python 3.12/Win)
    "quran-vocalized": 0.35,
    "mixed-bidi": 0.25,
    "pf-heavy": 0.30,
}

_CORPUS = {
    "quran-vocalized": (
        "وَٱلْقُرْآنِ ٱلْحَكِيمِ إِنَّكَ لَمِنَ ٱلْمُرْسَلِينَ عَلَىٰ صِرَٰطٍ "
        "مُّسْتَقِيمٍ وَٱلصِّرَٰطُ إِلَىٰ رَبِّكَ مُّسْتَقِيمٌ ۞ "
    )
    * 8,
    "mixed-bidi": (
        "تقرير GDP 2024 بنسبة 3.5% وUSD 1,250.00 للإصدار v1.2.3 "
        "حسب (ص. 125-140) وReport النهائي للمشروع "
    )
    * 10,
    "pf-heavy": "\ufee3\ufeae\ufea3\ufe92\ufe8e ﺎﺒﺣﺮﻣ ﻻ ﻷ ﻵ ﻣﺮﺣﺒﺎ " * 60,
}


def _min_of_3(fn) -> float:
    best = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


@pytest.mark.parametrize("case_name", list(PERF_BASELINE))
def test_performance_gate(case_name):
    text = _CORPUS[case_name]
    cfg = PipelineConfig()
    baseline = PERF_BASELINE[case_name]

    hashes = set()
    durations = []
    for _ in range(3):
        t0 = time.perf_counter()
        out = repair_text(text, cfg).text
        durations.append(time.perf_counter() - t0)
        hashes.add(hashlib.sha256(out.encode("utf-8")).hexdigest())

    runtime = min(durations)
    assert len(hashes) == 1, "المخرج غير مستقر بين التكرارات!"
    assert runtime <= baseline * _TOLERANCE, (
        f"انحدار أداء في {case_name}: {runtime:.3f}s > "
        f"{baseline * _TOLERANCE:.3f}s (خط الأساس {baseline}s)"
    )


def test_output_hash_stability_across_configs():
    """الثبات: نفس المدخل عبر إعدادات مختلفة قد يتغير نصياً (مقصود)،
    لكن داخل الإعداد الواحد لا بد من الاستقرار."""
    import hashlib as hl

    text = _CORPUS["quran-vocalized"]
    for cfg in (PipelineConfig(), PipelineConfig(forward_flank_marks=True)):
        h1 = hl.sha256(
            repair_text(text, cfg).text.encode("utf-8")
        ).hexdigest()
        h2 = hl.sha256(
            repair_text(text, cfg).text.encode("utf-8")
        ).hexdigest()
        assert h1 == h2
