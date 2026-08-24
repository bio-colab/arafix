"""الميدان 2-تشخيص — لماذا يفوت الإنقاذ أحياناً؟ تصنيف كمّي لأسباب الفوت.

لكل سطرٍ من النثر الحقيقي يُعكس بمحاكاة صادقة ثم يُصنَّف:
  below_threshold            درجته لم تجتز بوابة visual_order
  insufficient_sample_no_proof  اجتاز العتبة لكن لا برهان وصل والعينة قصيرة
  fix_order_not_exact        كُشف واجتاز البوابات لكن الاستعادة ليست حرفية
  rescued                    اكتُشف واستُعيد حرفياً

النتيجة المرجعية: الكشف ليس الاختناق (42/43 فوق العتبة)؛ الفوت غالباً
دقة استعادة `fix_order` للسطر المعزول.

    python benchmarks/optin_field/diagnose_misses.py
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from arafix import PipelineConfig, repair_text, reverse_visual_line  # noqa: E402
from arafix.order import fix_order  # noqa: E402
from arafix.pipeline import DEFAULT_THRESHOLDS, _line_reversal_score  # noqa: E402
from arafix.unicode_tables import is_arabic, is_presentation_form  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def load_lines(path: Path, want: int) -> list[str]:
    txt = path.read_text(encoding="utf-8-sig")
    lines = [ln.strip() for ln in txt.splitlines()]
    return [ln for ln in lines if len(ln.split()) >= 5][:want]


def main() -> int:
    golds = REPO / "benchmarks/wiki_eval/articles"
    sources = {
        name: load_lines(golds / f"{name}.gold.txt", 24)
        for name in ("human-rights", "ibn-sina", "aljabr")
    }
    thr = DEFAULT_THRESHOLDS["visual_order"]
    min_ar = DEFAULT_THRESHOLDS.get("min_arabic_chars", 0)
    print(f"thresholds: visual_order>{thr} min_arabic_chars={min_ar}\n")

    reasons = {
        "below_threshold": 0,
        "insufficient_sample_no_proof": 0,
        "fix_order_not_exact": 0,
        "rescued": 0,
    }
    scores: list[float] = []

    for lines in sources.values():
        for ln in lines:
            rev = reverse_visual_line(ln)
            score, evs = _line_reversal_score(rev)
            scores.append(score)
            proof = any(e.name == "joining_forms" and e.value > 0 for e in evs)
            n_ar = sum(1 for c in ln if is_arabic(c) or is_presentation_form(c))
            if score <= thr:
                reasons["below_threshold"] += 1
                continue
            if not proof and n_ar < min_ar:
                reasons["insufficient_sample_no_proof"] += 1
                continue
            restored = fix_order(rev)
            canonical = repair_text(ln, PipelineConfig(extractor="pymupdf")).text
            if restored in (canonical, ln):
                reasons["rescued"] += 1
            else:
                reasons["fix_order_not_exact"] += 1

    total = sum(reasons.values())
    print("=== تصنيف أسباب الفوت ===")
    for key, count in reasons.items():
        print(f"  {key:30} {count:>3} ({count / total:.0%})")
    above = sum(1 for s in scores if s > thr)
    print(f"\nscores: min={min(scores):+.2f} "
          f"median={statistics.median(scores):+.2f} max={max(scores):+.2f}")
    print(f"above default threshold ({thr}): {above}/{len(scores)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
