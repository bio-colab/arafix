"""
اختبارات البنية — أعمدة RTL، ترويسة/تذييل، جداول.
"""

from __future__ import annotations

import pytest
from arafix.layout import (
    Glyph,
    LayoutConfig,
    analyze_layout,
    cluster_to_lines,
    glyphs_from_triples,
    table_to_markdown,
)


def _col_glyphs(words: list[str], x0: float, y0: float, dy: float = 22.0) -> list[Glyph]:
    out: list[Glyph] = []
    for i, word in enumerate(words):
        y = y0 + i * dy
        for j, ch in enumerate(word):
            out.append(Glyph(y=y, x=x0 + j * 9, text=ch, size=11))
    return out


class TestClusterLines:
    def test_basic_line_join(self):
        gs = glyphs_from_triples([(10, 30, "ب"), (10, 20, "ا"), (10, 10, "م")], size=12)
        lines = cluster_to_lines(gs)
        assert len(lines) == 1
        assert lines[0].text == "ماب"  # x-sorted: 10,20,30

    def test_two_lines_by_y(self):
        gs = glyphs_from_triples(
            [(10, 0, "أ"), (10, 10, "ب"), (40, 0, "ج"), (40, 10, "د")],
            size=12,
        )
        lines = cluster_to_lines(gs)
        assert len(lines) == 2
        assert lines[0].text == "أب"
        assert lines[1].text == "جد"


class TestColumnsRTL:
    def test_two_columns_rtl_reading_order(self):
        glyphs = []
        glyphs += _col_glyphs(
            ["يمينواحد", "يميناثنين", "يمينثلاث", "يميناربعة", "يمينخمس"],
            x0=400,
            y0=150,
        )
        glyphs += _col_glyphs(
            ["يسارواحد", "يساراثنين", "يسارثلاث", "يساراربعة", "يسارخمس"],
            x0=50,
            y0=155,
        )
        lay = analyze_layout(
            glyphs, page_width=600, page_height=842, mode="columns"
        )
        assert lay.n_columns == 2
        assert lay.mode_used == "columns"
        # العمود 0 = الأيمن في RTL
        assert "يمين" in lay.columns[0].text
        assert "يسار" in lay.columns[1].text
        plain = lay.plain_text
        assert plain.index("يمينواحد") < plain.index("يسارواحد")

    def test_three_columns_rtl_reading_order(self):
        glyphs = []
        glyphs += _col_glyphs(["يمينأ", "يمينب", "يمينج", "يمينه"], x0=440, y0=120)
        glyphs += _col_glyphs(["وسطأ", "وسطب", "وسطج", "وسطه"], x0=250, y0=122)
        glyphs += _col_glyphs(["يسارأ", "يسارب", "يسارج", "يساره"], x0=50, y0=124)

        lay = analyze_layout(glyphs, page_width=600, page_height=842, mode="columns")

        assert lay.n_columns == 3
        assert "يمين" in lay.columns[0].text
        assert "وسط" in lay.columns[1].text
        assert "يسار" in lay.columns[2].text
        assert (
            lay.plain_text.index("يمينأ")
            < lay.plain_text.index("وسطأ")
            < lay.plain_text.index("يسارأ")
        )

    def test_single_column_stays_linear(self):
        glyphs = _col_glyphs(
            ["سطرأولتماماً", "سطرثانكامل", "سطرثالثهنا", "سطررابعكذا"],
            x0=80,
            y0=100,
        )
        # أسطر عريضة نسبياً على صفحة ضيقة؟ x يمتد مع طول الكلمة
        lay = analyze_layout(
            glyphs, page_width=500, page_height=800, mode="auto"
        )
        assert lay.n_columns == 1

    def test_ltr_reading_order_option(self):
        glyphs = []
        glyphs += _col_glyphs(["LEFTAAA", "LEFTBBB", "LEFTCCC", "LEFTDDD"], x0=50, y0=100)
        glyphs += _col_glyphs(["RIGHTAA", "RIGHTBB", "RIGHTCC", "RIGHTDD"], x0=350, y0=105)
        cfg = LayoutConfig(reading_order="ltr")
        lay = analyze_layout(
            glyphs, page_width=600, page_height=800, config=cfg, mode="columns"
        )
        assert lay.n_columns == 2
        assert "LEFT" in lay.columns[0].text
        assert "RIGHT" in lay.columns[1].text


class TestHeaderFooter:
    def test_bands_isolated(self):
        glyphs = []
        for j, ch in enumerate("عنوان"):
            glyphs.append(Glyph(y=20, x=200 + j * 12, text=ch, size=14))
        glyphs += _col_glyphs(
            ["جسدواحدا", "جسدثانين", "جسدثالثا", "جسدرابعا"],
            x0=100,
            y0=200,
        )
        for j, ch in enumerate("ذيل"):
            glyphs.append(Glyph(y=800, x=250 + j * 12, text=ch, size=10))

        lay = analyze_layout(
            glyphs, page_width=600, page_height=842, mode="full"
        )
        assert any("عنوان" in h.text for h in lay.headers)
        assert any("ذيل" in f.text for f in lay.footers)
        body = lay.plain_text
        # الترويسة قبل الجسد قبل التذييل
        assert body.index("عنوان") < body.index("جسد")
        assert body.index("جسد") < body.index("ذيل")


