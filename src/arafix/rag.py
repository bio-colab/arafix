"""Native spatial, structure-aware chunks for Arabic RAG pipelines.

The implementation is deterministic and dependency-free. It reuses the
``PageLayout`` reading order, repaired block text, and geometric bboxes; no
embedding model or external vector store is involved.
"""
from __future__ import annotations

import json
import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from .types import DocumentResult, PageResult

__all__ = ["RAGChunk", "extract_pdf_rag", "spatial_rag_chunks"]

_HEADING_PREFIX = re.compile(
    r"^(?:الفصل|الباب|القسم|المبحث|المطلب|المادة|الجزء|Chapter|Section|"
    r"\d+[.)]|[١-٩]+[.)])\b",
    re.IGNORECASE,
)
_TERMINAL = set(".,:;!?،؛؟.!؟")


@dataclass(frozen=True)
class RAGChunk:
    """A citation-ready chunk with page coordinates and structural ancestry."""

    id: str
    text: str
    page: int
    bbox: tuple[float, float, float, float]
    role: str = "paragraph"
    parent_context: tuple[str, ...] = ()
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "page": self.page,
            "bbox": [round(float(value), 3) for value in self.bbox],
            "role": self.role,
            "parent_context": list(self.parent_context),
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _normalise_bbox(
    bbox: tuple[float, float, float, float] | None,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    if bbox is None:
        return (0.0, 0.0, float(width), float(height))
    x0, y0, x1, y1 = (float(value) for value in bbox)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _line_size(line: Any) -> float:
    sizes = [float(g.size) for g in line.glyphs if float(g.size) > 0]
    return statistics.median(sizes) if sizes else 10.0


def _is_heading(line: Any, page_median_size: float) -> bool:
    if getattr(line, "is_heading", False):
        return True
    text = " ".join(str(line.text).split())
    if not text or len(text) > 140:
        return False
    words = text.split()
    if len(words) > 14 or text[-1:] in _TERMINAL:
        return False
    if _HEADING_PREFIX.match(text):
        return True
    return len(words) <= 9 and _line_size(line) >= page_median_size * 1.18


def _repaired_line_text(page: PageResult, block_id: str, fallback: str) -> str:
    if page.blocks is None:
        return fallback
    block = page.blocks.by_id().get(block_id)
    return block.text if block is not None else fallback


def _line_sources(page: PageResult) -> list[tuple[Any, str]]:
    """Return lines in the same order and IDs used by ``PageLayout.to_blocks``."""
    layout = page.layout
    if layout is None:
        return []
    sources: list[tuple[Any, str]] = []
    repaired_lines = (
        [line for line in page.text.splitlines() if line.strip()]
        if page.blocks is None
        else []
    )
    repaired_index = 0

    def text_for(line: Any, block_id: str) -> str:
        nonlocal repaired_index
        if page.blocks is None:
            text = (
                repaired_lines[repaired_index]
                if repaired_index < len(repaired_lines)
                else line.text
            )
            repaired_index += 1
            return text
        return _repaired_line_text(page, block_id, line.text)

    for index, line in enumerate(layout.headers):
        sources.append((line, text_for(line, f"p{page.page_number}h{index}")))
    for column in layout.columns:
        for index, line in enumerate(column.lines):
            block_id = f"p{page.page_number}c{column.index}l{index}"
            sources.append((line, text_for(line, block_id)))
    for index, line in enumerate(layout.footers):
        sources.append((line, text_for(line, f"p{page.page_number}f{index}")))
    return sources


def _table_sources(
    page: PageResult,
) -> Iterable[tuple[tuple[float, float, float, float] | None, str, dict[str, Any]]]:
    layout = page.layout
    if layout is None:
        return
    by_id = page.blocks.by_id() if page.blocks is not None else {}
    for table_index, table in enumerate(layout.tables):
        for row_index, row in enumerate(table.rows):
            for col_index, cell in enumerate(row):
                block_id = f"p{page.page_number}t{table_index}r{row_index}c{col_index}"
                block = by_id.get(block_id)
                bbox = None
                if row_index < len(table.cell_bboxes):
                    cell_row = table.cell_bboxes[row_index]
                    if col_index < len(cell_row):
                        bbox = cell_row[col_index]
                yield (
                    bbox,
                    block.text if block is not None else cell,
                    {
                        "table": table_index,
                        "row": row_index,
                        "col": col_index,
                        "table_shape": [len(table.rows), table.n_cols],
                    },
                )


def _make_paragraph_chunks(
    page: PageResult,
    sources: list[tuple[Any, str]],
    parent_context: tuple[str, ...],
    max_chars: int,
    chunk_prefix: str,
    source: str,
) -> list[RAGChunk]:
    if not sources:
        return []
    page_size = statistics.median([_line_size(line) for line, _ in sources])
    chunks: list[RAGChunk] = []
    buffer: list[tuple[Any, str]] = []

    def flush() -> None:
        if not buffer:
            return
        text = "\n".join(value.strip() for _, value in buffer if value.strip()).strip()
        if not text:
            buffer.clear()
            return
        bbox = (
            min(line.spatial_bbox[0] for line, _ in buffer),
            min(line.spatial_bbox[1] for line, _ in buffer),
            max(line.spatial_bbox[2] for line, _ in buffer),
            max(line.spatial_bbox[3] for line, _ in buffer),
        )
        chunks.append(
            RAGChunk(
                id=f"{chunk_prefix}-{len(chunks)}",
                text=text,
                page=page.page_number,
                bbox=bbox,
                role="paragraph",
                parent_context=parent_context,
                source=source,
                metadata={"line_count": len(buffer)},
            )
        )
        buffer.clear()

    for line, text in sources:
        if not text.strip():
            flush()
            continue
        if buffer:
            previous = buffer[-1][0]
            vertical_gap = line.spatial_bbox[1] - previous.spatial_bbox[3]
            if vertical_gap > max(page_size * 1.8, 18.0):
                flush()
        candidate = "\n".join([*(value for _, value in buffer), text]).strip()
        if buffer and len(candidate) > max_chars:
            flush()
        buffer.append((line, text))
    flush()
    return chunks


def spatial_rag_chunks(
    document: DocumentResult,
    *,
    max_chars: int = 1200,
) -> list[RAGChunk]:
    """Create deterministic, structure-aware spatial chunks from an extracted PDF."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    chunks: list[RAGChunk] = []
    context: list[str] = []
    for page in document.pages:
        layout = page.layout
        if layout is None:
            if page.text.strip():
                chunks.append(
                    RAGChunk(
                        id=f"p{page.page_number}-0",
                        text=page.text.strip(),
                        page=page.page_number,
                        bbox=(0.0, 0.0, page.width, page.height),
                        role="page",
                        parent_context=tuple(context),
                        source=document.path,
                    )
                )
            continue

        line_sources = _line_sources(page)
        paragraph_sources: list[tuple[Any, str]] = []
        page_size = (
            statistics.median([_line_size(line) for line, _ in line_sources])
            if line_sources
            else 10.0
        )
        for line, text in line_sources:
            if _is_heading(line, page_size):
                chunks.extend(
                    _make_paragraph_chunks(
                        page,
                        paragraph_sources,
                        tuple(context),
                        max_chars,
                        f"p{page.page_number}-b{len(chunks)}",
                        document.path,
                    )
                )
                paragraph_sources.clear()
                heading = text.strip()
                chunks.append(
                    RAGChunk(
                        id=f"p{page.page_number}-h{len(chunks)}",
                        text=heading,
                        page=page.page_number,
                        bbox=line.spatial_bbox,
                        role="heading",
                        parent_context=tuple(context),
                        source=document.path,
                    )
                )
                context = [*context[-2:], heading]
            else:
                paragraph_sources.append((line, text))
        chunks.extend(
            _make_paragraph_chunks(
                page,
                paragraph_sources,
                tuple(context),
                max_chars,
                f"p{page.page_number}-b{len(chunks)}",
                document.path,
            )
        )
        for bbox, text, metadata in _table_sources(page):
            if not str(text).strip():
                continue
            chunks.append(
                RAGChunk(
                    id=(
                        f"p{page.page_number}-t{metadata['table']}"
                        f"-r{metadata['row']}-c{metadata['col']}"
                    ),
                    text=str(text).strip(),
                    page=page.page_number,
                    bbox=_normalise_bbox(bbox, layout.width, layout.height),
                    role="table_cell",
                    parent_context=tuple(context),
                    source=document.path,
                    metadata=metadata,
                )
            )
    return chunks


def extract_pdf_rag(
    path: str,
    config: Any = None,
    *,
    max_chars: int = 1200,
    indent: int | None = 2,
) -> str:
    """Extract a PDF and return a citation-ready JSON RAG document."""
    from .pipeline import PipelineConfig, extract_pdf

    rag_config = replace(
        config or PipelineConfig(),
        preserve_spatial_bboxes=True,
    )
    document = extract_pdf(path, rag_config)
    return document.to_rag_json(max_chars=max_chars, indent=indent)
