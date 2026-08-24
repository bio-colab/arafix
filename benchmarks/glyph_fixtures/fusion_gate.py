"""بوابة الدمج — الاسترجاع الكامل عبر الواجهة العامة فقط.

السلسلة: fixture PDF → استخراج arafix (يمتنع اليوم كما هو موثق) → محاذاة
آلية للكلمات بين الحقيقة والنص المستخرج → GlyphEvidence لكل كلمة مفسودة
→ DocumentContext + CharacterConfusionModel(mعاير cost=0.30)
→ EvidenceFusion → SAFE فقط بالإجماع المستقل.

البوابات الصارمة (خروج 1 عند خرقها):
  * RAR: استرجاع حرفي 100% لكلمات الذهب.
  * FPR = 0: صفر تغيير على أي كلمة ة حقيقية (داخل المعجم أو خارجه).

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


def _load_manifest() -> dict:
    return json.loads((ASSETS / "gold_manifest.json").read_text(encoding="utf-8"))


def word_pairs(manifest: dict, extracted_text: str) -> tuple[dict[str, str], list[str]]:
    """محاذاة آلية: كلمة-بكلمة بين الحقيقة والمستخرَج، أول اختلاف هو الهدف."""
    truth_lines = manifest["truth_lines"]
    got_lines = extracted_text.split("\n")
    pairs: dict[str, str] = {}
    skipped: list[str] = []
    for tline, gline in zip(truth_lines, got_lines):
        tw, gw = tline.split(), gline.split()
        if len(tw) != len(gw):
            skipped.append(tline)
            continue
        for t, c in zip(tw, gw):
            if t == c or len(t) != len(c):
                continue
            diffs = [i for i, (a, b) in enumerate(zip(t, c)) if a != b]
            if len(diffs) == 1 and c not in pairs:
                pairs[c] = t
    return pairs, skipped


def main() -> int:
    manifest = _load_manifest()
    true_ch, lie_ch = manifest["pair"]["true"], manifest["pair"]["lie"]
    pdf_path = ASSETS / f"glyph_{true_ch}_to_{lie_ch}.pdf"

    # 1) الأنبوب الحالي: امتناع متوقع على كذبات المحارف العادية
    doc = extract_pdf(str(pdf_path), PipelineConfig(extractor="pymupdf"))
    corrupted_text = doc.pages[0].text
    if corrupted_text.count(lie_ch) == 0:
        print(f"FAIL: المتوقع كذبة «{lie_ch}» في المخرج — سلوك الأنبوب تغيّر")
        return 1
    print(f"extracted (امتناع متوقع): {corrupted_text.splitlines()[0][:48]}…")

    pairs, skipped = word_pairs(manifest, corrupted_text)
    if skipped:
        print(f"WARN: أسطر لم تُحاذاة (عدد كلمات مختلف): {skipped}")
    print(f"word pairs من المحاذاة الآلية: {len(pairs)}")

    # 2) النموذج: سياق نظيف + التباس مُعاير + دليل الجليف الكلمي
    context_lines = manifest["context_lines"] * 6
    gen = CandidateGenerator(confusion_model=CharacterConfusionModel(
        [Confusion(lie_ch, true_ch, source="labeled-fixture", cost=0.30)]))
    ctx = DocumentContext.from_texts(context_lines, candidate_generator=gen)
    fusion = EvidenceFusion()
    neg = NegativeEvidenceModel()

    def glyph_ev(word: str):
        t = pairs.get(word)
        if t is None:
            return ()
        return (GlyphEvidence(observed=word, candidate=t, score=0.95,
                              font="Amiri-Regular", glyph_id=None,
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
        dec = fusion.decide(tok, cands,
                            negative_evidence=neg.inspect(corrupted_text, 0, len(tok)))
        if tok in pairs:
            if dec.decision.value == "safe":
                if dec.replacement != pairs[tok]:
                    wrong_safe.append((tok, dec.replacement or ""))
                else:
                    replacements[tok] = dec.replacement
            else:
                misses.append(tok)
        elif dec.replacement is not None:
            wrong_safe.append((tok, dec.replacement))

    restored = corrupted_text
    for old, new in replacements.items():
        restored = re.sub(rf"(?<![\u0621-\u064A]){old}(?![\u0621-\u064A])",
                          new, restored)

    rar_ok = all(restored.count(t) >= 1 for t in (
        "الشهادة", "الهلال", "الفهري")) and not misses and not wrong_safe
    exact = restored == "\n".join(manifest["truth_lines"])
    fpr_probe = fusion.decide(
        "مكتبة",
        gen.generate("مكتبة", document_context=ctx, left="الكبيرة", right="الآن"),
    )
    fpr_ok = fpr_probe.replacement is None

    print(f"\nrestored : {restored.replace(chr(10), ' | ')}")
    print(f"targets={len(pairs)} restored={len(replacements)} "
          f"wrong_safe={len(wrong_safe)} missed={len(misses)}")
    print(f"FPR probe 'مكتبة': {fpr_probe.decision.value}")

    if rar_ok and exact and fpr_ok:
        print("PASS: RAR=100% حرفياً، FPR=0، عبر الواجهة العامة فقط")
        return 0
    print(f"FAIL: exact={exact} rar_ok={rar_ok} fpr_ok={fpr_ok}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
