"""
اختبار التكامل — دورة مغلقة على ملف PDF حقيقي.

نولّد ملفاً معطوباً بالمولّد نفسه، ثم نستخرجه بالمكتبة، ثم نطالب بأن
يعود النص كما بدأ. هذه أصدق شهادةٍ ممكنة دون ملفاتٍ حقيقية.

يُتخطّى تلقائياً إن غاب PyMuPDF أو غاب خطٌّ عربيّ — لا يُكسر البناء.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

from arafix import extract_pdf  # noqa: E402
from arafix.extractors import PyMuPDFExtractor  # noqa: E402

pytestmark = pytest.mark.skipif(
    not PyMuPDFExtractor.available(), reason="PyMuPDF غير مثبَّت"
)


@pytest.fixture(scope="module")
def broken_pdf(tmp_path_factory):
    make = pytest.importorskip("make_broken_pdf")
    try:
        font = make.find_font()
    except SystemExit:
        pytest.skip("لا خطّ عربيّ في هذه البيئة")
    path = tmp_path_factory.mktemp("pdf") / "broken.pdf"
    make.build(str(path), font)
    return str(path)


def test_raw_extraction_is_actually_broken(broken_pdf):
    """
    نتحقق أولاً أن الملف **معطوبٌ فعلاً**.

    بدون هذا الاختبار قد ينجح ما بعده لأن المولّد لم يُعطِب شيئاً —
    وهو أخبث أنواع الاختبارات الخضراء الكاذبة.
    """
    import fitz

    from arafix.diagnose import detect_presentation_forms

    raw = fitz.open(broken_pdf)[0].get_text()
    ratio, _ = detect_presentation_forms(raw)
    assert ratio > 0.5, "المولّد لم يُعطِب النص — الاختبار بعده بلا معنى"


def test_roundtrip_recovers_arabic(broken_pdf):
    doc = extract_pdf(broken_pdf)
    text = doc.text
    for phrase in ["دراسة مقارنة", "جامعة تكريت", "مراجعة الأدبيات"]:
        assert phrase in text, f"لم يُسترجع: {phrase}"


def test_roundtrip_preserves_digits_and_latin(broken_pdf):
    """أهم ما يفسده `text[::-1]`."""
    doc = extract_pdf(broken_pdf)
    assert "2024" in doc.text and "4202" not in doc.text
    assert "GDP" in doc.text and "PDG" not in doc.text
    assert "3.5" in doc.text


def test_roundtrip_reports_confidence(broken_pdf):
    doc = extract_pdf(broken_pdf)
    assert doc.confidence > 0.5
    assert doc.pages[0].fonts, "لم تُكشف الخطوط — الدرجة ٣ تحتاجها"


def test_font_extraction_feeds_stage_three(broken_pdf):
    from arafix.cmap import build_glyph_map

    fonts = PyMuPDFExtractor().font_bytes(broken_pdf)
    assert fonts, "لا خطوط مضمَّنة — الدرجة ٣ مستحيلة"
    name, data = next(iter(fonts.items()))
    gm = build_glyph_map(data, name)
    assert gm.coverage > 0.0
    assert gm.lookup("alef") or gm.by_name, "الخريطة فارغة"
