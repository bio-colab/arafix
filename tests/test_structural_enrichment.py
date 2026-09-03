"""
فحوصات معمارية المرحلة الأولى: إثراء البنية الهيكلية (Structural Enrichment).

تغطي:
- تصنيف العناوين (H1, H2, H3) والقوائم والمتن في layout.py
- كشف الترويسات والتذييلات المتكررة عبر الصفحات running_headers / running_footers
- متن المستند الصافي المنقّى doc.body_text وربط الفقرات المكسورة عبر حواف الصفحات
- استخراج هرمية عناوين المستند doc.headings
"""

from arafix.diagnose import Diagnosis
from arafix.layout import Glyph, LayoutConfig, LayoutLine, analyze_layout
from arafix.pipeline import extract_pdf
from arafix.types import (
    BlockResult,
    BlocksResult,
    DocumentResult,
    PageResult,
    RepairResult,
    TextBlock,
)


def _make_line(text: str, y: float, size: float, role: str = "body") -> LayoutLine:
    glyphs = []
    x = 10.0
    for ch in text:
        glyphs.append(Glyph(x=x, y=y, text=ch, size=size))
        x += size * 0.6
    return LayoutLine(y=y, glyphs=glyphs, role=role)


def test_heading_and_list_classification():
    cfg = LayoutConfig()
    glyphs = []

    # Title (H1): 20pt, placed at y=100 (below 8% header band of 800 = 64)
    y = 100.0
    for ch in "الفصل الأول: الأحكام العامة":
        glyphs.append(Glyph(x=10.0, y=y, text=ch, size=20.0))

    # Subheading (H2): 16pt
    y = 140.0
    for ch in "المبحث الأول: نطاق السريان":
        glyphs.append(Glyph(x=10.0, y=y, text=ch, size=16.0))

    # Body paragraph: 12pt
    y = 180.0
    for ch in "تسري أحكام هذا القانون على كافة المعاملات التجارية المبرمة داخل الدولة.":
        glyphs.append(Glyph(x=10.0, y=y, text=ch, size=12.0))

    # List item: 12pt
    y = 210.0
    for ch in "١- العقود التجارية المباشرة":
        glyphs.append(Glyph(x=10.0, y=y, text=ch, size=12.0))

    # List item 2: 12pt
    y = 240.0
    for ch in "• المعاملات المصرفية المعتمدة":
        glyphs.append(Glyph(x=10.0, y=y, text=ch, size=12.0))

    layout = analyze_layout(glyphs, page_width=500.0, page_height=800.0, config=cfg)
    lines = layout.columns[0].lines

    assert len(lines) == 5
    assert lines[0].role == "heading"
    assert lines[0].heading_level == 1
    assert lines[0].is_heading is True

    assert lines[1].role == "heading"
    assert lines[1].heading_level == 2
    assert lines[1].is_heading is True

    assert lines[2].role == "body"
    assert lines[2].heading_level == 0
    assert lines[2].is_heading is False

    assert lines[3].role == "list_item"
    assert lines[3].is_list_item is True

    assert lines[4].role == "list_item"
    assert lines[4].is_list_item is True


def test_page_result_structural_properties():
    dummy_diag = Diagnosis(defects=(), metrics={}, confidence=1.0)
    rep = RepairResult(
        original="raw",
        text="ترويسة الصفحة\nالفصل الأول\nنص المتن هنا.\n1",
        diagnosis=dummy_diag,
        confidence=1.0,
    )
    b1 = BlockResult(
        block=TextBlock(text="ترويسة الصفحة", role="header"),
        repair=RepairResult(
            original="raw", text="ترويسة الصفحة", diagnosis=dummy_diag, confidence=1.0
        ),
    )
    b2 = BlockResult(
        block=TextBlock(text="الفصل الأول", role="heading", meta={"heading_level": 1}),
        repair=RepairResult(
            original="raw", text="الفصل الأول", diagnosis=dummy_diag, confidence=1.0
        ),
    )
    b3 = BlockResult(
        block=TextBlock(text="نص المتن هنا.", role="line"),
        repair=RepairResult(
            original="raw", text="نص المتن هنا.", diagnosis=dummy_diag, confidence=1.0
        ),
    )
    b4 = BlockResult(
        block=TextBlock(text="1", role="footer"),
        repair=RepairResult(original="raw", text="1", diagnosis=dummy_diag, confidence=1.0),
    )

    page = PageResult(
        page_number=1,
        repair=rep,
        blocks=BlocksResult(blocks=[b1, b2, b3, b4]),
    )

    assert page.header_text == "ترويسة الصفحة"
    assert page.footer_text == "1"
    assert page.headings == [("الفصل الأول", 1)]
    assert "ترويسة الصفحة" not in page.body_text
    assert "1" not in page.body_text
    assert "الفصل الأول" in page.body_text
    assert "نص المتن هنا." in page.body_text


