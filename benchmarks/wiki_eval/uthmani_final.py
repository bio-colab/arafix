# -*- coding: utf-8 -*-
"""قياس ختامي: يس العثمانية عبر الأنماط الثلاثة بالوضعين."""
import re
import sys
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
sys.path.insert(0, "../..")

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import make_pdfs  # noqa: E402

from arafix import PipelineConfig, extract_pdf  # noqa: E402

pdfmetrics.registerFont(TTFont(make_pdfs.FONT_NAME, str(make_pdfs.FONT_PATH)))


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def attachables(t: str) -> int:
    return sum(
        1
        for c in t
        if unicodedata.category(c) == "Mn" or c in "\u06e5\u06e6"
    )


gold = norm(Path("quran/yaseen.uthmani.gold.txt").read_text(encoding="utf-8"))
mn_gold = attachables(gold)

for mode in ("clean", "pf", "pf_visual"):
    make_pdfs.render_pdf(
        Path(f"quran/pdfs/uthmani.{mode}.pdf"), gold, mode
    )
    for label, cfg in (
        ("off", PipelineConfig()),
        ("on", PipelineConfig(forward_flank_marks=True)),
    ):
        res = extract_pdf(f"quran/pdfs/uthmani.{mode}.pdf", cfg)
        T = norm("\n".join(p.text.strip() for p in res.pages))
        mn = attachables(T)
        prev = list(range(len(gold) + 1))
        for i, a in enumerate(gold, 1):
            cur = [i]
            for j, b in enumerate(T, 1):
                cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (a != b)))
            prev = cur
        cer = prev[-1] / len(gold)
        print(f"{mode:10s} [{label}]: cer={cer:.4f} علامات={mn}/{mn_gold}")
