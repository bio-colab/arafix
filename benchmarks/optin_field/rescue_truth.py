"""الميدان 2 — أرضية حقيقة معلومة لـrescue_mixed_lines.

يُحقن سطرٌ معكوسٌ واحد (في منتصف الصفحة) عبر `reverse_visual_line` — المحاكاة
الصادقة للتخزين البصري: جزر LTR بترتيبها، أقواس مرآة، عناقيد محفوظة (لا
`[::-1]` الساذج الذي يولد أنماطاً لا تحدث في الواقع).

البوابة الصارمة: صفر تغيير على أي سطرٍ نظيف. دقة الاسترجاع تُطبع للمتابعة.

    python benchmarks/optin_field/rescue_truth.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from arafix import PipelineConfig, repair_text, reverse_visual_line  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
BASE = {"extractor": "pymupdf"}


def load_lines(path: Path, want: int) -> list[str]:
    txt = path.read_text(encoding="utf-8-sig")
    lines = [ln.strip() for ln in txt.splitlines()]
    return [ln for ln in lines if len(ln.split()) >= 5][:want]


def sources() -> dict[str, list[str]]:
    golds = REPO / "benchmarks/wiki_eval/articles"
    out = {
        "human-rights": load_lines(golds / "human-rights.gold.txt", 24),
        "ibn-sina": load_lines(golds / "ibn-sina.gold.txt", 24),
        "aljabr": load_lines(golds / "aljabr.gold.txt", 24),
        "relativity": load_lines(golds / "relativity.gold.txt", 24),
    }
    const = REPO / "tests/fixtures/real_pdf_narrative/iraq_constitution_original.txt"
    if const.exists():
        out["constitution"] = load_lines(const, 32)
    return {k: v for k, v in out.items() if len(v) >= 8}


def make_pages(lines: list[str], per_page: int = 8) -> list[list[str]]:
    return [lines[i:i + per_page]
            for i in range(0, max(0, len(lines) - per_page + 1), per_page)]


def main() -> int:
    print(f"{'source':14} {'pages':>5} {'targets':>7} {'rescued':>7} "
          f"{'missed':>6} {'false':>5}")
    grand = {"t": 0, "r": 0, "fp": 0}
    miss_samples: list[tuple[str, str, str]] = []

    for sname, lines in sources().items():
        pages = make_pages(lines)
        for page in pages:
            mid = len(page) // 2
            corrupted = list(page)
            corrupted[mid] = reverse_visual_line(page[mid])

            baseline = repair_text("\n".join(page), PipelineConfig(**BASE))
            rescued = repair_text("\n".join(corrupted), PipelineConfig(
                rescue_mixed_lines=True, **BASE))

            base_lines = baseline.text.split("\n")
            got_lines = rescued.text.split("\n")
            if len(base_lines) != len(got_lines):
                grand["fp"] += abs(len(base_lines) - len(got_lines))
                continue
            for i, (got, want) in enumerate(zip(got_lines, base_lines)):
                if i == mid:
                    grand["t"] += 1
                    if got == want:
                        grand["r"] += 1
                    else:
                        miss_samples.append((sname, want[:48], got[:48]))
                elif got != want:
                    grand["fp"] += 1
        print(f"{sname:14} {len(pages):>5} {grand['t']:>7} {grand['r']:>7} "
              f"{grand['t'] - grand['r']:>6} {grand['fp']:>5}")

    t, r, fp = grand["t"], grand["r"], grand["fp"]
    rate = (r / t) if t else float("nan")
    print(f"\nTOTAL: targets={t} rescued_exact={r} (rate={rate:.1%}) "
          f"false_touches={fp}")
    if miss_samples:
        print("\nعينات الفوات (للتشخيص؛ انظر diagnose_misses.py):")
        for sname, want, got in miss_samples[:3]:
            print(f"  [{sname}]\n    want: {want}…\n    got : {got}…")

    if fp:
        print("\nFAIL: ضرر جانبي على أسطر نظيفة — غير مقبول")
        return 1
    print("PASS: صفر ضرر جانبي على كل الأسطر النظيفة")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
