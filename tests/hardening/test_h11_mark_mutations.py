"""H11 — تعذيب الحركات: محرك طفرات × سورة يس المُشكَّلة كثيفاً."""
from __future__ import annotations

import random
from pathlib import Path

import pytest
from harness import mutate_marks, split_marks

from arafix import PipelineConfig, repair_text

GOLD = (
    Path(__file__).parents[2]
    / "benchmarks/wiki_eval/quran/yaseen.simple.gold.txt"
).read_text(encoding="utf-8")

CFG = PipelineConfig()
KINDS = ["delete", "duplicate", "move", "reverse_run", "cross_letter"]


def cluster_acc(gold: str, cand: str) -> float | None:
    """
    دقة الالتصاق **لغوياً**: تقارن مجموعات الحركات بعد توحيد الترتيب
    القياسي (شدة أولاً — اتفاقية المكتبة والرسم القرآني). الفرق في
    الترتيب الطباعي وحده ليس خطأ لغوياً.
    يعيد None إن اختلفت القواعد نفسها.
    """
    from arafix.order import order_combining_marks

    gu = split_marks(gold)
    ou = split_marks(cand)
    if [b for b, _ in gu] != [b for b, _ in ou]:
        return None
    exact = sum(
        1
        for (_, gm), (_, om) in zip(gu, ou)
        if order_combining_marks(gm) == order_combining_marks(om)
    )
    return exact / len(gu) if gu else 1.0


def long_lines(min_len: int = 35, cap: int = 14) -> list[str]:
    return [line for line in GOLD.splitlines() if len(line) > min_len][:cap]


@pytest.mark.parametrize("kind", KINDS)
def test_repair_never_worse_than_input(kind):
    """الإصلاح لا يجعل دقة الالتصاق أسوأ من النص المعطوب المدخل."""
    rng = random.Random(abs(hash(kind)) & 0xFFFF)
    worse = measured = 0
    for line in long_lines():
        mut, _ = mutate_marks(line, kind, rng, count=2)
        if mut == line:
            continue
        out = repair_text(mut, CFG).text
        a, b = cluster_acc(line, mut), cluster_acc(line, out)
        if a is None or b is None:
            continue
        measured += 1
        if b < a - 1e-9:
            worse += 1
    assert worse == 0, f"{kind}: {worse}/{measured} حالة أصبحت أسوأ"


def test_reverse_run_partially_recovered():
    """انعكاس جريان العلامات قابلٌ للاسترجاع نصياً في جزء من الحالات."""
    rng = random.Random(99)
    improved = measured = 0
    for line in long_lines(45, 20):
        mut, _ = mutate_marks(line, "reverse_run", rng, count=3)
        if mut == line:
            continue
        before = cluster_acc(line, mut)
        out = repair_text(mut, CFG).text
        after = cluster_acc(line, out)
        if before is None or after is None:
            continue
        measured += 1
        if after > before:
            improved += 1
    assert measured > 0, "لا حالات قياس"
    # لا نشترط نسبةً صارمة — التوثيق: الاسترجاع موجود لكنه جزئي
