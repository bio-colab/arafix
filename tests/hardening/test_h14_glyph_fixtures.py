"""H14 — ميدان Glyph Evidence المُعنون: الإشارة والدمج والتحفظ.

يثبّت أدلة benchmarks/glyph_fixtures/ (الـfixture المولَّد بفساد ToUnicode
مُصنَّع، والذهب gold_manifest.json):

* كشف حتمي دقيق: كل جليفٍ مرسومٍ حقيقتُه «ه» يتناقض مع طبقة النص،
  وصفر تناقض خارج الذهب.
* التحفظ الحالي: extract_pdf لا يصلح كذبات المحارف العادية تلقائياً —
  الكذبة تبقى في المخرج (تثبيتٌ يُحدَّث بقرار موثق عند تفعيل الطبقة).
* سلسلة الدمج عبر الواجهة العامة فقط تسترجع الذهب حرفياً 100% بصفر
  إصلاح كاذب.
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


def _manifest() -> dict:
    return json.loads((FIXTURES / "gold_manifest.json").read_text(encoding="utf-8"))


def _normalize(ch: str) -> str:
    return PF_TO_BASE.get(ch, ch)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return _manifest()


def test_gold_conflicts_are_exactly_the_painted_truth_glyphs(manifest) -> None:
    import fitz

    pdf = FIXTURES / (
        f"glyph_{manifest['pair']['true']}_to_{manifest['pair']['lie']}.pdf")
    doc = fitz.open(pdf)
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

    true_ch = manifest["pair"]["true"]
    conflicts, painted_truth_gids = set(), set()
    for gid, chars in reported.items():
        truth = gm.lookup_id(gid)
        if truth is None or len(truth) != 1:
            continue
        is_truth_glyph = _normalize(truth) == true_ch
        if is_truth_glyph:
            painted_truth_gids.add(gid)
        if any(_normalize(ch) != _normalize(truth) for ch in chars):
            assert is_truth_glyph, f"تناقض خارج الذهب على gid={gid}"
            conflicts.add(gid)

    assert conflicts == painted_truth_gids, "الكشف ليس حتمياً بالضبط"
    assert conflicts, "لا تناقضات مكتشفة — الـfixture تغيّر؟"


def test_pipeline_abstains_on_normal_character_lies(manifest) -> None:
    """التثبيت المحافظ: الأنبوب اليوم لا يخترع إصلاحاً من شكل الجليف.

    كلمةٌ مفسودةٌ محددة («الةلال» من «الهلال») تبقى في المخرج كما هي.
    عند تفعيل طبقة Glyph Evidence داخل الأنبوب مستقبلاً، يُحدَّث هذا
    التثبيت بقرار موثق في CHANGELOG.
    """
    lie_ch = manifest["pair"]["lie"]
    pdf = FIXTURES / f"glyph_{manifest['pair']['true']}_to_{lie_ch}.pdf"
    doc = extract_pdf(str(pdf), PipelineConfig(extractor="pymupdf"))
    text = doc.pages[0].text

    truth_text = "\n".join(manifest["truth_lines"])
    assert text != truth_text, "المخرج مطابق للحقيقة رغم الفساد؟"
    # كذبةٌ محددة بالاسم لا مجرد عدّاد — أي إصلاحٍ جزئيٍّ يكسر التثبيت
    # فيستحق مراجعة قرار.
    corrupted_word = manifest["truth_lines"][1].split()[0].replace(
        manifest["pair"]["true"], lie_ch)
    assert corrupted_word in text, (
        f"الكذبة «{corrupted_word}» لم تعد تظهر — سلوك الأنبوب تغيّر")


def test_public_api_fusion_restores_gold_exactly_with_zero_fpr(manifest) -> None:
    true_ch, lie_ch = manifest["pair"]["true"], manifest["pair"]["lie"]
    pdf = FIXTURES / f"glyph_{true_ch}_to_{lie_ch}.pdf"
    corrupted_text = extract_pdf(
        str(pdf), PipelineConfig(extractor="pymupdf")).pages[0].text

    pairs: dict[str, str] = {}
    for tline, gline in zip(manifest["truth_lines"], corrupted_text.split("\n")):
        tw, gw = tline.split(), gline.split()
        if len(tw) != len(gw):
            continue
        for t, c in zip(tw, gw):
            if t != c and len(t) == len(c):
                diffs = [i for i, (a, b) in enumerate(zip(t, c)) if a != b]
                if len(diffs) == 1 and c not in pairs:
                    pairs[c] = t
    assert pairs, "لا أهداف محاذاة"

    gen = CandidateGenerator(confusion_model=CharacterConfusionModel(
        [Confusion(lie_ch, true_ch, source="labeled-fixture", cost=0.30)]))
    ctx = DocumentContext.from_texts(manifest["context_lines"] * 6,
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
                                 font=manifest["font"].split()[0],
                                 source="embedded-font-cmap"),)
        cands = gen.generate(tok, document_context=ctx, left=left, right=right,
                             glyph_evidence=evs)
        dec = fusion.decide(tok, cands,
                            negative_evidence=neg.inspect(corrupted_text, 0, len(tok)))
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

    assert restored == "\n".join(manifest["truth_lines"]), \
        f"الاسترجاع ليس حرفياً: {restored!r}"
    assert not misses and not wrong_safe, "RAR<100% أو إصلاح كاذب"

    # FPR: كلمة ة حقيقية غريبة عن المعجم بلا دليل جليف تبقى كما هي.
    probe = fusion.decide("مكتبة", gen.generate(
        "مكتبة", document_context=ctx, left="الكبيرة", right="الآن"))
    assert probe.replacement is None, "إصلاح كاذب على كلمة سليمة"
