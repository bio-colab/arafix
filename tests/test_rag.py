import json
from pathlib import Path

from arafix import (
    DocumentResult,
    Glyph,
    LayoutColumn,
    LayoutConfig,
    LayoutLine,
    PageLayout,
    PageResult,
    analyze_layout,
    extract_pdf_rag,
    repair_text,
    spatial_rag_chunks,
)


def _line(text: str, *, x: float, y: float, size: float = 10.0) -> LayoutLine:
    glyphs = [
        Glyph(
            y=y,
            x=x + index * 7,
            text=char,
            size=size,
            bbox=(x + index * 7, y - size, x + index * 7 + 6, y),
        )
        for index, char in enumerate(text)
    ]
    return LayoutLine(y=y, glyphs=glyphs)


def test_spatial_rag_chunks_preserve_heading_context_and_exact_bbox() -> None:
    heading = _line("الفصل الأول", x=40, y=40, size=16)
    body = _line("هذا نص عربي", x=40, y=70)
    second = _line("يمتد في السطر التالي", x=40, y=84)
    layout = PageLayout(
        width=300,
        height=400,
        columns=[LayoutColumn(index=0, x0=40, x1=220, lines=[heading, body, second])],
        lines=[heading, body, second],
    )
    page = PageResult(
        page_number=1,
        repair=repair_text(layout.plain_text),
        layout=layout,
        width=300,
        height=400,
    )

    chunks = spatial_rag_chunks(DocumentResult(path="sample.pdf", pages=[page]))

    assert [chunk.role for chunk in chunks] == ["heading", "paragraph"]
    assert chunks[1].parent_context == ("الفصل الأول",)
    assert chunks[1].text == "هذا نص عربي\nيمتد في السطر التالي"
    assert chunks[1].bbox == (40.0, 60.0, 179.0, 84.0)
    assert chunks[1].source == "sample.pdf"
    assert chunks[1].page == 1


def test_table_cells_receive_spatial_bboxes_without_changing_grid_text() -> None:
    glyphs = []
    for row, y in enumerate((50.0, 70.0, 90.0)):
        for column, x in enumerate((30.0, 150.0)):
            text = f"{row}{column}"
            for index, char in enumerate(text):
                glyphs.append(
                    Glyph(
                        y=y,
                        x=x + index * 7,
                        text=char,
                        size=10,
                        bbox=(x + index * 7, y - 10, x + index * 7 + 6, y),
                    )
                )
    layout = analyze_layout(
        glyphs,
        page_width=240,
        page_height=120,
        config=LayoutConfig(),
        mode="full",
    )
    assert len(layout.tables) == 1
    table = layout.tables[0]
    assert table.rows == [["00", "01"], ["10", "11"], ["20", "21"]]
    assert table.cell_bboxes[0][0] == (30.0, 40.0, 43.0, 50.0)
    assert table.to_blocks(page=1, table_id=0)[0].bbox == table.cell_bboxes[0][0]


def test_rag_chunk_json_is_stable_and_serialisable() -> None:
    line = _line("نص", x=10, y=40)
    layout = PageLayout(
        width=100,
        height=100,
        columns=[LayoutColumn(index=0, x0=10, x1=40, lines=[line])],
        lines=[line],
    )
    page = PageResult(
        page_number=2,
        repair=repair_text(layout.plain_text),
        layout=layout,
        width=100,
        height=100,
    )
    document = DocumentResult(path="x.pdf", pages=[page])
    chunk = document.to_rag_chunks()[0]
    payload = json.loads(chunk.to_json())
    document_payload = json.loads(document.to_rag_json(indent=None))

    assert payload["page"] == 2
    assert payload["bbox"] == [10.0, 30.0, 23.0, 40.0]
    assert payload["parent_context"] == []
    assert payload["role"] == "paragraph"
    assert document_payload["schema"] == "arafix.spatial-rag.v1"
    assert document_payload["chunks"][0]["id"] == chunk.id


def test_extract_pdf_rag_returns_real_citation_coordinates() -> None:
    pdf = Path("tests/fixtures/real_pdf_narrative/file.pdf")
    payload = json.loads(extract_pdf_rag(str(pdf), max_chars=500, indent=None))

    assert payload["schema"] == "arafix.spatial-rag.v1"
    assert payload["chunks"]
    assert all(chunk["source"] == str(pdf) for chunk in payload["chunks"])
    assert all(chunk["page"] >= 1 for chunk in payload["chunks"])
    assert all(chunk["bbox"][0] <= chunk["bbox"][2] for chunk in payload["chunks"])
    assert any(chunk["bbox"][2] > chunk["bbox"][0] for chunk in payload["chunks"])