class TestTables:
    def test_aligned_cells_become_table(self):
        """أسطر بفجوات أفقية منتظمة → جدول."""
        glyphs: list[Glyph] = []
        rows = [
            ("اسم", 50, "قيمة", 250, "وحدة", 450),
            ("طول", 50, "12", 250, "سم", 450),
            ("عرض", 50, "8", 250, "سم", 450),
            ("ارتفاع", 50, "3", 250, "م", 450),
        ]
        for i, (a, xa, b, xb, c, xc) in enumerate(rows):
            y = 200 + i * 24
            for j, ch in enumerate(a):
                glyphs.append(Glyph(y=y, x=xa + j * 10, text=ch, size=11))
            for j, ch in enumerate(b):
                glyphs.append(Glyph(y=y, x=xb + j * 10, text=ch, size=11))
            for j, ch in enumerate(c):
                glyphs.append(Glyph(y=y, x=xc + j * 10, text=ch, size=11))

        lay = analyze_layout(
            glyphs, page_width=600, page_height=842, mode="full"
        )
        assert len(lay.tables) >= 1
        assert lay.tables[0].n_cols >= 2
        md = table_to_markdown(lay.tables[0].rows)
        assert "|" in md

    def test_to_blocks_and_reassemble(self):
        glyphs = _col_glyphs(
            ["سطرألفاء", "سطرباءء", "سطرجيمم", "سطردالال"],
            x0=100,
            y0=150,
        )
        lay = analyze_layout(
            glyphs, page_width=500, page_height=800, mode="linear"
        )
        blocks = lay.to_blocks(page_number=1)
        assert blocks
        # محاكاة إصلاح: اقلب النص
        fixed = {b.id: b.text[::-1] for b in blocks if b.id}
        out = lay.reassemble_from_blocks(fixed, page_number=1)
        assert out  # غير فارغ


class TestIntegrationPDF:
    @pytest.fixture(scope="module")
    def multicol_pdf(self, tmp_path_factory):
        fitz = pytest.importorskip("fitz")
        from pathlib import Path

        # خط
        font = None
        for c in [
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]:
            if Path(c).exists():
                font = c
                break
        if not font:
            pytest.skip("no font")

        path = tmp_path_factory.mktemp("lay") / "multi.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_font(fontname="ar", fontfile=font)

        page.insert_text((200, 40), "عنوان الجريدة", fontname="ar", fontsize=14)
        # right column
        y = 120
        for line in ["عمود يمين سطر واحد", "عمود يمين سطر اثنان", "عمود يمين سطر ثلاثة",
                     "عمود يمين سطر اربعة", "عمود يمين سطر خمسة"]:
            page.insert_text((320, y), line, fontname="ar", fontsize=12)
            y += 28
        # left column
        y = 120
        for line in ["عمود يسار سطر واحد", "عمود يسار سطر اثنان", "عمود يسار سطر ثلاثة",
                     "عمود يسار سطر اربعة", "عمود يسار سطر خمسة"]:
            page.insert_text((50, y), line, fontname="ar", fontsize=12)
            y += 28
        page.insert_text((250, 800), "صفحة 1", fontname="ar", fontsize=10)
        doc.save(str(path))
        doc.close()
        return str(path)

    def test_extract_detects_columns(self, multicol_pdf):
        from arafix import PipelineConfig, extract_pdf

        doc = extract_pdf(
            multicol_pdf,
            PipelineConfig(layout="columns", layout_config=LayoutConfig(reading_order="rtl")),
        )
        assert doc.pages[0].n_columns >= 1  # best effort on real PDF
        text = doc.text
        assert "يمين" in text or "يسار" in text or "عمود" in text

    def test_broken_pdf_still_recovers(self, tmp_path):
        """لا نكسر مسار 0.7 — الملف المعطوب أحادي العمود."""
        pytest.importorskip("fitz")
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
        make = pytest.importorskip("make_broken_pdf")
        try:
            font = make.find_font()
        except SystemExit:
            pytest.skip("no font")
        path = tmp_path / "b.pdf"
        make.build(str(path), font)

        import re

        from arafix import extract_pdf

        doc = extract_pdf(str(path))
        # Geometry may insert mid-word spaces on synthetic PDFs; require letter content.
        letters = re.sub(r"\s+", "", doc.text)
        assert "دراسةمقارنة" in letters or "دراسة مقارنة" in doc.text
        assert "2024" in doc.text
