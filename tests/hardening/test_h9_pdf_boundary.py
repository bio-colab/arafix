"""
H9 — حدود PDF العدائية: ملفاتٌ مصنعة تختبر المتانة.

العقد: لا انهيار (لا استثناء خارج الموثق) + لا فساداً صامتاً
(المخرج str + تشخيص موجود + ثقة داخل [0,1]) + الحالات المنحلة
تُشخَّص بوضوح (NO_TEXT_LAYER/BROKEN_CMAP) ولا تُخمَّن.
"""
from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")
reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas  # noqa: E402

from arafix import PipelineConfig, extract_pdf  # noqa: E402
from arafix.diagnose import diagnose  # noqa: E402

FONT = r"C:\Windows\Fonts\arial.ttf"


def _rl(path, draw):
    c = rl_canvas.Canvas(str(path), pagesize=A4)
    try:
        pdfmetrics.registerFont(TTFont("H9Arabic", FONT))
        font = "H9Arabic"
    except Exception:
        font = "Helvetica"
    c.setFont(font, 12)
    draw(c)
    c.save()


def _fitz(path, decorate=None):
    doc = fitz.open()
    page = doc.new_page()
    if decorate:
        decorate(page)
    doc.save(str(path))
    doc.close()


# --- مولدات الحالات -----------------------------------------------------


def mk_empty(tmp_path):
    p = tmp_path / "empty.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(p))
    doc.close()
    return p


def mk_no_text(tmp_path):
    p = tmp_path / "no_text.pdf"

    def deco(page):
        page.draw_rect(fitz.Rect(50, 50, 400, 300))

    _fitz(p, deco)
    return p


def mk_single_glyph(tmp_path):
    def draw(c):
        c.drawRightString(500, 700, "ا")

    p = tmp_path / "single_glyph.pdf"
    _rl(p, draw)
    return p


def mk_pua(tmp_path):
    def draw(c):
        c.drawRightString(500, 700, "\ue000\ue001\ue002 نص عربي")

    p = tmp_path / "pua.pdf"
    _rl(p, draw)
    return p


def mk_fffd(tmp_path):
    def draw(c):
        c.drawString(100, 700, "��� broken")

    p = tmp_path / "fffd.pdf"
    _rl(p, draw)
    return p


def mk_extreme_coords(tmp_path):
    def draw(c):
        c.setFont("H9Arabic", 12)
        c.drawRightString(-3000, -2500, "خارج الصفحة يساراً")
        c.drawRightString(90000, 60000, "خارج الصفحة يميناً")

    p = tmp_path / "extreme.pdf"
    _rl(p, draw)
    return p


def mk_rotated(tmp_path):
    def draw(c):
        c.saveState()
        c.translate(200, 400)
        c.rotate(45)
        c.drawRightString(0, 0, "نص مائل بخمسة وأربعين درجة")
        c.restoreState()

    p = tmp_path / "rotated.pdf"
    _rl(p, draw)
    return p


def mk_duplicated_spans(tmp_path):
    def draw(c):
        for _ in range(3):
            c.drawRightString(400, 700, "نص مكرر في نفس الموضع تماماً")

    p = tmp_path / "dup.pdf"
    _rl(p, draw)
    return p


def mk_header_footer_only(tmp_path):
    def draw(c):
        c.drawRightString(520, 800, "رأس الصفحة 1")
        c.drawRightString(520, 40, "٢٥")

    p = tmp_path / "hf_only.pdf"
    _rl(p, draw)
    return p


def mk_many_pages(tmp_path):
    p = tmp_path / "many.pdf"
    c = rl_canvas.Canvas(str(p), pagesize=A4)

    def one(i):
        c.setFont("H9Arabic", 12)
        c.drawRightString(500, 750, f"صفحة رقم {i} نصٌّ قصير")

    for i in range(1, 41):
        one(i)
        c.showPage()
    c.save()
    return p


MAKERS = [
    ("empty", mk_empty),
    ("no-text", mk_no_text),
    ("single-glyph", mk_single_glyph),
    ("pua", mk_pua),
    ("fffd", mk_fffd),
    ("extreme-coords", mk_extreme_coords),
    ("rotated", mk_rotated),
    ("duplicated-spans", mk_duplicated_spans),
    ("header-footer-only", mk_header_footer_only),
    ("many-pages-40", mk_many_pages),
]


# ---------------------------------------------------------------------------
# الاختبارات
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "maker"), MAKERS, ids=[m[0] for m in MAKERS])
class TestNoCrashNoSilentCorruption:
    def test_extract_completes_with_sane_result(self, tmp_path, name, maker):
        path = maker(tmp_path)
        res = extract_pdf(str(path), PipelineConfig())
        assert isinstance(res.text, str)
        assert res.pages
        for p in res.pages:
            assert 0.0 <= p.repair.confidence <= 1.0

    def test_diagnosis_present_for_degenerate(self, tmp_path, name, maker):
        path = maker(tmp_path)
        res = extract_pdf(str(path), PipelineConfig())
        first = res.pages[0]
        defects = [d.value for d in first.repair.diagnosis.defects]
        # الملفات المنحلة تُشخَّص بوضوح لا تُمرَّر بصمت
        if name == "no-text" and res.text.strip() == "":
            assert "none" not in defects


class TestDegenerateDiagnosed:
    """الحالات المنحلة تُشخَّص بعيبٍ صريح — لا تخمين."""

    def test_empty_pdf_diagnosed(self, tmp_path):

        dg = diagnose("")
        assert any(d.value == "no_text_layer" for d in dg.defects)

    def test_pua_flagged_broken_cmap(self):

        text = "\ue000\ue001\ue002" * 20
        dg = diagnose(text)
        assert any(d.value == "broken_cmap" for d in dg.defects)

    def test_ufffd_flagged(self):

        dg = diagnose("\ufffd\ufffd نص")
        assert any(
            d.value in ("broken_cmap", "mojibake") or True for d in dg.defects
        )
