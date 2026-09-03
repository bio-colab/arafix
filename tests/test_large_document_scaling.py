"""
Tests for large document scaling: streaming API (iter_extract_pdf),
multiprocessing parallelism (workers parameter in extract_pdf), and zero-regression guarantees.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arafix import PageResult, extract_pdf, iter_extract_pdf
from arafix.extractors import PyMuPDFExtractor

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "real_pdf_narrative"
IRAQ_PDF = FIXTURE_DIR / "iraq_constitution.pdf"
FILE_PDF = FIXTURE_DIR / "file.pdf"

pytestmark = [
    pytest.mark.skipif(
        not PyMuPDFExtractor.available(),
        reason="PyMuPDF not installed (arafix[pdf])",
    ),
    pytest.mark.skipif(
        not IRAQ_PDF.is_file(),
        reason=f"fixture missing under {FIXTURE_DIR}",
    ),
]


class TestStreamingAPI:
    """Test iter_extract_pdf generator behavior and identity with extract_pdf."""

    def test_iter_extract_pdf_yields_page_results(self):
        generator = iter_extract_pdf(str(IRAQ_PDF))
        pages = list(generator)
        assert len(pages) == 4
        assert all(isinstance(p, PageResult) for p in pages)
        assert [p.page_number for p in pages] == [1, 2, 3, 4]

    def test_iter_extract_pdf_matches_extract_pdf_text(self):
        doc = extract_pdf(str(IRAQ_PDF))
        iter_pages = list(iter_extract_pdf(str(IRAQ_PDF)))

        assert len(iter_pages) == len(doc.pages)
        for p_iter, p_doc in zip(iter_pages, doc.pages):
            assert p_iter.page_number == p_doc.page_number
            assert p_iter.text == p_doc.text


class TestMultiprocessingParallelism:
    """Test extract_pdf with workers > 1 for multicore throughput."""

    def test_multiprocessing_matches_sequential_output(self):
        doc_seq = extract_pdf(str(IRAQ_PDF), workers=1)
        doc_par = extract_pdf(str(IRAQ_PDF), workers=2)

        assert len(doc_seq.pages) == len(doc_par.pages)
        assert doc_par.metadata.get("workers") == 2

        for p_seq, p_par in zip(doc_seq.pages, doc_par.pages):
            assert p_seq.page_number == p_par.page_number
            assert p_seq.text == p_par.text
            assert p_seq.repair.confidence == p_par.repair.confidence
            assert p_seq.repair.stages_applied == p_par.repair.stages_applied

        assert doc_seq.text == doc_par.text

    def test_file_pdf_parallel_matches_sequential(self):
        doc_seq = extract_pdf(str(FILE_PDF), workers=1)
        doc_par = extract_pdf(str(FILE_PDF), workers=2)

        assert doc_seq.text == doc_par.text
