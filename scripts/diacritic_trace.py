#!/usr/bin/env python3
"""Trace Arabic diacritics from PyMuPDF texttrace to arafix output.

The tool is diagnostic only: it does not modify arafix behavior. It records
where marks are present, attached, preserved, or lost for a PDF and a gold
text, plus ten representative mismatched vocalized cases.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import fitz

from arafix import PipelineConfig, extract_pdf
from arafix.extractors.pymupdf_extractor import PyMuPDFExtractor
from arafix.hygiene import sanitize_extraction


def marks(text: str) -> list[str]:
    return [ch for ch in text if unicodedata.category(ch) == "Mn"]


def strip_marks(text: str) -> str:
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def mark_inventory(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for ch in marks(text):
        out[ch] = out.get(ch, 0) + 1
    return out


def trace_page(page: Any, extractor: PyMuPDFExtractor) -> dict[str, Any]:
    raw_marks: list[dict[str, Any]] = []
    for span_index, span in enumerate(page.get_texttrace()):
        if span.get("type", 0) != 0:
            continue
        for char_index, (uni, glyph_id, origin, bbox) in enumerate(span["chars"]):
            source = chr(uni)
            expanded = extractor._as_combining_marks(source)
            if expanded is None:
                continue
            for mark in expanded:
                raw_marks.append(
                    {
                        "span_index": span_index,
                        "char_index": char_index,
                        "glyph_id": int(glyph_id),
                        "source": source,
                        "mark": mark,
                        "origin": [float(origin[0]), float(origin[1])],
                        "bbox": [float(x) for x in bbox],
                        "font": str(span.get("font") or ""),
                    }
                )
    return {"count": len(raw_marks), "inventory": mark_inventory("".join(x["mark"] for x in raw_marks)), "marks": raw_marks}


def glyph_mark_records(raw: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for glyph_index, glyph in enumerate(raw.glyphs):
        text = str(glyph[2])
        ms = marks(text)
        if not ms:
            continue
        base = strip_marks(text)[:1]
        records.append(
            {
                "glyph_index": glyph_index,
                "x": float(glyph[1]),
                "y": float(glyph[0]),
                "seq": int(glyph[4]) if len(glyph) > 4 else 0,
                "glyph_text": text,
                "base": base,
                "marks": ms,
                "font": str(glyph[6]) if len(glyph) > 6 else "",
                "glyph_id": int(glyph[5]) if len(glyph) > 5 else None,
            }
        )
    return records


def line_context(lines: list[Any], needle: str) -> tuple[str, list[dict[str, Any]]]:
    needle_base = strip_marks(needle)
    for line in lines:
        text = line.text
        if needle in text or needle_base in strip_marks(text):
            return text, glyph_mark_records_from_line(line)
    for line in lines:
        if marks(line.text):
            return line.text, glyph_mark_records_from_line(line)
    return "", []


def glyph_mark_records_from_line(line: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, glyph in enumerate(line.glyphs):
        ms = marks(glyph.text)
        if not ms:
            continue
        records.append(
            {
                "line_glyph_index": index,
                "x": float(glyph.x),
                "y": float(glyph.y),
                "seq": int(glyph.seq),
                "glyph_text": glyph.text,
                "base": strip_marks(glyph.text)[:1],
                "marks": ms,
            }
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("gold", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    config = PipelineConfig()
    extractor = PyMuPDFExtractor(layout_mode=config.layout, geometric_noise=config.geometric_noise)
    raw_pages = list(extractor.pages(str(args.pdf)))
    final_doc = extract_pdf(str(args.pdf), config)
    gold = args.gold.read_text(encoding="utf-8")

    # Representative known mismatch pairs from the constitution alignment. The
    # list is deliberately explicit so the trace remains stable across runs.
    pairs = [
        ("حق", "حقٌ"),
        ("لأب", "لأبٍ"),
        ("لأم", "لاٍُم"),
        ("دولة", "دولةٌ"),
        ("اتحادية", "اتحاديةٌ"),
        ("واحدة", "واحدةٌ"),
        ("مستقلة", "مستقلةٌ"),
        ("جمهوري", "جمهورٌي"),
        ("نيابي", "نيابٌي"),
        ("ديمقراطي", "ديمقراطيٌ"),
    ]

    page_records: list[dict[str, Any]] = []
    with fitz.open(str(args.pdf)) as pdf:
        for index, raw in enumerate(raw_pages):
            trace = trace_page(pdf.load_page(index), extractor)
            layout_text = raw.layout.plain_text if raw.layout else raw.text
            clean_text = sanitize_extraction(layout_text)
            final_text = final_doc.pages[index].text if index < len(final_doc.pages) else ""
            extracted_text = "".join(g[2] for g in raw.glyphs)
            page_records.append(
                {
                    "page": index + 1,
                    "trace": trace,
                    "extracted_glyph_mark_count": len(marks(extracted_text)),
                    "extracted_glyph_mark_inventory": mark_inventory(extracted_text),
                    "layout_mark_count": len(marks(layout_text)),
                    "layout_mark_inventory": mark_inventory(layout_text),
                    "hygiene_mark_count": len(marks(clean_text)),
                    "hygiene_mark_inventory": mark_inventory(clean_text),
                    "final_mark_count": len(marks(final_text)),
                    "final_mark_inventory": mark_inventory(final_text),
                    "glyph_mark_records": glyph_mark_records(raw),
                    "raw_layout_lines": [line.text for line in (raw.layout.lines if raw.layout else []) if marks(line.text)],
                    "final_text": final_text,
                }
            )

    cases: list[dict[str, Any]] = []
    for gold_word, hyp_word in pairs:
        page_hit = next((p for p in page_records if hyp_word in p["final_text"]), None)
        if page_hit is None:
            page_hit = next((p for p in page_records if strip_marks(hyp_word) in strip_marks(p["final_text"])), None)
        if page_hit is None:
            cases.append({"gold": gold_word, "hypothesis": hyp_word, "status": "not-located-in-final-pages"})
            continue
        raw_lines = page_hit["raw_layout_lines"]
        raw_context = next((line for line in raw_lines if strip_marks(hyp_word) in strip_marks(line)), raw_lines[0] if raw_lines else "")
        cases.append(
            {
                "gold": gold_word,
                "hypothesis": hyp_word,
                "page": page_hit["page"],
                "final_context": next((line for line in page_hit["final_text"].splitlines() if hyp_word in line), page_hit["final_text"][:500]),
                "raw_layout_context": raw_context,
                "page_mark_counts": {
                    "trace": page_hit["trace"]["count"],
                    "extracted": page_hit["extracted_glyph_mark_count"],
                    "layout": page_hit["layout_mark_count"],
                    "hygiene": page_hit["hygiene_mark_count"],
                    "final": page_hit["final_mark_count"],
                },
                "attached_glyphs_in_page": page_hit["glyph_mark_records"],
                "interpretation": "compare counts and attached_glyphs_in_page; a drop before glyphs indicates extraction loss, a changed base indicates attachment error, and a drop only after hygiene/final indicates a later-stage deletion.",
            }
        )

    payload = {
        "pdf": str(args.pdf),
        "gold": str(args.gold),
        "pages": len(page_records),
        "page_records": page_records,
        "ten_cases": cases,
        "gold_mark_count": len(marks(gold)),
        "gold_mark_inventory": mark_inventory(gold),
        "diagnostic_note": "This log is observational and does not change arafix behavior.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "pages": len(page_records), "cases": len(cases)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
