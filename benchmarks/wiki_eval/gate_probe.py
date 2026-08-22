# -*- coding: utf-8 -*-
"""قياس مباشر: ماذا رأت بوابة الدرجة ٢ في كل تركيبة؟ بلا تأويل."""
from __future__ import annotations

import sys
from pathlib import Path

import fitz

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "../..")

from arafix import PipelineConfig  # noqa: E402
from arafix.diagnose import diagnose, detect_visual_order  # noqa: E402
from arafix.extractors import PyMuPDFExtractor  # noqa: E402
from arafix.normalize import fold_simple_forms  # noqa: E402

PDFS = Path("quran/pdfs")


def show_mode(mode: str) -> None:
    print(f"{'=' * 60}\n### {mode} ###")

    # ١) ما ينتجه المستخرج الفعلي (مسار الأنبوب)
    ex = PyMuPDFExtractor(layout_mode="auto")
    pages = list(ex.pages(str(PDFS / f"yaseen.{mode}.pdf")))
    raw_p1 = pages[0].text
    print(f"خام المستخرج p1 ({len(raw_p1)} محرف): {raw_p1[:80]!r}")

    dg = diagnose(raw_p1)
    print(f"تشخيص الخام: defects={[d.value for d in dg.defects]} order={dg.metrics.get('order_score', 0):+.3f}")
    score_raw, evs_raw = detect_visual_order(fold_simple_forms(raw_p1), shaped_source=raw_p1)
    print(f"درجة الاتجاه على الخام (بالمطابق للأنبوب): {score_raw:+.3f}")

    # ٢) الأنبوب بالوضعين
    for label, cfg in (("OFF", PipelineConfig()), ("ON", PipelineConfig(forward_flank_marks=True))):
        from arafix import extract_pdf  # noqa: E402

        res = __import__("arafix", fromlist=["extract_pdf"]).extract_pdf(
            str(PDFS / f"yaseen.{mode}.pdf"), cfg
        )
        p1 = res.pages[0]
        oscore = p1.repair.diagnosis.metrics.get("order_score", 0)
        print(f"\n[{label}] stages={[s.value for s in p1.repair.stages_applied]}")
        print(f"   order_score(بعد التطبيع)={oscore:+.3f} | conf={p1.repair.confidence:.3f}")
        for n in p1.repair.notes[:6]:
            print(f"   note: {n}")


for m in ("clean", "pf_visual"):
    show_mode(m)