def test_running_headers_footers_and_stitching():
    dummy_diag = Diagnosis(defects=(), metrics={}, confidence=1.0)
    # Page 1
    p1_rep = RepairResult(
        original="raw",
        text="كتاب التاريخ\nوكانت هذه الخطوة\n- 1 -",
        diagnosis=dummy_diag,
        confidence=1.0,
    )
    p1_blocks = BlocksResult(
        blocks=[
            BlockResult(
                block=TextBlock(text="كتاب التاريخ", role="header"),
                repair=RepairResult(
                    original="raw", text="كتاب التاريخ", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
            BlockResult(
                block=TextBlock(text="وكانت هذه الخطوة", role="line"),
                repair=RepairResult(
                    original="raw", text="وكانت هذه الخطوة", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
            BlockResult(
                block=TextBlock(text="- 1 -", role="footer"),
                repair=RepairResult(
                    original="raw", text="- 1 -", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
        ]
    )
    p1 = PageResult(page_number=1, repair=p1_rep, blocks=p1_blocks)

    # Page 2
    p2_rep = RepairResult(
        original="raw",
        text="كتاب التاريخ\nبداية لمرحلة جديدة في التطور.\n- 2 -",
        diagnosis=dummy_diag,
        confidence=1.0,
    )
    p2_blocks = BlocksResult(
        blocks=[
            BlockResult(
                block=TextBlock(text="كتاب التاريخ", role="header"),
                repair=RepairResult(
                    original="raw", text="كتاب التاريخ", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
            BlockResult(
                block=TextBlock(text="بداية لمرحلة جديدة في التطور.", role="line"),
                repair=RepairResult(
                    original="raw",
                    text="بداية لمرحلة جديدة في التطور.",
                    diagnosis=dummy_diag,
                    confidence=1.0,
                ),
            ),
            BlockResult(
                block=TextBlock(text="- 2 -", role="footer"),
                repair=RepairResult(
                    original="raw", text="- 2 -", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
        ]
    )
    p2 = PageResult(page_number=2, repair=p2_rep, blocks=p2_blocks)

    doc = DocumentResult(path="test.pdf", pages=[p1, p2])

    # 1. Deduplication
    assert "كتاب التاريخ" in doc.running_headers
    assert any("1" in f for f in doc.running_footers)
    assert any("2" in f for f in doc.running_footers)

    # 2. Body text stitching: p1 ends without terminal punct -> stitched with space!
    body = doc.body_text
    assert "كتاب التاريخ" not in body
    assert "- 1 -" not in body
    assert "- 2 -" not in body
    assert "وكانت هذه الخطوة بداية لمرحلة جديدة في التطور." in body


def test_real_pdf_headings_file_narrative():
    doc = extract_pdf("tests/fixtures/real_pdf_narrative/file.pdf")
    headings = doc.headings
    heading_texts = [h[0] for h in headings]

    # Verify key sections were identified as headings
    assert any("غز" in t for t in heading_texts)
    assert any("سوريا" in t for t in heading_texts)
    assert any("لبنان" in t for t in heading_texts)
    assert any("العراق" in t for t in heading_texts)
    assert any("إيران" in t for t in heading_texts)

    # Verify body_text is clean and non-empty
    assert len(doc.body_text) > 500
    assert len(doc.body_text) <= len(doc.text)
