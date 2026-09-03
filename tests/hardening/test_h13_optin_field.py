"""H13 — ميدان الميزات الاختيارية: أمان opt-in والعمى الموثَّق.

يثبّت الأدلة المقيسة لحملة الميدان (benchmarks/optin_field/):

* نص المدونات النظيفة متطابق بايت-ببايت عبر كل أوضاع opt-in.
* rescue_mixed_lines يسترجع السطر المعكوس المحقون حرفياً بلا أي مساس
  جانبي، ويسجل قاعدته في التقرير.
* confidence_mode=density شهادةٌ فقط: النص ثابت دائماً، ويعالج عدم تماثل
  W6 كمّياً (classic تسحق الثقة إلى 0.35 صرفاً عن الكثافة).
* العمى الموثَّق يبقى محافظاً حتى يُقرر غير ذلك صراحةً:
    - نمط «رقم:» في رأس السطر يسجل تحت العتبة فلا يُنقذ (لا يُمسّ أيضاً).
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

import pytest

from arafix import PipelineConfig, extract_pdf, repair_text, reverse_visual_line
from arafix.pipeline import DEFAULT_THRESHOLDS, _line_reversal_score

REPO = Path(__file__).resolve().parents[2]
BASE = {"extractor": "pymupdf"}

PDF_SUBSET = [
    REPO / "benchmarks/wiki_eval/pdfs/human-rights.clean.pdf",
    REPO / "benchmarks/wiki_eval/pdfs/salahaddin.clean.pdf",
]
OPTIN_CFGS: dict[str, dict] = {
    "default": {},
    "rescue": {"rescue_mixed_lines": True},
    "density": {"confidence_mode": "density"},
    "both": {"rescue_mixed_lines": True, "confidence_mode": "density"},
}


def _gold_lines(name: str, want: int) -> list[str]:
    txt = (REPO / f"benchmarks/wiki_eval/articles/{name}.gold.txt").read_text(
        encoding="utf-8-sig")
    lines = [ln.strip() for ln in txt.splitlines()]
    return [ln for ln in lines if len(ln.split()) >= 5][:want]


def test_optin_modes_leave_clean_corpus_byte_identical() -> None:
    for pdf in PDF_SUBSET:
        if not pdf.exists():
            pytest.skip(f"Benchmark PDF not found: {pdf}")
        shas = set()
        for extra in OPTIN_CFGS.values():
            doc = extract_pdf(str(pdf),
                              PipelineConfig(extractor="pymupdf", **extra))
            shas.add(hashlib.sha256(doc.text.encode("utf-8")).hexdigest())
        assert len(shas) == 1, f"نص مختلف بين الأوضاع على {pdf.name}"


def test_rescue_restores_injected_line_exactly_with_provenance() -> None:
    page = _gold_lines("human-rights", 8)
    assert len(page) == 8
    mid = 4
    corrupted = list(page)
    corrupted[mid] = reverse_visual_line(page[mid])

    baseline = repair_text("\n".join(page),
                           PipelineConfig(audit_mode="summary", **BASE))
    rescued = repair_text("\n".join(corrupted), PipelineConfig(
        audit_mode="summary", rescue_mixed_lines=True, **BASE))

    want_lines = baseline.text.split("\n")
    got_lines = rescued.text.split("\n")
    assert len(got_lines) == len(want_lines)
    for i, (got, want) in enumerate(zip(got_lines, want_lines)):
        if i == mid:
            assert got == want, "السطر المعكوس لم يُستعَد حرفياً"
        else:
            assert got == want, f"ضرر جانبي على سطر نظيف ({i})"

    rules = {event.rule for event in rescued.audit.events}
    assert "MIXED_LINE_RESCUE" in rules, "الإنقاذ بلا شهادة تقرير"


def test_density_mode_changes_testimony_not_text() -> None:
    words = [w for w in (
        w.strip("،.؛:()«»") for w in (
            REPO / "tests/fixtures/real_pdf_narrative/"
            "iraq_constitution_original.txt").read_text(
                encoding="utf-8-sig").split()
    ) if len(w) >= 3 and all("\u0600" <= c <= "\u06FF" for c in w)]
    la_words = sorted({w for w in words if "لا" in w})
    rng = random.Random(7)

    def make_long_sparse_page() -> str:
        ws = [rng.choice(words) for _ in range(300)]
        for i in rng.sample(range(300), 3):
            ws[i] = rng.choice(la_words).replace("لا", "ال", 1)
        ws[150] = "االنترنيت"  # إصلاحٌ عرضي واحد يفعّل عقوبة classic
        return " ".join(ws)

    page = make_long_sparse_page()
    classic = repair_text(page, PipelineConfig(extractor="pymupdf"))
    density = repair_text(page, PipelineConfig(
        extractor="pymupdf", confidence_mode="density"))

    assert classic.text == density.text, "density غيّرت النص!"
    # W6+W4: classic تسحق الثقة إلى الحد الأدنى صرفاً عن الطول،
    # وdensity تحفظ شهادة نسبية أعلى بكثير على الصفحة الطويلة الخفيفة.
    assert classic.confidence <= 0.36
    assert density.confidence >= 0.80
    assert density.confidence > classic.confidence


def test_known_blindspot_numeral_line_is_conservatively_untouched() -> None:
    const = (REPO / "tests/fixtures/real_pdf_narrative/"
             "iraq_constitution_original.txt").read_text(encoding="utf-8-sig")
    numeral_line = next(
        (ln.strip() for ln in const.splitlines() if ln.strip().startswith("٢")),
        None)
    assert numeral_line is not None, "fixture الدستور تغيّر: لا سطر «٢:»"

    rev = reverse_visual_line(numeral_line)
    score, _evs = _line_reversal_score(rev)
    thr = DEFAULT_THRESHOLDS["visual_order"]
    # العمى الموثَّق: الدرجة تحت العتبة فتمر البوابة محافظةً. إن أُصلح
    # الكشف مستقبلاً فهذا الاختبار أول من يجب تحديثه قراراً موثقاً.
    assert score <= thr, "الكشف تغيّر — حدّث هذا التثبيت بقرار موثق"

    page_lines = _gold_lines("salahaddin", 8)
    truncated = numeral_line[:120]
    page_lines[2] = truncated
    corrupted = list(page_lines)
    corrupted[2] = reverse_visual_line(truncated)

    default_out = repair_text("\n".join(corrupted), PipelineConfig(**BASE)).text
    rescue_out = repair_text("\n".join(corrupted), PipelineConfig(
        rescue_mixed_lines=True, **BASE)).text
    assert default_out == rescue_out, (
        "سلوك الإنقاذ تجاه العمى الرقمي تغيّر دون تحديث التثبيت")
