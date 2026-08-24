"""الميدان 4 — الأداء والعمى الموثَّق.

(أ) زمن repair_text على مستند مختلط 35K محرف: افتراضي مقابل rescue ON،
    مع التحقق أن سطر الترويسة المحقون يُستعاد حرفياً.
(ب) بروب عمى نمط «رقم:»: سطر يبدأ برقمٍ عربيٍّ ثم نقطتين يسجل ‎+0.000 في
    detect_visual_order — البوابة تمرره بلا إنقاذ (تحفظٌ موثَّق لا عطل).

    python benchmarks/optin_field/perf_and_blindspots.py [--bench-iters 5]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from arafix import PipelineConfig, repair_text, reverse_visual_line  # noqa: E402
from arafix.pipeline import DEFAULT_THRESHOLDS, _line_reversal_score  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def numeral_blindspot_probe() -> None:
    src = REPO / "tests/fixtures/real_pdf_narrative/iraq_constitution_original.txt"
    text = src.read_text(encoding="utf-8-sig")
    line = next(
        (ln.strip() for ln in text.splitlines() if ln.strip().startswith("٢")),
        None,
    )
    print("=== (أ) عمى نمط «رقم:» ===")
    if line is None:
        print("  (لم يُوجد سطر يبدأ بـ٢ في الـfixture — تخطٍ)")
        return
    rev = reverse_visual_line(line)
    score, _evs = _line_reversal_score(rev)
    thr = DEFAULT_THRESHOLDS["visual_order"]
    print(f"orig : {line[:64]}…")
    print(f"score={score:+.3f} vs threshold>{thr} -> "
          f"{'DETECTED' if score > thr else 'BLIND SPOT (conservative pass)'}")


def bench(args) -> None:
    src = REPO / "tests/fixtures/real_pdf_narrative/iraq_constitution_original.txt"
    body = [ln.strip() for ln in src.read_text(encoding="utf-8-sig").splitlines()
            if len(ln.split()) >= 5][:220]
    page = "\n".join(body)
    while len(page) < 35_000:
        page = page + "\n" + "\n".join(body)
    lines = page.split("\n")
    mixed = list(lines)
    mixed[3] = reverse_visual_line(mixed[3])
    mixed_txt = "\n".join(mixed)

    def once(rescue: bool) -> float:
        best = float("inf")
        for _ in range(args.bench_iters):
            t0 = time.perf_counter()
            repair_text(mixed_txt, PipelineConfig(
                extractor="pymupdf", rescue_mixed_lines=rescue))
            best = min(best, time.perf_counter() - t0)
        return best

    print(f"\n=== (ب) الأداء على {len(mixed_txt):,} محرفاً مختلطاً ===")
    t_off = once(False)
    t_on = once(True)
    r_on = repair_text(mixed_txt, PipelineConfig(
        extractor="pymupdf", rescue_mixed_lines=True))
    r_base = repair_text(page, PipelineConfig(extractor="pymupdf"))
    restored = r_on.text.split("\n")[3] == r_base.text.split("\n")[3]
    print(f"default  : {t_off * 1000:8.1f} ms")
    print(f"rescue ON: {t_on * 1000:8.1f} ms ({(t_on / t_off - 1) * 100:+.1f}%)")
    print(f"header line restored exactly: {restored}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-iters", type=int, default=3)
    args = parser.parse_args()
    numeral_blindspot_probe()
    bench(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
