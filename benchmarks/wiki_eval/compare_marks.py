"""مقارنة forward_flank_marks على كامل الحقيبة (42 ملفاً)."""
from __future__ import annotations  # noqa: E402

import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "../..")

from arafix import PipelineConfig, extract_pdf  # noqa: E402
from arafix.evaluate import evaluate_text  # noqa: E402

ROOT = Path(".")
MANIFEST = json.loads((ROOT / "articles.json").read_text(encoding="utf-8"))

cfg_off = PipelineConfig()
cfg_on = PipelineConfig(forward_flank_marks=True)

rows = []
for art in MANIFEST["articles"]:
    slug = art["slug"]
    gold_path = ROOT / "articles" / f"{slug}.gold.txt"
    gold = gold_path.read_text(encoding="utf-8")
    for mode in ("clean", "pf", "pf_visual"):
        pdf = ROOT / "pdfs" / f"{slug}.{mode}.pdf"
        r_off = extract_pdf(str(pdf), cfg_off)
        r_on = extract_pdf(str(pdf), cfg_on)
        t_off = "\n\n".join(p.text for p in r_off.pages)
        t_on = "\n\n".join(p.text for p in r_on.pages)
        cer_off = evaluate_text(t_off, gold).cer.rate
        cer_on = evaluate_text(t_on, gold).cer.rate
        rows.append((slug, mode, cer_off, cer_on))
        mark = ""
        if abs(cer_off - cer_on) > 0.002:
            mark = "  <<<" + (" أفضل" if cer_on < cer_off else " أسوأ!")
        print(f"{slug:15s} {mode:10s} off={cer_off:.4f} on={cer_on:.4f}{mark}")

sum_off = sum(r[2] for r in rows)
sum_on = sum(r[3] for r in rows)
print(f"\nمجموع CER: off={sum_off:.4f} on={sum_on:.4f}")
better = sum(1 for r in rows if r[3] < r[2] - 0.001)
worse = sum(1 for r in rows if r[3] > r[2] + 0.001)
print(f"أفضل بـON: {better} | أسوأ بـON: {worse} | محايد: {len(rows)-better-worse}")
