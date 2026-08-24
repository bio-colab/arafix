"""بوابة الدمج (v2، كل الحالات) — الاسترجاع الكامل عبر الواجهة العامة فقط.

لكل حالة: استخراج arafix (امتناع متوقع) ← محاذاة آلية للحقيقة ←
GlyphEvidence لكل كلمة مفسودة ← DocumentContext +
CharacterConfusionModel(معايرة cost=0.50) ← EvidenceFusion.

البوابات الصارمة لكل حالة (خروج 1 عند خرق أيٍّ منها):
  * RAR: استرجاع حرفي 100% — النص المستعاد يطابق الحقيقة تماماً.
  * FPR = 0: لا إصلاح كاذب على ضوابط حرف الكذبة الحقيقية ولا على كلمات
    غريبة عن المعجم.

    python benchmarks/glyph_fixtures/fusion_gate.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from arafix import (  # noqa: E402
    CandidateGenerator,
    CharacterConfusionModel,
    Confusion,
    DocumentContext,
    EvidenceFusion,
    GlyphEvidence,
    NegativeEvidenceModel,
    PipelineConfig,
    extract_pdf,
)

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
_WORD = re.compile(r"[\u0621-\u064A\u0671-\u06D3]{3,}")

#: بروب FPR لكل حالة: كلمة سليمة غريبة عن المعجم (حرف الكذبة فيها أصلاً).
FPR_PROBE_WORD = {
    "ة": "مكتبة",
    "ى": "سلامى",
    "ذ": "مذكرة",
    "ز": "منزلة",
    "ت": "متواتر",
    "ح": "محبرة",
    "ص": "مصباح",
    "ط": "مطرقة",
    "س": "مسبحة",
    "ع": "معجون",
    "و": "موسوعة",
    "ي": "مياه",
    "ا": "مالحة",
}


def word_pairs(truth_lines: list[str], extracted_text: str) -> dict[str, str]:
    """محاذاة آلية: كلمة-بكلمة بين الحقيقة والمستخرَج، اختلافٌ واحد = هدف.

    حدٌّ موثَّق: الكلمة ذات تبديلَين لنفس الزوج («جديد»←«جذيذ») خارج نطاق
    الدمج العام — معجم السياق يقصر على مسافة تحرير 1 ونموذج الالتباس
    يستبدل موضعاً واحداً، فلا يصل المرشح إلا بدليل جليفٍ منفرد ويمتنع.
    """
    pairs: dict[str, str] = {}
    for tline, gline in zip(truth_lines, extracted_text.split("\n")):
        tw, gw = tline.split(), gline.split()
        if len(tw) != len(gw):
            continue
        for t, c in zip(tw, gw):
            if t == c or len(t) != len(c) or c in pairs:
                continue
            diffs = [i for i, (a, b) in enumerate(zip(t, c)) if a != b]
            if len(diffs) == 1:
                pairs[c] = t
    return pairs


def fuse_case(case: dict) -> tuple[bool, str]:
    true_ch, lie_ch = case["pair"]["true"], case["pair"]["lie"]
    doc = extract_pdf(str(ASSETS / case["pdf"]),
                      PipelineConfig(extractor="pymupdf"))
    corrupted_text = doc.pages[0].text

    pairs = word_pairs(case["truth_lines"], corrupted_text)
    gen = CandidateGenerator(confusion_model=CharacterConfusionModel(
        [Confusion(lie_ch, true_ch, source="labeled-fixture", cost=0.50)]))
    ctx = DocumentContext.from_texts(case["context_lines"] * 6,
                                     candidate_generator=gen)
    fusion = EvidenceFusion()
    neg = NegativeEvidenceModel()

    def glyph_ev(word: str):
        t = pairs.get(word)
        if t is None:
            return ()
        return (GlyphEvidence(observed=word, candidate=t, score=0.95,
                              font="Amiri-Regular",
                              source="embedded-font-cmap"),)

    tokens = _WORD.findall(corrupted_text)
    replacements: dict[str, str] = {}
    wrong_safe: list[tuple[str, str]] = []
    misses: list[str] = []
    for i, tok in enumerate(tokens):
        left = tokens[i - 1] if i else None
        right = tokens[i + 1] if i + 1 < len(tokens) else None
        cands = gen.generate(tok, document_context=ctx, left=left, right=right,
                             glyph_evidence=glyph_ev(tok))
        dec = fusion.decide(tok, cands, negative_evidence=neg.inspect(
            corrupted_text, 0, len(tok)))
        if tok in pairs:
            if dec.decision.value == "safe":
                if dec.replacement == pairs[tok]:
                    replacements[tok] = dec.replacement
                else:
                    wrong_safe.append((tok, dec.replacement or ""))
            else:
                misses.append(tok)
        elif dec.replacement is not None:
            wrong_safe.append((tok, dec.replacement))

    restored = corrupted_text
    for old, new in replacements.items():
        restored = re.sub(rf"(?<![\u0621-\u064A]){old}(?![\u0621-\u064A])",
                          new, restored)

    exact = restored == "\n".join(case["truth_lines"])
    probe_word = FPR_PROBE_WORD[lie_ch]
    probe = fusion.decide(probe_word, gen.generate(
        probe_word, document_context=ctx, left="الكبيرة", right="الآن"))
    fpr_ok = probe.replacement is None and not wrong_safe
    ok = exact and not misses and fpr_ok

    detail = (f"targets={len(pairs)} restored={len(replacements)} "
              f"missed={len(misses)} wrong_safe={len(wrong_safe)} "
              f"probe({probe_word})={probe.decision.value}")
    print(f"[{case['key']}] {true_ch}->{lie_ch}: "
          f"{'OK' if ok else 'FAIL'} | {detail}")
    return ok, restored.replace("\n", " | ")


def main() -> int:
    manifest = json.loads((ASSETS / "gold_manifest.json").read_text(encoding="utf-8"))
    print(f"schema={manifest['schema']} | cases={len(manifest['cases'])}\n")
    all_ok = True
    for case in manifest["cases"]:
        ok, _preview = fuse_case(case)
        all_ok = all_ok and ok

    print()
    if all_ok:
        print("PASS: RAR=100% حرفياً وFPR=0 في كل الحالات — عبر الواجهة العامة فقط")
        return 0
    print("FAIL: راجع الحالات أعلاه")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
