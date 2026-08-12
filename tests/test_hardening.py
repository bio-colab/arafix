from __future__ import annotations

import json
from pathlib import Path

import pytest

from arafix import GeometricNoiseConfig, GeometricNoiseFilter, extract_pdf
from arafix.order import fix_order


CORPUS = Path(__file__).parents[1] / "benchmarks" / "adversarial_bidi_corpus.json"


def test_adversarial_bidi_corpus_is_exactly_recovered():
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert len(data["cases"]) == 1000
    counts = {}
    for case in data["cases"]:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
        assert fix_order(case["visual_input"]) == case["logical_gold"], case["id"]
    assert counts == {"dates": 250, "versions": 250, "hybrid": 250, "phones": 250}


def _span(text, *, color=(0.78, 0.78, 0.78), direction=(0.9, -0.43), size=30.0, bbox=(100, 100, 300, 140)):
    return {"chars": [(ord(ch), 0, (0, 0), bbox) for ch in text], "color": color, "dir": direction, "size": size, "bbox": bbox}


def test_geometric_filter_drops_light_gray_rotated_span():
    filt = GeometricNoiseFilter()
    drop, reason = filt.should_drop(_span("WATERMARK 2026"))
    assert drop
    assert reason == "light-gray-rotated"


def test_geometric_filter_keeps_black_rotated_content():
    filt = GeometricNoiseFilter()
    drop, reason = filt.should_drop(_span("محتوى مهم", color=(0.05, 0.05, 0.05)))
    assert not drop
    assert reason == ""


def test_geometric_filter_requires_physical_evidence_for_repetition():
    filt = GeometricNoiseFilter(GeometricNoiseConfig(repeated_min_pages=2, remove_repeated_short_spans=True))
    pages = [[_span("X", color=(0.78, 0.78, 0.78), direction=(1.0, 0.0), size=10.0, bbox=(10, 10, 20, 20))],
             [_span("X", color=(0.78, 0.78, 0.78), direction=(1.0, 0.0), size=10.0, bbox=(10, 10, 20, 20))]]
    keys = filt.repeated_keys(pages)
    kept, removed, reasons = filt.filter_spans(pages[0], keys)
    assert kept == []
    assert removed == 1
    assert reasons == {"repeated-short-span": 1}


@pytest.mark.skipif(__import__("importlib").util.find_spec("fitz") is None, reason="PyMuPDF not installed")
def test_noise_filter_removes_rotated_gray_watermark_from_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "noise.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 80), "CONTENT 2026", fontsize=14, color=(0.05, 0.05, 0.05))
    page.insert_text((180, 430), "WATERMARK 2026", fontsize=30, rotate=90, color=(0.78, 0.78, 0.78))
    doc.save(str(path))
    doc.close()

    result = extract_pdf(str(path))
    assert "CONTENT" in result.text
    assert "WATERMARK" not in result.text
    assert result.metadata.get("geometric_noise_spans_removed", 0) >= 1
