# -*- coding: utf-8 -*-
"""
محور الفحص: سورة يس — تشكيلٌ كثيف 100% + ألف خنجرية.

يعيد استخدام مولّد PDF وأنماط الإتلاف نفسها من wiki_eval، ويقيس
الوضعين: افتراضي مقابل forward_flank_marks (لأن مولّدنا ينتج انعكاساً
خاماً معروفاً — الحركة قبل قاعدتها في الخام).
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import fitz

from arafix import PipelineConfig, extract_pdf
from arafix.evaluate import evaluate_text
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_pdfs  # noqa: E402
from make_pdfs import render_pdf  # noqa: E402

pdfmetrics.registerFont(
    TTFont(make_pdfs.FONT_NAME, str(make_pdfs.FONT_PATH))
)

ROOT = Path(__file__).resolve().parent
QURAN_DIR = ROOT / "quran"
PDFS_DIR = QURAN_DIR / "pdfs"
MODES = ("clean", "pf", "pf_visual")


def letters_only(t: str) -> str:
    return "".join(
        c for c in t if not (c.isspace() or c in ".,؛:!؟()[]{}«»\"'-—–/\\|*+=<>٪@#$&_~^`")
    )


def mn_count(t: str) -> int:
    return sum(1 for c in t if unicodedata.category(c) == "Mn")


def norm_layout(t: str) -> str:
    """يفصل فنَّ لفّ الأسطر عن المحتوى — فواصل التخطيط ليست نصاً."""
    return re.sub(r"\s+", " ", t).strip()


def cer(ref: str, hyp: str) -> float:
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / len(ref)


def classify(gold: str, out: str) -> dict[str, int]:
    sm = difflib.SequenceMatcher(None, gold, out, autojunk=False)
    buckets: dict[str, int] = {}

    def bump(k: str, n: int = 1) -> None:
        buckets[k] = buckets.get(k, 0) + n

    def is_pf(c: str) -> bool:
        return "\ufb50" <= c <= "\ufeff"

    def is_mn(c: str) -> bool:
        return unicodedata.category(c) == "Mn"

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        g, o = gold[i1:i2], out[j1:j2]
        gl = [c for c in g if not c.isspace()]
        ol = [c for c in o if not c.isspace()]
        if not gl and not ol:
            bump("spacing")
        elif not ol:
            if gl and all(is_mn(c) for c in gl):
                bump("mark-loss")
            elif any(is_mn(c) for c in gl):
                bump("mark-partial")
            else:
                bump("letter-deletion")
        elif not gl:
            bump("letter-insertion" if not any(is_pf(c) for c in ol) else "residual-pf")
        elif any(is_pf(c) for c in ol):
            bump("residual-pf")
        elif all(is_mn(c) for c in gl[:1]) or all(is_mn(c) for c in ol[:1]):
            bump("mark-swap")
        else:
            bump("letter-substitution")
    return buckets


def main() -> int:
    gold_path = QURAN_DIR / "yaseen.simple.gold.txt"
    gold = norm_layout(gold_path.read_text(encoding="utf-8"))

    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"الذهب: {len(gold)} محرفاً، حركات={mn_count(gold)}\n")
    for mode in MODES:
        render_pdf(PDFS_DIR / f"yaseen.{mode}.pdf", gold, mode)

    cfg_off = PipelineConfig()
    cfg_on = PipelineConfig(forward_flank_marks=True)
    results = []
    for mode in MODES:
        pdf = str(PDFS_DIR / f"yaseen.{mode}.pdf")
        doc = fitz.open(pdf)
        raw = "\n".join(p.get_text() for p in doc)
        doc.close()

        row = {"mode": mode, "raw_cer": round(cer(gold, raw), 4)}
        for label, cfg in (("off", cfg_off), ("on", cfg_on)):
            t0 = time.perf_counter()
            res = extract_pdf(pdf, cfg)
            dt = (time.perf_counter() - t0) * 1000
            text = norm_layout("\n".join(p.text.strip() for p in res.pages))
            e_full = evaluate_text(text, gold)
            lo = evaluate_text(letters_only(text), letters_only(gold))
            row[label] = {
                "cer": round(e_full.cer.rate, 4),
                "wer": round(e_full.wer.rate, 4),
                "cer_lo": round(lo.cer.rate, 4),
                "marks": f"{mn_count(text)}/{mn_count(gold)}",
                "conf_min": min(p.repair.confidence for p in res.pages),
                "ms": round(dt),
            }
        results.append(row)
        o, n = row["off"], row["on"]
        print(
            f"{mode:10s} raw={row['raw_cer']:.3f} | "
            f"off: cer={o['cer']:.3f} lo={o['cer_lo']:.3f} marks={o['marks']} conf={o['conf_min']:.2f} | "
            f"on: cer={n['cer']:.3f} lo={n['cer_lo']:.3f} marks={n['marks']} conf={n['conf_min']:.2f}"
        )

    out = Path(__file__).resolve().parent / "reports"
    out.mkdir(exist_ok=True)
    (out / "quran_yaseen.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
