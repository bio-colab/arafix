#!/usr/bin/env python3
"""
أداة المقارنة المعيارية متعددة المحركات وخطوط الأنابيب (Cross-Engine & Pipeline Harness).

تقارن أداء arafix ضد:
1. المستخرجات الخام (Raw PyMuPDF, Raw pdfplumber, pdfminer.six)
2. خطوط أنابيب المعالجة الشائعة (pdfplumber + arabic_reshaper + bidi, PyMuPDF + bidi)
3. أدوات إصلاح العربية المتخصصة (pdfplumber + arabic-repair, PyMuPDF + arabic-repair)
بمقاييس علمية موضوعية وحقيقة أرضية نقية (CER, Letters-CER, WER, Word Accuracy, Time).

الاستعمال::

    python scripts/bench_cross_engine.py --pdf doc.pdf --truth truth.txt
    python scripts/bench_cross_engine.py --pdf doc.pdf --truth truth.txt --json-out bench.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure arafix is importable
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from arafix import PipelineConfig, extract_pdf  # noqa: E402
from arafix.evaluate import EvalConfig, cer, cer_letters_only, wer  # noqa: E402


@dataclass
class EngineMetric:
    engine_name: str
    cer_full: float
    cer_letters: float
    wer: float
    word_accuracy: float
    elapsed_ms: float
    char_count: int
    notes: str = ""


def extract_raw_pymupdf(pdf_path: str) -> str:
    import fitz

    doc = fitz.open(pdf_path)
    pages = [doc[i].get_text("text") for i in range(len(doc))]
    doc.close()
    return "\n".join(pages)


def extract_pdfplumber(pdf_path: str) -> str | None:
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        return None
    except Exception as e:
        return f"[pdfplumber error: {e}]"


def extract_pdfminer(pdf_path: str) -> str | None:
    try:
        from pdfminer.high_level import extract_text

        return extract_text(pdf_path)
    except ImportError:
        return None
    except Exception as e:
        return f"[pdfminer error: {e}]"

def apply_reshaper_bidi(text: str) -> str:
    import arabic_reshaper
    from bidi.algorithm import get_display

    lines = []
    for line in text.splitlines():
        if line.strip():
            try:
                lines.append(get_display(arabic_reshaper.reshape(line)))
            except Exception:
                lines.append(line)
        else:
            lines.append(line)
    return "\n".join(lines)


def apply_arabic_repair(text: str) -> str:
    import arabic_repair

    return arabic_repair.repair(text)


def evaluate_extracted(name: str, hyp: str, truth: str, elapsed_ms: float) -> EngineMetric:
    cfg = EvalConfig()
    c_full = cer(truth, hyp, cfg).rate
    c_letters = cer_letters_only(truth, hyp).rate
    w_rate = wer(truth, hyp, cfg).rate
    w_acc = max(0.0, 1.0 - w_rate)
    return EngineMetric(
        engine_name=name,
        cer_full=c_full,
        cer_letters=c_letters,
        wer=w_rate,
        word_accuracy=w_acc,
        elapsed_ms=elapsed_ms,
        char_count=len(hyp),
    )


def run_benchmark(pdf_path: str, truth_path: str) -> list[EngineMetric]:
    truth = Path(truth_path).read_text(encoding="utf-8-sig")
    metrics: list[EngineMetric] = []

    # Check optional packages
    has_bidi = False
    try:
        import arabic_reshaper  # noqa: F401
        from bidi.algorithm import get_display  # noqa: F401

        has_bidi = True
    except ImportError:
        pass

    has_arabic_repair = False
    try:
        import arabic_repair  # noqa: F401

        has_arabic_repair = True
    except ImportError:
        pass

    # 1. Raw PyMuPDF
    t0 = time.perf_counter()
    raw_fitz = extract_raw_pymupdf(pdf_path)
    t_raw = (time.perf_counter() - t0) * 1000.0
    metrics.append(evaluate_extracted("Raw PyMuPDF (no repair)", raw_fitz, truth, t_raw))

    # 2. Raw pdfplumber
    plumber_text = extract_pdfplumber(pdf_path)
    t_plumber = 0.0
    if plumber_text is not None and not plumber_text.startswith("["):
        t0 = time.perf_counter()
        plumber_text = extract_pdfplumber(pdf_path) or ""
        t_plumber = (time.perf_counter() - t0) * 1000.0
        metrics.append(
            evaluate_extracted("Raw pdfplumber (no repair)", plumber_text, truth, t_plumber)
        )

    # 3. Pipelines: arabic_reshaper + python-bidi
    if has_bidi:
        if plumber_text is not None and not plumber_text.startswith("["):
            t0 = time.perf_counter()
            plumber_rb = apply_reshaper_bidi(plumber_text)
            t_total = t_plumber + (time.perf_counter() - t0) * 1000.0
            metrics.append(
                evaluate_extracted(
                    "pdfplumber + arabic_reshaper + python-bidi", plumber_rb, truth, t_total
                )
            )

        t0 = time.perf_counter()
        fitz_rb = apply_reshaper_bidi(raw_fitz)
        t_total = t_raw + (time.perf_counter() - t0) * 1000.0
        metrics.append(
            evaluate_extracted("PyMuPDF + arabic_reshaper + python-bidi", fitz_rb, truth, t_total)
        )

    # 4. Pipelines: arabic-repair
    if has_arabic_repair:
        if plumber_text is not None and not plumber_text.startswith("["):
            t0 = time.perf_counter()
            plumber_ar = apply_arabic_repair(plumber_text)
            t_total = t_plumber + (time.perf_counter() - t0) * 1000.0
            metrics.append(
                evaluate_extracted("pdfplumber + arabic-repair", plumber_ar, truth, t_total)
            )

        t0 = time.perf_counter()
        fitz_ar = apply_arabic_repair(raw_fitz)
        t_total = t_raw + (time.perf_counter() - t0) * 1000.0
        metrics.append(
            evaluate_extracted("PyMuPDF + arabic-repair", fitz_ar, truth, t_total)
        )

    # 5. pdfminer.six
    miner_text = extract_pdfminer(pdf_path)
    if miner_text is not None and not miner_text.startswith("["):
        t0 = time.perf_counter()
        miner_text = extract_pdfminer(pdf_path) or ""
        t_miner = (time.perf_counter() - t0) * 1000.0
        metrics.append(evaluate_extracted("pdfminer.six", miner_text, truth, t_miner))

    # 6. arafix (default)
    t0 = time.perf_counter()
    doc_default = extract_pdf(pdf_path, PipelineConfig())
    t_arafix = (time.perf_counter() - t0) * 1000.0
    metrics.append(evaluate_extracted("arafix (default)", doc_default.text, truth, t_arafix))

    # 7. arafix (layout-aware)
    t0 = time.perf_counter()
    doc_layout = extract_pdf(pdf_path, PipelineConfig(layout=True))
    t_layout = (time.perf_counter() - t0) * 1000.0
    metrics.append(evaluate_extracted("arafix (layout-aware)", doc_layout.text, truth, t_layout))

    return metrics


def format_table(metrics: list[EngineMetric], pdf_path: str) -> str:
    lines = [
        f"### نتائج المقارنة المعيارية الموضوعية: `{Path(pdf_path).name}`\n",
        "| المستخرج / خط الأنابيب | CER (كامل) | CER (حروف فقط) | WER (خطأ الكلمات) | دقة الكلمات (Word Acc) | الزمن (ms) |",  # noqa: E501
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| **{m.engine_name}** | {m.cer_full:6.2%} | {m.cer_letters:6.2%} | "
            f"{m.wer:6.2%} | {m.word_accuracy:6.2%} | {m.elapsed_ms:7.1f} ms |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="Path to evaluation PDF")
    parser.add_argument("--truth", required=True, help="Path to ground truth text")
    parser.add_argument("--json-out", help="Optional JSON report output path")
    args = parser.parse_args()

    metrics = run_benchmark(args.pdf, args.truth)
    table = format_table(metrics, args.pdf)
    print("\n" + table + "\n")

    if args.json_out:
        payload = {
            "pdf": args.pdf,
            "truth": args.truth,
            "metrics": [asdict(m) for m in metrics],
        }
        Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Report written to: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
