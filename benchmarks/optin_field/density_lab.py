"""الميدان 3 — مختبر confidence_mode="density" على نص قانوني حقيقي.

يبني صفحات بطولٍ وكثافةِ مشتبهاتٍ متحكَّمَبهما (حقن لا→ال بمعدل ثابت)،
ويقيس ثقة الوضعين classic/density مع عدّادات lam-alef الخام، ويؤكد:

  * النص متطابق بين الوضعين دائماً (density شهادةٌ فقط) — خروج 1 خلاف ذلك.
  * W6 كمّياً: classic تعاقب بنفس الشدة صرفاً عن طول الصفحة وكثافتها
    (0.35 المسطحة)، وdensity تنسجم مع الكثافة وتحمي الصفحات الطويلة.

    python benchmarks/optin_field/density_lab.py
"""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from arafix import PipelineConfig, repair_text  # noqa: E402
from arafix.lamalef import repair_lam_alef_transposition  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SEED = 7


def corpus_words() -> tuple[list[str], list[str]]:
    src = REPO / "tests/fixtures/real_pdf_narrative/iraq_constitution_original.txt"
    text = src.read_text(encoding="utf-8-sig")
    words = [w.strip("،.؛:()«»") for w in text.split()]
    words = [w for w in words if len(w) >= 3 and all("\u0600" <= c <= "\u06FF" for c in w)]
    la_words = sorted({w for w in words if "لا" in w})
    return words, la_words


def make_page(rng: random.Random, words: list[str], la_words: list[str],
              n_words: int, n_suspects: int, decisive: bool) -> str:
    ws = [rng.choice(words) for _ in range(n_words)]
    idxs = rng.sample(range(n_words), min(n_suspects, n_words))
    for i in idxs:
        ws[i] = rng.choice(la_words).replace("لا", "ال", 1)
    if decisive:
        ws[n_words // 2] = "االنترنيت"
    return " ".join(ws)


def counters(res) -> tuple[int, int]:
    """يقرأ عدّادَي lam-alef من ملاحظات التقرير (صيغتا pipeline الموثقتان):
    حاسم: «رُدَّ N انقلابَ لام-ألف بشاهدٍ قاطع» · معجم: «وحُسم N موضعاً…».
    """
    joined = " ".join(res.notes)
    dec = re.search(r"رُدَّ\s*(\d+)\s*انقلاب", joined)
    lex = re.search(r"(\d+)\s*موضع\S*\s*مُبهَماً", joined) or re.search(
        r"حُسم\s*(\d+)\s*مُبهَم", joined
    )
    return (int(dec.group(1)) if dec else 0,
            int(lex.group(1)) if lex else 0)


def main() -> int:
    words, la_words = corpus_words()
    rng = random.Random(SEED)
    print(f"corpus words={len(words)} | la-bearing unique={len(la_words)}\n")

    cases = [
        ("long/sparse 300w/3s", 300, 3),
        ("short/dense 30w/3s", 30, 3),
        ("long/dense 300w/25s", 300, 25),
    ]
    print(f"{'case':24} {'fix?':>5} | {'classic':>7} {'density':>7} | "
          f"{'dec':>3} {'lex':>3} {'left':>4} | text_eq")
    rows = []
    all_equal = True
    for label, n_words, n_suspects in cases:
        for decisive in (True, False):
            page = make_page(rng, words, la_words, n_words, n_suspects, decisive)
            rc = repair_text(page, PipelineConfig(extractor="pymupdf"))
            rd = repair_text(page, PipelineConfig(
                extractor="pymupdf", confidence_mode="density"))
            equal = rc.text == rd.text
            all_equal = all_equal and equal
            dec_c, lex_c = counters(rc)
            left = repair_lam_alef_transposition(rc.text).suspects_left
            rows.append((label, decisive, rc.confidence, rd.confidence))
            print(f"{label:24} {str(decisive):>5} | {rc.confidence:>7} "
                  f"{rd.confidence:>7} | {dec_c:>3} {lex_c:>3} {left:>4} | {equal}")

    print("\n=== W6: أثر إصلاحٍ عرضيٍّ واحد على شهادة الثقة ===")
    by_label: dict[str, dict[bool, tuple[float, float]]] = {}
    for label, decisive, cc, dc in rows:
        by_label.setdefault(label, {})[decisive] = (cc, dc)
    for label, modes in by_label.items():
        cc_fix, dc_fix = modes[True]
        cc_nofix, dc_nofix = modes[False]
        print(f"{label:24} classic(fix/nofix)={cc_fix}/{cc_nofix} "
              f"density(fix/nofix)={dc_fix}/{dc_nofix}")

    print()
    if not all_equal:
        print("FAIL: اختلاف نصي بين الوضعين — density يجب أن تبقى شهادةً فقط")
        return 1
    print("PASS: النص ثابت عبر الوضعين في كل الحالات")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
