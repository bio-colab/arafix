"""Tests for read-only PDF producer/creator metadata propagation."""

from __future__ import annotations

from pathlib import Path

import pytest

from arafix import PipelineConfig, extract_pdf, pipeline
from arafix.extractors import PyMuPDFExtractor
from arafix.extractors.base import Extractor, RawPage


class _LegacyExtractor(Extractor):
    """A pre-metadata extractor: the optional hook must keep it working."""

    name = "_legacy_metadata_test"

    def pages(self, path: str):
        yield RawPage(number=1, text="نص سليم")

    def font_bytes(self, path: str) -> dict[str, bytes]:
        return {}


class _MetadataExtractor(Extractor):
    name = "_metadata_test"

    def __init__(self, metadata: dict[str, str]):
        self._metadata = metadata

    def pages(self, path: str):
        yield RawPage(number=1, text="هاذا الكتاب")

    def font_bytes(self, path: str) -> dict[str, bytes]:
        return {}

    def metadata(self, path: str) -> dict[str, str]:
        return dict(self._metadata)


def test_metadata_hook_is_optional_for_existing_extractors() -> None:
    extractor = _LegacyExtractor()
    assert extractor.metadata("unused.pdf") == {}


def test_extract_pdf_propagates_read_only_metadata(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"not parsed by fake extractor")
    monkeypatch.setattr(
        pipeline,
        "get_extractor",
        lambda name: _MetadataExtractor(
            {"producer": "Example Producer", "creator": "Example Creator"}
        ),
    )

    document = extract_pdf(
        str(source), PipelineConfig(extractor="fake", layout="linear")
    )

    assert document.metadata["producer"] == "Example Producer"
    assert document.metadata["creator"] == "Example Creator"
    assert document.pages[0].text == "هاذا الكتاب"
    assert document.pages[0].repair.diagnosis.healthy


def test_metadata_does_not_change_repair_result(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"not parsed by fake extractor")

    def fake_extractor(name: str):
        producer = "Adobe InDesign" if name == "one" else "doPDF Ver 8.3"
        return _MetadataExtractor({"producer": producer, "creator": ""})

    monkeypatch.setattr(pipeline, "get_extractor", fake_extractor)
    first = extract_pdf(str(source), PipelineConfig(extractor="one", layout="linear"))
    second = extract_pdf(str(source), PipelineConfig(extractor="two", layout="linear"))

    assert first.text == second.text == "هاذا الكتاب"
    assert first.metadata["producer"] != second.metadata["producer"]


@pytest.mark.skipif(
    not PyMuPDFExtractor.available(), reason="PyMuPDF غير مثبَّت"
)
def test_pymupdf_producer_creator_reach_document_metadata() -> None:
    pdf = (
        Path(__file__).parent
        / "fixtures"
        / "real_pdf_narrative"
        / "iraq_constitution.pdf"
    )
    if not pdf.is_file():
        pytest.skip("fixture PDF غير موجود")

    extracted = PyMuPDFExtractor().metadata(str(pdf))
    document = extract_pdf(str(pdf))

    assert extracted["producer"]
    assert document.metadata["producer"] == extracted["producer"]
    assert document.metadata["creator"] == extracted["creator"]
