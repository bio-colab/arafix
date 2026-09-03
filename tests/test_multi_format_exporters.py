"""
فحوصات معمارية المرحلة الثانية: محرك التصدير متعدد الصيغ (Multi-Format Exporters).

تغطي:
- كائن TableResult ودوال التصدير (Markdown, CSV, Dict, DataFrame)
- تصدير الصفحات والمستندات إلى Markdown مهيكل: doc.to_markdown(), page.to_markdown()
- تصدير نصوص فائقة الكفاءة لنماذج الذكاء الاصطناعي: doc.to_llm_text()
- المداخل العليا الميسرة: arafix.read_markdown(), arafix.read_llm()
"""

import arafix
from arafix.diagnose import Diagnosis
from arafix.types import (
    BlockResult,
    BlocksResult,
    DocumentResult,
    PageResult,
    RepairResult,
    TableResult,
    TextBlock,
)


def test_table_result_exporters():
    rows = [
        ["الاسم", "المنصب", "الراتب"],
        ["أحمد", "مهندس", "15000"],
        ["سارة", "مديرة", "20000"],
    ]
    tbl = TableResult(rows=rows, page=1, index=0)

    # 1. Headers & Data
    assert tbl.headers == ["الاسم", "المنصب", "الراتب"]
    assert len(tbl.data) == 2
    assert tbl.data[0] == ["أحمد", "مهندس", "15000"]

    # 2. Markdown export
    md = tbl.to_markdown()
    assert "| الاسم | المنصب | الراتب |" in md
    assert "| --- | --- | --- |" in md
    assert "| أحمد | مهندس | 15000 |" in md

    # 3. CSV export
    csv_str = tbl.to_csv()
    assert "الاسم,المنصب,الراتب" in csv_str
    assert "سارة,مديرة,20000" in csv_str

    # 4. Dict export
    dicts = tbl.to_dict()
    assert len(dicts) == 2
    assert dicts[0] == {"الاسم": "أحمد", "المنصب": "مهندس", "الراتب": "15000"}
    assert dicts[1] == {"الاسم": "سارة", "المنصب": "مديرة", "الراتب": "20000"}


def test_page_and_doc_markdown_export():
    dummy_diag = Diagnosis(defects=(), metrics={}, confidence=1.0)
    p1_blocks = BlocksResult(
        blocks=[
            BlockResult(
                block=TextBlock(text="ترويسة سرية", role="header"),
                repair=RepairResult(
                    original="raw", text="ترويسة سرية", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
            BlockResult(
                block=TextBlock(text="العنوان الرئيسي", role="heading", meta={"heading_level": 1}),
                repair=RepairResult(
                    original="raw", text="العنوان الرئيسي", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
            BlockResult(
                block=TextBlock(text="هذا هو نص الفقرة الأولى.", role="line"),
                repair=RepairResult(
                    original="raw",
                    text="هذا هو نص الفقرة الأولى.",
                    diagnosis=dummy_diag,
                    confidence=1.0,
                ),
            ),
            BlockResult(
                block=TextBlock(text="عنصر قائمة", role="list_item"),
                repair=RepairResult(
                    original="raw", text="عنصر قائمة", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
            BlockResult(
                block=TextBlock(text="ص 1", role="footer"),
                repair=RepairResult(
                    original="raw", text="ص 1", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
        ]
    )
    p1 = PageResult(
        page_number=1,
        repair=RepairResult(original="raw", text="", diagnosis=dummy_diag, confidence=1.0),
        blocks=p1_blocks,
        tables=[[["أ", "ب"], ["1", "2"]]],
    )

    doc = DocumentResult(path="doc.pdf", pages=[p1])

    # Default export: strips headers & footers, renders heading as #, table as markdown grid
    md = doc.to_markdown(include_headers_footers=False)
    assert "# العنوان الرئيسي" in md
    assert "هذا هو نص الفقرة الأولى." in md
    assert "- عنصر قائمة" in md
    assert "| أ | ب |" in md
    assert "ترويسة سرية" not in md
    assert "ص 1" not in md

    # Export with headers/footers
    md_with_hf = doc.to_markdown(include_headers_footers=True)
    assert "> *ترويسة سرية*" in md_with_hf
    assert "> *ص 1*" in md_with_hf


def test_llm_text_export_token_optimization():
    dummy_diag = Diagnosis(defects=(), metrics={}, confidence=1.0)
    p1_blocks = BlocksResult(
        blocks=[
            BlockResult(
                block=TextBlock(text="كتاب التـاريخ", role="header"),
                repair=RepairResult(
                    original="raw", text="كتاب التـاريخ", diagnosis=dummy_diag, confidence=1.0
                ),
            ),
            BlockResult(
                block=TextBlock(text="مَرحَباً بِكُـمْ فِي العَالَمِ الجَدِيدِ.", role="line"),
                repair=RepairResult(
                    original="raw",
                    text="مَرحَباً بِكُـمْ فِي العَالَمِ الجَدِيدِ.",
                    diagnosis=dummy_diag,
                    confidence=1.0,
                ),
            ),
            BlockResult(
                block=TextBlock(text="1", role="footer"),
                repair=RepairResult(original="raw", text="1", diagnosis=dummy_diag, confidence=1.0),
            ),
        ]
    )
    p1 = PageResult(
        page_number=1,
        repair=RepairResult(original="raw", text="", diagnosis=dummy_diag, confidence=1.0),
        blocks=p1_blocks,
    )
    doc = DocumentResult(path="test.pdf", pages=[p1])

    # 1. Normal optimize (tatweel removed, headers/footers suppressed, tashkeel preserved)
    llm_with_tashkeel = doc.to_llm_text(optimize_tokens=True, strip_tashkeel=False)
    assert "ـ" not in llm_with_tashkeel
    assert "مَرحَباً" in llm_with_tashkeel
    assert "كتاب" not in llm_with_tashkeel  # footer/header removed

    # 2. Aggressive optimize (strip_tashkeel=True)
    llm_no_tashkeel = doc.to_llm_text(optimize_tokens=True, strip_tashkeel=True)
    assert "ـ" not in llm_no_tashkeel
    assert "مرحبا بكم في العالم الجديد." in llm_no_tashkeel
    assert "َ" not in llm_no_tashkeel  # Fatha stripped
    assert "ً" not in llm_no_tashkeel  # Tanween stripped


def test_top_level_convenience_apis():
    md = arafix.read_markdown("tests/fixtures/real_pdf_narrative/file.pdf")
    assert "## هل خسرت إيران حربَ الرواية؟" in md or "# هل خسرت إيران" in md
    assert "### سوريا:" in md or "## سوريا:" in md

    llm_text = arafix.read_llm(
        "tests/fixtures/real_pdf_narrative/file.pdf", strip_tashkeel=True
    )
    assert "هل خسرت ايران حرب" in llm_text or "هل خسرت إيران حرب" in llm_text
    assert "َ" not in llm_text  # Tashkeel stripped for token saving
    assert "ـ" not in llm_text  # Tatweel stripped
