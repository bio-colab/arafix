"""اختبارات حصاد هوية المنتج ومصنف المحركات (قراءة فقط).

يغطي: قواعد التصنيف النصية، البصمات البنائية (نمط القصاصات)، وسجل
الحصاد الكامل على عينة ملتزمة داخل المستودع.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SCRIPT = REPO / "scripts" / "harvest_producer_metadata.py"

_spec = importlib.util.spec_from_file_location("harvest_producer", _SCRIPT)
harvest_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harvest_mod)

classify_text = harvest_mod.classify_text
subset_style = harvest_mod.subset_style


def test_classification_known_producers() -> None:
    cases = {
        "doPDF Ver 8.3 Build 931": "print-driver",
        "Skia/PDF m152 Google Docs Renderer": "web-export",
        "ReportLab PDF Library - (opensource)": "programmatic-reportlab",
        "pdfTeX-1.40.0": "latex",
        "LibreOffice 7.5": "libreoffice",
        "Adobe InDesign 18.0": "indesign-adobe",
        "ABBYY FineReader 15": "scanner-ocr",
        "MuPDF 1.28.0": "programmatic-pymupdf",
    }
    for producer, expected in cases.items():
        got = classify_text(producer, "")
        assert got["source_software_class"] == expected, producer
        assert got["confidence"] >= 0.60


def test_classification_creator_fallback_and_unknown() -> None:
    # creator يُسأل إن صمت producer:
    got = classify_text("", "Microsoft Word لـ Microsoft 365")
    assert got["source_software_class"] == "word"
    # الصمت كله unknown بلا تخمين:
    empty = classify_text("", "")
    assert empty["source_software_class"] == "unknown"
    assert empty["confidence"] == 0.0
    # نص عشوائي لا يقفز إلى فئة:
    noise = classify_text("برنامجنا الخاص جدا", "")
    assert noise["source_software_class"] == "unknown"


def test_subset_style_structural_signature() -> None:
    assert subset_style(["AAAAAA+ArialMT", "BAAAAA+Arial-BoldMT"]) == \
        "subset-sequential-hex"
    assert subset_style(["FNTSBS+SimplifiedArabic"]) == "subset-mnemonic"
    assert subset_style(["Amiri Regular"]) == "full-embed"


@pytest.fixture(scope="module")
def harvested() -> dict:
    pdf = REPO / "benchmarks/wiki_eval/pdfs/human-rights.pf.pdf"
    return harvest_mod.harvest(pdf)


def test_harvest_record_schema(harvested) -> None:
    assert harvested["schema"] == "arafix.producer-sample.v1-preview"
    for key in ("sample_id", "producer", "creator", "pdf_version",
                "fonts", "structural_signatures", "classification",
                "extractor"):
        assert key in harvested, f"حقل مفقود: {key}"
    assert len(harvested["sample_id"]) == 16
    assert harvested["producer"] == "ReportLab PDF Library - (opensource)"
    assert harvested["pdf_version"] == "1.3"


def test_harvest_fonts_details(harvested) -> None:
    fonts = harvested["fonts"]
    assert fonts, "لا خطوط؟"
    for f in fonts:
        assert isinstance(f["has_ToUnicode"], bool)
        assert f["type"] in ("Type0", "TrueType", "Type1", "Type3", "CID")
    by_name = {f["name"]: f for f in fonts}
    subsetted = by_name["AAAAAA+ArialMT"]
    assert subsetted["is_subset"] is True
    assert subsetted["has_ToUnicode"] is True


def test_harvest_classification_matches_producer(harvested) -> None:
    cls = harvested["classification"]
    assert cls["source_software_class"] == "programmatic-reportlab"
    sig = harvested["structural_signatures"]
    assert sig["subset_style"] in (
        "subset-sequential-hex", "subset-mnemonic", "full-embed")
    assert sig["tounicode_style"] in (
        "bfchar-only", "range-only", "mixed-bfchar-bfrange", None)


def test_json_round_trip(tmp_path, harvested) -> None:
    payload = {"schema": harvested["schema"], "records": [harvested]}
    out = tmp_path / "p.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    back = json.loads(out.read_text(encoding="utf-8"))
    assert back["records"][0]["sample_id"] == harvested["sample_id"]
