"""Run raw MuPDF + arafix extract on the Safahat independent-eval books.

Writes per-book folders under docs/<doc_id>/:
  source.pdf           (copied or hardlinked from flat name if needed)
  raw_mupdf.txt        full raw extract
  arafix_out.txt       full arafix extract
  diagnose.json        per-page defect summary (first N content-ish pages)
  sample_pages.json    page numbers chosen for gold annotation
  sample/
    page_NNN_raw.txt
    page_NNN_arafix.txt
    page_NNN_gold.txt  (seeded from arafix; mark gold_status when edited)

Does not invent literary content: gold seeds are system output for manual fix.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import fitz

from arafix import PipelineConfig, __version__ as ARAFIX_VERSION, diagnose, extract_pdf
from arafix.extractors import PyMuPDFExtractor

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
AR = re.compile(r"[\u0600-\u06FF]")

BOOKS = [
    {
        "doc_id": "thumb_red",
        "filename": "بصمة_الإبهام_الحمراء.pdf",
        "title_ar": "بصمة الإبهام الحمراء",
    },
    {
        "doc_id": "deconstruction",
        "filename": "مداخل_إلى_التفكيك.pdf",
        "title_ar": "مداخل إلى التفكيك",
    },
    {
        "doc_id": "bilhaqq",
        "filename": "وبالحق_نزل.pdf",
        "title_ar": "وبالحق نزل",
    },
]

# Prefer mid-book content pages for gold (skip covers / license).
SAMPLE_COUNT = 5
DIAGNOSE_PAGES = 15


def ensure_book_dir(book: dict) -> tuple[Path, Path]:
    """Return (book_dir, pdf_path). Prefer flat PDF in docs/, else book_dir/source.pdf."""
    flat = DOCS / book["filename"]
    book_dir = DOCS / book["doc_id"]
    book_dir.mkdir(parents=True, exist_ok=True)
    dest = book_dir / "source.pdf"
    if flat.exists():
        if not dest.exists() or dest.stat().st_size != flat.stat().st_size:
            shutil.copy2(flat, dest)
        return book_dir, dest
    if dest.exists():
        return book_dir, dest
    raise FileNotFoundError(f"Missing PDF for {book['doc_id']}: {flat}")


def raw_full_text(pdf: Path) -> str:
    doc = fitz.open(pdf)
    parts = []
    for i, page in enumerate(doc):
        t = page.get_text("text") or ""
        parts.append(f"----- page {i + 1} -----\n{t}")
    doc.close()
    return "\n".join(parts)


def page_arabic_density(pdf: Path) -> list[tuple[int, int, int]]:
    """Return list of (1-based page, arabic_chars, total_chars)."""
    doc = fitz.open(pdf)
    rows = []
    for i, page in enumerate(doc):
        t = page.get_text("text") or ""
        rows.append((i + 1, len(AR.findall(t)), len(t)))
    doc.close()
    return rows


def pick_sample_pages(density: list[tuple[int, int, int]], k: int = SAMPLE_COUNT) -> list[int]:
    """Pick k high-Arabic pages, spread across the book, skipping very early fronts."""
    n = len(density)
    if n == 0:
        return []
    # skip first 5% and last 2% when possible
    lo = max(1, int(n * 0.05))
    hi = max(lo + 1, int(n * 0.98))
    candidates = [
        (p, ar, tot) for p, ar, tot in density if lo <= p <= hi and ar >= 80 and tot >= 200
    ]
    if len(candidates) < k:
        candidates = [(p, ar, tot) for p, ar, tot in density if ar >= 40]
    if not candidates:
        # fall back to evenly spaced pages
        step = max(1, n // (k + 1))
        return [min(n, step * (i + 1)) for i in range(k)]

    # spread: divide range into k buckets, take densest Arabic in each
    cmin, cmax = candidates[0][0], candidates[-1][0]
    picks: list[int] = []
    for i in range(k):
        a = cmin + (cmax - cmin) * i // k
        b = cmin + (cmax - cmin) * (i + 1) // k
        bucket = [c for c in candidates if a <= c[0] <= b] or candidates
        best = max(bucket, key=lambda x: x[1])
        if best[0] not in picks:
            picks.append(best[0])
    # fill if duplicates collapsed
    for p, ar, _ in sorted(candidates, key=lambda x: -x[1]):
        if len(picks) >= k:
            break
        if p not in picks:
            picks.append(p)
    return sorted(picks)[:k]


def extract_page_texts(pdf: Path, page_1based: int) -> tuple[str, str]:
    """Raw MuPDF text and arafix text for one page (via full extract filter)."""
    doc = fitz.open(pdf)
    raw = doc[page_1based - 1].get_text("text") or ""
    doc.close()
    return raw, ""  # arafix filled by caller from DocumentResult


def main() -> int:
    cfg = PipelineConfig()
    summary = []

    for book in BOOKS:
        print(f"=== {book['doc_id']} ({book['title_ar']}) ===", flush=True)
        book_dir, pdf = ensure_book_dir(book)

        # density + samples (keep prior selection if present — stable gold pages)
        density = page_arabic_density(pdf)
        sp_path = book_dir / "sample_pages.json"
        if sp_path.exists():
            prior = json.loads(sp_path.read_text(encoding="utf-8"))
            samples = list(prior.get("sample_pages") or pick_sample_pages(density))
            gold_reviewed = list(prior.get("gold_reviewed") or [])
            gold_draft = list(prior.get("gold_draft") or [])
        else:
            samples = pick_sample_pages(density)
            gold_reviewed, gold_draft = [], []
        (book_dir / "sample_pages.json").write_text(
            json.dumps(
                {
                    "doc_id": book["doc_id"],
                    "sample_pages": samples,
                    "gold_reviewed": gold_reviewed,
                    "gold_draft": gold_draft or [p for p in samples if p not in gold_reviewed],
                    "note": "Pages selected for gold annotation (held-out sample).",
                    "arafix_extract_version": ARAFIX_VERSION,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"  sample pages: {samples}", flush=True)

        # raw full
        print("  raw MuPDF extract…", flush=True)
        raw_txt = raw_full_text(pdf)
        (book_dir / "raw_mupdf.txt").write_text(raw_txt, encoding="utf-8")

        # arafix full
        print("  arafix extract…", flush=True)
        result = extract_pdf(str(pdf), cfg)
        (book_dir / "arafix_out.txt").write_text(result.text, encoding="utf-8")
        conf = result.confidence
        print(
            f"  pages={len(result.pages)} confidence_min={conf} "
            f"chars={len(result.text)}",
            flush=True,
        )

        # diagnose first DIAGNOSE_PAGES non-empty
        diag_rows = []
        ex = PyMuPDFExtractor()
        for raw_page in ex.pages(str(pdf)):
            if raw_page.number > DIAGNOSE_PAGES and len(diag_rows) >= DIAGNOSE_PAGES:
                break
            dg = diagnose(raw_page.text)
            if dg.char_count < 30:
                continue
            diag_rows.append(
                {
                    "page": raw_page.number,
                    "chars": dg.char_count,
                    "arabic_ratio": round(dg.arabic_ratio, 3),
                    "defects": [d.value for d in dg.defects],
                    "confidence": dg.confidence,
                }
            )
            if len(diag_rows) >= DIAGNOSE_PAGES:
                break
        (book_dir / "diagnose.json").write_text(
            json.dumps(diag_rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # per-sample page files
        sample_dir = book_dir / "sample"
        sample_dir.mkdir(exist_ok=True)
        by_num = {p.page_number: p for p in result.pages}
        for pno in samples:
            raw_p, _ = extract_page_texts(pdf, pno)
            af_p = by_num[pno].text if pno in by_num else ""
            (sample_dir / f"page_{pno:03d}_raw.txt").write_text(raw_p, encoding="utf-8")
            (sample_dir / f"page_{pno:03d}_arafix.txt").write_text(
                af_p, encoding="utf-8"
            )
            gold_path = sample_dir / f"page_{pno:03d}_gold.txt"
            if not gold_path.exists():
                # seed gold from arafix for manual correction — never overwrite reviewed gold
                header = (
                    f"# GOLD DRAFT — {book['doc_id']} page {pno}\n"
                    f"# Status: DRAFT (seeded from arafix {ARAFIX_VERSION}; "
                    f"correct manually)\n"
                    f"# Instructions: fix letter order, punctuation, spacing, "
                    f"lam-alef; do not invent missing text.\n"
                    f"# Source: published Safahat book PDF — not AI-generated.\n"
                    f"# When done, set gold_status=reviewed in sample_pages.json "
                    f"or remove this header block.\n\n"
                )
                gold_path.write_text(header + af_p, encoding="utf-8")

        meta = {
            "doc_id": book["doc_id"],
            "title_ar": book["title_ar"],
            "source_site": "https://www.safahat.org/",
            "path": str(pdf.as_posix()),
            "n_pages": len(result.pages),
            "arafix_chars": len(result.text),
            "raw_chars": len(raw_txt),
            "confidence_min": conf,
            "arafix_version": ARAFIX_VERSION,
            "evidence_note": (
                "Published Arabic books from safahat.org; independent held-out "
                "eval — not AI-generated fixtures."
            ),
            "sample_pages": samples,
            "gold_status": "partial_reviewed" if gold_reviewed else "draft_seeded",
            "gold_reviewed_pages": gold_reviewed,
            "gold_scope": "sample_pages_only",
            "outputs": {
                "raw_mupdf": "raw_mupdf.txt",
                "arafix_out": "arafix_out.txt",
                "diagnose": "diagnose.json",
                "sample_dir": "sample/",
            },
        }
        (book_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary.append(meta)
        print(f"  wrote under {book_dir}", flush=True)

    (ROOT / "extract_summary.json").write_text(
        json.dumps(
            {
                "arafix_version": ARAFIX_VERSION,
                "evidence_source": "safahat.org published books (not AI-generated)",
                "books": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"DONE (arafix {ARAFIX_VERSION})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
