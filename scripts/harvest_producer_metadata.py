"""P0+P1 — حصاد هوية المنتج ومصنّف محركات PDF (قراءة فقط).

لأي قائمة ملفات PDF يفرغ لكل ملف سجلَّ المنتج الكامل ويصنّف مصدرَه:

    python scripts/harvest_producer_metadata.py a.pdf b.pdf --json-out out.json

التصنيف طبقتان:
  ١. قواعد نصية على producer/creator (أولوية الترتيب، أول تطابق يحسم).
  ٢. بصمات بنائية لا تعتمد على النصوص: نمط تسمية القصاصات، أسلوب كتل
     ToUnicode، وجود جدول name — تُرفع كشواهد مستقلة مهما كانت الفئة.

المخرجات قراءةٌ فقط: لا شيء هنا يمس سلوك الأنبوب. التصنيف «شبهة» موثقة
الثقة وليست هوية قاطعة — والفئة الافتراضية دائماً unknown لا تخمين.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import fitz  # noqa: E402

SCHEMA = "arafix.producer-sample.v1-preview"

# ---------------------------------------------------------------------------
# P1 — مصنف المصادر: قواعد نصية مرتبة (أول تطابق يحسم)
# ---------------------------------------------------------------------------

RULES: list[tuple[str, str, float]] = [
    # (الفئة، نمط regex على producer/creator، الثقة)
    ("programmatic-pymupdf", r"\bmupdf\b|\bfitz\b", 0.90),
    ("programmatic-reportlab", r"\breportlab\b", 0.85),
    ("web-export", r"\bskia[/ ]?pdf\b|google docs renderer", 0.85),
    ("web-export", r"\bwkhtmltopdf\b|\bweasyprint\b|\bchromium?\b", 0.75),
    ("word", r"microsoft:? (?:word|office)|\bdocx\b|word for microsoft", 0.90),
    ("print-driver",
     r"\bdopdf\b|\bpdfcreator\b|\bnitro.{0,10}printer\b|\bpdf24\b"
     r"|\bbullzip\b|\bcuteprinter\b|\bfineprint\b", 0.90),
    ("latex", r"\bpdftex\b|\bxetex\b|\bluatex\b|\bdvipdfm\b|\bdvips\b", 0.95),
    ("libreoffice", r"\blibreoffice\b|\bopenoffice\b|\bstaroffice\b", 0.95),
    ("indesign-adobe",
     r"\bindesign\b|\bacrobat distiller\b|adobe pdf library"
     r"|\badobe acrobat\b", 0.85),
    ("scanner-ocr",
     r"\babbyy\b|\bscansoft\b|\bhp scan\b|\bir-adv\b|\bxerox\b"
     r"|\bepson scan\b|\bnaps2\b|\bcanonscan\b", 0.85),
    # برامج النشر العربية القديمة — أفضل جهد، ثقة مخفضة عمداً:
    ("legacy-arabic", r"\bsakhr\b|\bal[- ]?nashr\b|\barabicxt\b|\bdiwan\b", 0.60),
]


def classify_text(producer: str, creator: str) -> dict:
    """يصنف من النصوص؛ أول قاعدة مطابقة تحسم بثقتها."""
    haystacks = (
        ("producer", producer or ""),
        ("creator", creator or ""),
    )
    for cls, pattern, conf in RULES:
        rx = re.compile(pattern, re.I)
        for field_name, value in haystacks:
            m = rx.search(value)
            if m:
                return {
                    "source_software_class": cls,
                    "confidence": conf,
                    "matched": {"field": field_name, "pattern": pattern,
                                "span": m.group(0)},
                }
    return {
        "source_software_class": "unknown",
        "confidence": 0.0,
        "matched": None,
    }


# ---------------------------------------------------------------------------
# بصمات بنائية (لا تعتمد على النصوص)
# ---------------------------------------------------------------------------

_SUBSET_PREFIX = re.compile(r"^([A-Z]{6})\+")


def subset_style(font_names: list[str]) -> str:
    """نمط تسمية القصاصات: تسلسلي-ستعشري (Skia-style) أم ذهني أم كامل."""
    prefixes = []
    for name in font_names:
        m = _SUBSET_PREFIX.match(name)
        if m:
            prefixes.append(m.group(1))
    if not prefixes:
        return "full-embed"
    if all(re.fullmatch(r"[A-F]{6}", p) for p in prefixes):
        return "subset-sequential-hex"
    return "subset-mnemonic"


def tounicode_style(doc, font_xrefs: list[int]) -> str | None:
    """أسلوب كتل ToUnicode عبر خطوط الملف: bfchar-only/range-heavy/mixed."""
    bfchar = bfrange = 0
    seen = False
    for xref in font_xrefs:
        try:
            key = doc.xref_get_key(xref, "ToUnicode")
            if key[0] == "null":
                continue
            tou_xref = int(key[1].split()[0])
            stream = doc.xref_stream(tou_xref).decode("latin-1")
        except Exception:
            continue
        seen = True
        bfchar += len(re.findall(r"beginbfchar", stream))
        bfrange += len(re.findall(r"beginbfrange", stream))
    if not seen:
        return None
    if bfchar and not bfrange:
        return "bfchar-only"
    if bfrange and not bfchar:
        return "range-only"
    return "mixed-bfchar-bfrange"


def font_vendor(doc, font_xref: int) -> str | None:
    """قارئ المصنّع من جدول name إن وُجد (يغيب في المقصوص غالباً)."""
    try:
        _name, _ext, _ftype, data = doc.extract_font(font_xref)
        from fontTools.ttLib import TTFont
        tf = TTFont(io.BytesIO(data), fontNumber=0, lazy=True)
        vendor = None
        if "name" in tf:
            vendor = tf["name"].getDebugName(9) or tf["name"].getDebugName(8)
        tf.close()
        return vendor
    except Exception:
        return None


# ---------------------------------------------------------------------------
# P0 — حصاد السجل الكامل
# ---------------------------------------------------------------------------

def harvest(pdf_path: Path) -> dict:
    data = pdf_path.read_bytes()
    sample_id = hashlib.sha256(data).hexdigest()[:16]
    doc = fitz.open(str(pdf_path))
    md = doc.metadata or {}

    font_rows: list[dict] = []
    seen_xrefs: set[int] = set()
    font_xrefs_all: list[int] = []
    for pno in range(doc.page_count):
        for entry in doc.get_page_fonts(pno):
            xref = entry[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            font_xrefs_all.append(xref)
            name, ftype, enc = entry[3], entry[2], entry[5]
            sub_m = _SUBSET_PREFIX.match(name or "")
            font_rows.append({
                "name": name,
                "type": ftype,
                "encoding": enc,
                "has_ToUnicode": has_tounicode(doc, xref),
                "is_subset": bool(sub_m),
                "vendor": font_vendor(doc, xref),
            })

    text_cls = classify_text(md.get("producer") or "", md.get("creator") or "")
    record = {
        "schema": SCHEMA,
        "file": pdf_path.name,
        "sample_id": sample_id,
        "page_count": doc.page_count,
        "producer": md.get("producer") or "",
        "creator": md.get("creator") or "",
        "pdf_version": (md.get("format") or "").removeprefix("PDF "),
        "encrypted": bool(doc.needs_pass),
        "fonts": font_rows,
        "structural_signatures": {
            "subset_style": subset_style([f["name"] for f in font_rows]),
            "tounicode_style": tounicode_style(doc, font_xrefs_all),
        },
        "classification": text_cls,
        "extractor": {
            "harvester": "harvest_producer_metadata.py",
            "pymupdf": fitz.__doc__.split()[1] if fitz.__doc__ else "unknown",
        },
    }
    doc.close()
    return record


def has_tounicode(doc, xref: int) -> bool:
    try:
        return doc.xref_get_key(xref, "ToUnicode")[0] != "null"
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+", help="ملفات PDF للفحص")
    parser.add_argument("--json-out", type=Path, default=None,
                        help="كتابة السجلات JSON إلى مسار")
    args = parser.parse_args()

    records = []
    for raw in args.pdfs:
        path = Path(raw)
        if not path.exists():
            print(f"SKIP (غير موجود): {path}")
            continue
        rec = harvest(path)
        records.append(rec)
        cls = rec["classification"]
        sig = rec["structural_signatures"]
        n_sub = sum(1 for f in rec["fonts"] if f["is_subset"])
        print(f"{rec['file']}")
        print(f"  producer={rec['producer']!r} version={rec['pdf_version']!r}")
        print(f"  class={cls['source_software_class']} "
              f"(conf={cls['confidence']:.2f}) "
              f"subset_style={sig['subset_style']} "
              f"tou={sig['tounicode_style']} fonts={len(rec['fonts'])} "
              f"(subset={n_sub})")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"schema": SCHEMA, "records": records},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\nJSON -> {args.json_out}")
    print(f"\nتم فحص {len(records)} ملفاً — قراءةٌ فقط، بلا أي تصنيفٍ نهائي.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
