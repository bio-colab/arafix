"""
Canonical eval loop for *بصمة الإبهام الحمراء* (thumb_red).

This book is the **future regression gate** for arafix quality work:
compare full-power extract_pdf pages against manual gold, report CER/WER
and letter-only CER, and dump per-page error samples.

Usage::

    python benchmarks/independent_eval/eval_thumb_red.py
    python benchmarks/independent_eval/eval_thumb_red.py --refresh   # re-extract pages
    python benchmarks/independent_eval/eval_thumb_red.py --json-out reports/thumb_red.json

Evidence: published Safahat PDF — not AI-generated.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from arafix import PipelineConfig, __version__, evaluate_text, extract_pdf
from arafix.pipeline import _extract_one_page
from arafix.extractors import PyMuPDFExtractor

ROOT = Path(__file__).resolve().parent
BOOK = ROOT / "docs" / "thumb_red"
SAMPLE = BOOK / "sample"
GOLD_PAGES = [47, 87, 149, 176, 188]
AR = re.compile(r"[\u0600-\u06FF]")


def clean(t: str) -> str:
    lines = [ln for ln in t.splitlines() if not ln.startswith("#")]
    while lines and lines[-1].strip().isdigit():
        lines.pop()
    return "\n".join(lines).strip()


def letters_only(t: str) -> str:
    return re.sub(r"[^\w\u0600-\u06FF]+", "", t, flags=re.UNICODE)


def full_power_config() -> PipelineConfig:
    """Maximum quality defaults for book recovery (explicit)."""
    return PipelineConfig(
        enable_mojibake_fix=True,
        enable_normalize=True,
        enable_reorder=True,
        enable_hygiene=True,
        enable_lam_alef_repair=True,
        enable_pdf_confusion_repair=True,
        use_core_lexicon=True,
        harvest_document_lexicon=True,
        repair_per_block=True,
        layout="auto",
    )


def refresh_pages(cfg: PipelineConfig) -> None:
    pdf = BOOK / "source.pdf"
    if not pdf.exists():
        raise SystemExit(f"Missing {pdf} — place the Safahat book PDF there.")
    ex = PyMuPDFExtractor(layout_mode=cfg.layout)
    want = set(GOLD_PAGES)
    SAMPLE.mkdir(parents=True, exist_ok=True)
    for raw in ex.pages(str(pdf)):
        if raw.number not in want:
            continue
        page = _extract_one_page(raw, cfg)
        (SAMPLE / f"page_{raw.number:03d}_arafix.txt").write_text(
            page.text + ("\n" if not page.text.endswith("\n") else ""),
            encoding="utf-8",
        )
        print(
            f"  page {raw.number}: conf={page.repair.confidence} "
            f"stages={[s.value for s in page.repair.stages_applied]} "
            f"chars={len(page.text)}",
            flush=True,
        )
        want.discard(raw.number)
        if not want:
            break


def classify_space_errors(hyp: str, ref: str) -> dict:
    """Rough space-error proxy: CER with/without spaces."""
    full = evaluate_text(hyp, ref)
    lo = evaluate_text(letters_only(hyp), letters_only(ref))
    # space contribution ≈ full CER − letter CER (not exact but directional)
    return {
        "cer": round(full.cer.rate, 6),
        "cer_letters_only": round(lo.cer.rate, 6),
        "wer": round(full.wer.rate, 6),
        "space_gap_proxy": round(max(0.0, full.cer.rate - lo.cer.rate), 6),
        "hyp_spaces": hyp.count(" "),
        "ref_spaces": ref.count(" "),
    }


def first_diff_snippets(hyp: str, ref: str, n: int = 5) -> list[dict]:
    """Find first character mismatches for debugging (letters-only streams)."""
    h, r = letters_only(hyp), letters_only(ref)
    out = []
    i = j = 0
    while i < len(h) and j < len(r) and len(out) < n:
        if h[i] == r[j]:
            i += 1
            j += 1
            continue
        # window
        out.append(
            {
                "hyp": h[max(0, i - 8) : i + 12],
                "ref": r[max(0, j - 8) : j + 12],
                "hyp_i": i,
                "ref_j": j,
            }
        )
        # skip one side greedily
        if i + 1 < len(h) and h[i + 1] == r[j]:
            i += 1
        elif j + 1 < len(r) and h[i] == r[j + 1]:
            j += 1
        else:
            i += 1
            j += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-extract gold pages")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    cfg = full_power_config()
    print(f"arafix {__version__} | thumb_red canonical eval", flush=True)
    print(f"gold pages: {GOLD_PAGES}", flush=True)

    if args.refresh:
        print("refreshing extracts…", flush=True)
        refresh_pages(cfg)

    pages = []
    for pno in GOLD_PAGES:
        gold_p = SAMPLE / f"page_{pno:03d}_gold.txt"
        af_p = SAMPLE / f"page_{pno:03d}_arafix.txt"
        raw_p = SAMPLE / f"page_{pno:03d}_raw.txt"
        if not gold_p.exists() or not af_p.exists():
            print(f"  SKIP page {pno}: missing files", flush=True)
            continue
        gold = clean(gold_p.read_text(encoding="utf-8"))
        af = clean(af_p.read_text(encoding="utf-8"))
        raw = clean(raw_p.read_text(encoding="utf-8")) if raw_p.exists() else ""
        m = classify_space_errors(af, gold)
        m_raw = classify_space_errors(raw, gold) if raw else {}
        diffs = first_diff_snippets(af, gold)
        row = {
            "page": pno,
            "arafix": m,
            "raw": m_raw,
            "diff_samples": diffs,
            "arafix_preview": af.splitlines()[0][:80] if af else "",
            "gold_preview": gold.splitlines()[0][:80] if gold else "",
        }
        pages.append(row)
        print(
            f"  p{pno:03d}  CER_af={m['cer']:.3f}  CERlo={m['cer_letters_only']:.3f}  "
            f"WER={m['wer']:.3f}  space_gap={m['space_gap_proxy']:.3f}  "
            f"spaces {m['hyp_spaces']}/{m['ref_spaces']}",
            flush=True,
        )
        if diffs:
            print(f"         first mismatch hyp={diffs[0]['hyp']!r}", flush=True)
            print(f"                        ref={diffs[0]['ref']!r}", flush=True)

    if not pages:
        return 1

    mean_cer = statistics.mean(p["arafix"]["cer"] for p in pages)
    mean_lo = statistics.mean(p["arafix"]["cer_letters_only"] for p in pages)
    mean_wer = statistics.mean(p["arafix"]["wer"] for p in pages)
    mean_raw = statistics.mean(
        p["raw"]["cer"] for p in pages if p.get("raw") and "cer" in p["raw"]
    )
    print("--- aggregate ---", flush=True)
    print(f"  mean CER raw     : {mean_raw:.3f}", flush=True)
    print(f"  mean CER arafix  : {mean_cer:.3f}", flush=True)
    print(f"  mean CER letters : {mean_lo:.3f}", flush=True)
    print(f"  mean WER arafix  : {mean_wer:.3f}", flush=True)
    # informal golden targets
    print(
        "  targets (informal): CERlo < 0.02, CER < 0.08, WER < 0.5",
        flush=True,
    )

    report = {
        "book": "thumb_red",
        "title_ar": "بصمة الإبهام الحمراء",
        "source": "https://www.safahat.org/",
        "arafix_version": __version__,
        "gold_pages": GOLD_PAGES,
        "aggregate": {
            "mean_cer_raw": round(mean_raw, 6),
            "mean_cer_arafix": round(mean_cer, 6),
            "mean_cer_letters_only": round(mean_lo, 6),
            "mean_wer_arafix": round(mean_wer, 6),
        },
        "pages": pages,
        "notes": (
            "Canonical book for iterative root-cause repair. "
            "Gold is manual correction of system output on a published PDF."
        ),
    }
    out = args.json_out or (ROOT / "thumb_red_eval.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
