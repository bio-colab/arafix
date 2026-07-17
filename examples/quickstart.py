#!/usr/bin/env python3
"""
جولة سريعة على المكتبة — شغّلها وستراها تعمل على العلل الخمس كلها.

    python examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arafix import diagnose, repair_text, reverse_visual_line  # noqa: E402
from arafix.unicode_tables import PF_TO_BASE  # noqa: E402


def show(title: str, text: str) -> None:
    print("\n" + "─" * 66)
    print(f"■ {title}")
    print("─" * 66)
    print(f"  الخام    : {text[:60]!r}")

    d = diagnose(text)
    print(f"  التشخيص  : {d.summary()}   (ثقة {d.confidence})")
    for e in d.evidence:
        if abs(e.value) > 0.01:
            print(f"      · {e.name:22s} {e.value:+.3f}  {e.detail}")

    r = repair_text(text)
    print(f"  العلاج   : {r.text[:60]!r}")
    print(f"  المراحل  : {[s.value for s in r.stages_applied]}   (ثقة {r.confidence})")
    for n in r.notes:
        print(f"      · {n}")


LOGICAL = "دراسة مقارنة حديثة في السياسة العامة نُشرت عام 2024"

# نبني العينات المعطوبة من الجداول نفسها — لا لصقاً من محرّر قد يخدعنا.
_ISO = {v: k for k, v in PF_TO_BASE.items() if len(v) == 1}


def main() -> None:
    print("arafix — جولة على العلل الخمس")

    # ١ — سليم: يجب ألّا تمسّه المكتبة
    show("نصّ سليم (اختبار عدم الأذى)", LOGICAL)

    # ٢ — أشكال رسومية
    show("أشكال رسومية مطبوخة", "".join(_ISO.get(c, c) for c in LOGICAL))

    # ٣ — ترتيب بصريّ. نستعمل reverse_visual_line لا [::-1]:
    #     المُصدِّر الواقعي لا يعكس الأرقام، فمحاكاته بـ [::-1] محاكاةُ عطبٍ
    #     لا وجود له — والتحويل انعكاسيّ فالدالة نفسها تصلح وتُعطِب.
    show("ترتيب بصريّ معكوس", reverse_visual_line(LOGICAL))

    # ٤ — الاثنان معاً: هنا يظهر أثر ترتيب الدرجات
    show("مطبوخ ومعكوس معاً", reverse_visual_line("".join(_ISO.get(c, c) for c in LOGICAL)))

    # ٥ — موجيبيك
    show("موجيبيك", LOGICAL.encode("utf-8").decode("latin-1"))

    # ٦ — خريطة تالفة
    show("خريطة تالفة (PUA)", "\ue001\ue002\ue003\ue004 " + LOGICAL[:20])

    print("\n" + "─" * 66)
    print("لاحظ الحالة الأولى: لم تُمسّ. المكتبة لا تعالج «احتياطاً».")
    print("ولاحظ الأخيرة: الثقة سُقِفت عند ٠٫٣ — لأن النص أصلاً بلا معنى.")


if __name__ == "__main__":
    main()
