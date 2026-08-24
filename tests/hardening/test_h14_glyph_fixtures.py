"""H14 — ميدان Glyph Evidence المُعنون (v2): أربع حالات مُعنونة.

يثبّت أدلة benchmarks/glyph_fixtures/ لكل حالة من حالات الذهب
(arafix.glyph-fixture.v2):

* كشف حتمي دقيق: كل جليفٍ مرسومٍ حقيقتُه حرفُ الحقيقة يتناقض مع طبقة
  النص، وصفر تناقض خارج الذهب.
* التحفظ الحالي: extract_pdf لا يصلح كذبات المحارف العادية تلقائياً —
  كلمةٌ مفسودةٌ محددة تبقى في المخرج (تثبيتٌ يُحدَّث بقرار موثق).
* سلسلة الدمج عبر الواجهة العامة فقط تسترجع كل هدفٍ حرفياً بصفر إصلاح
  كاذب وامتناعٍ على البروب الخارجي للمعجم.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from arafix import (
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
from arafix.cmap import build_glyph_map
from arafix.unicode_tables import PF_TO_BASE

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "benchmarks" / "glyph_fixtures" / "assets"
_WORD = re.compile(r"[\u0621-\u064A\u0671-\u06D3]{3,}")

#: بروب FPR لكل زوج: كلمة سليمة غريبة عن معجم الحالة.
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


def _normalize(ch: str) -> str:
    return PF_TO_BASE.get(ch, ch)


def _manifest() -> dict:
    return json.loads((FIXTURES / "gold_manifest.json").read_text(encoding="utf-8"))


_CASES = _manifest()["cases"]
_CASE_IDS = [c["key"] for c in _CASES]

pytestmark = pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)


def _word_pairs(truth_lines: list[str], extracted_text: str) -> dict[str, str]:
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


def test_gold_conflicts_are_exactly_the_painted_truth_glyphs(case) -> None:
    import fitz

    doc = fitz.open(FIXTURES / case["pdf"])
    page = doc[0]
    font_xref = doc.get_page_fonts(0)[0][0]
    name, _ext, _t, data = doc.extract_font(font_xref)
    gm = build_glyph_map(data, name)

    reported: dict[int, set[str]] = {}
    for span in page.get_texttrace():
        if span.get("type") != 0:
            continue
        for uni, gid, _origin, _bbox in span["chars"]:
            reported.setdefault(gid, set()).add(chr(uni))

    true_ch = case["pair"]["true"]
    conflicts: set[int] = set()
    painted_truth_gids: set[int] = set()
    for gid, chars in reported.items():
        truth = gm.lookup_id(gid)
        if truth is None or len(truth) != 1:
            continue
        if _normalize(truth) == true_ch:
            painted_truth_gids.add(gid)
        if any(_normalize(ch) != _normalize(truth) for ch in chars):
            assert _normalize(truth) == true_ch, f"تناقض خارج الذهب gid={gid}"
            conflicts.add(gid)

    assert conflicts == painted_truth_gids, "الكشف ليس حتمياً بالضبط"
    assert conflicts, f"لا تناقضات في {case['key']} — الـfixture تغيّر؟"


def test_pipeline_abstains_on_normal_character_lies(case) -> None:
    """التثبيت المحافظ: كلمةٌ مفسودةٌ محددة تبقى في مخرج الأنبوب كما هي."""
    true_ch, lie_ch = case["pair"]["true"], case["pair"]["lie"]
    doc = extract_pdf(str(FIXTURES / case["pdf"]),
                      PipelineConfig(extractor="pymupdf"))
    text = doc.pages[0].text

    truth_text = "\n".join(case["truth_lines"])
    assert text != truth_text, f"[{case['key']}] المخرج مطابق للحقيقة رغم الفساد؟"

    target_word = next(
        w for ln in case["truth_lines"] for w in ln.split() if true_ch in w
    )
    corrupted_word = target_word.replace(true_ch, lie_ch)
    assert corrupted_word in text, (
        f"[{case['key']}] الكذبة «{corrupted_word}» لم تعد تظهر — "
        "سلوك الأنبوب تغيّر؛ حدّث التثبيت بقرار موثق")


def test_public_api_fusion_restores_gold_exactly_with_zero_fpr(case) -> None:
    true_ch, lie_ch = case["pair"]["true"], case["pair"]["lie"]
    doc = extract_pdf(str(FIXTURES / case["pdf"]),
                      PipelineConfig(extractor="pymupdf"))
    corrupted_text = doc.pages[0].text
    pairs = _word_pairs(case["truth_lines"], corrupted_text)
    assert pairs, f"[{case['key']}] لا أهداف محاذاة"

    gen = CandidateGenerator(confusion_model=CharacterConfusionModel(
        [Confusion(lie_ch, true_ch, source="labeled-fixture", cost=0.50)]))
    ctx = DocumentContext.from_texts(case["context_lines"] * 6,
                                     candidate_generator=gen)
    fusion = EvidenceFusion()
    neg = NegativeEvidenceModel()

    tokens = _WORD.findall(corrupted_text)
    replacements: dict[str, str] = {}
    wrong_safe: list[tuple[str, str]] = []
    misses: list[str] = []
    for i, tok in enumerate(tokens):
        left = tokens[i - 1] if i else None
        right = tokens[i + 1] if i + 1 < len(tokens) else None
        evs = ()
        if tok in pairs:
            evs = (GlyphEvidence(observed=tok, candidate=pairs[tok], score=0.95,
                                 font="Amiri-Regular",
                                 source="embedded-font-cmap"),)
        cands = gen.generate(tok, document_context=ctx, left=left, right=right,
                             glyph_evidence=evs)
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

    assert restored == "\n".join(case["truth_lines"]), \
        f"[{case['key']}] الاسترجاع ليس حرفياً: {restored!r}"
    assert not misses and not wrong_safe, \
        f"[{case['key']}] RAR<100% أو إصلاح كاذب"

    probe_word = FPR_PROBE_WORD[lie_ch]
    probe = fusion.decide(probe_word, gen.generate(
        probe_word, document_context=ctx, left="الكبيرة", right="الآن"))
    assert probe.replacement is None, \
        f"[{case['key']}] إصلاح كاذب على «{probe_word}»"
