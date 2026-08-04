#!/usr/bin/env python3
"""
تقييم موحّد — نصوص و/أو PDF مقابل مرجع، بأرقام ثقة **حقيقية** من الأنبوب.

لا يختلق ثقة 1.00: يطبع:

  * ثقة كل صفحة / الكتلة (كما تُرجعها ``RepairResult.confidence``)
  * أدنى ثقة (أضعف حلقة) ومتوسط الثقة
  * CER / WER (وعلمية اختيارية MCS/DBR/BFE/SHDR)
  * توزيع العلل والمراحل

أمثلة::

    python scripts/eval_unified.py --text-hyp out.txt --truth gold.txt
    python scripts/eval_unified.py --pdf thesis.pdf --truth thesis.txt
    python scripts/eval_unified.py --pdf thesis.pdf --truth thesis.txt --scientific
    python scripts/eval_unified.py --repair-text broken.txt --truth gold.txt

Exit codes:
  0  CER < 5%
  3  CER ≥ 5%
  2  استعمال خاطئ / ملف ناقص
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without install.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _cmd_text_pair(args: argparse.Namespace) -> int:
    from arafix.evaluate import EvalConfig, evaluate_text
    from arafix.scientific import scientific_audit

    hyp = _read(args.text_hyp) if args.text_hyp else _read(args.repair_text)
    if args.repair_text:
        from arafix import PipelineConfig, repair_text

        cfg = PipelineConfig(use_core_lexicon=not args.no_core_lexicon)
        rep = repair_text(_read(args.repair_text), cfg)
        hyp = rep.text
        print("── repair_text ──")
        print(f"  confidence (pipeline): {rep.confidence:.3f}")
        print(f"  stages: {[s.value for s in rep.stages_applied]}")
        print(f"  defects: {rep.diagnosis.summary()}")
        print(f"  defect_confidence: "
              f"{{{', '.join(f'{k.value}={v:.3f}' for k, v in rep.diagnosis.defect_confidence.items())}}}")

    truth = _read(args.truth)
    ecfg = EvalConfig(
        ignore_diacritics=args.ignore_diacritics,
        ignore_punctuation=args.ignore_punctuation,
    )
    report = evaluate_text(truth, hyp, config=ecfg, label=args.label or "text")
    print("── metrics ──")
    print(f"  {report}")
    print(f"  CER={_pct(report.cer.rate)}  WER={_pct(report.wer.rate)}")
    print(f"  chars ref={report.cer.length}  hyp_len={len(hyp)}  truth_len={len(truth)}")

    if args.scientific:
        print("── scientific ──")
        print(scientific_audit(truth, hyp, label=report.label))

    if args.json_out:
        payload = {
            "label": report.label,
            "cer": report.cer.rate,
            "wer": report.wer.rate,
            "hyp_len": len(hyp),
            "truth_len": len(truth),
        }
        Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return 0 if report.cer.rate < 0.05 else 3


def _cmd_pdf(args: argparse.Namespace) -> int:
    from arafix import PipelineConfig, extract_pdf
    from arafix.evaluate import EvalConfig, evaluate_pdf
    from arafix.scientific import scientific_audit

    cfg = PipelineConfig(
        extractor=args.extractor,
        use_core_lexicon=not args.no_core_lexicon,
        layout=args.layout,
    )
    doc = extract_pdf(args.pdf, cfg)

    confidences = [p.repair.confidence for p in doc.pages]
    min_c = min(confidences) if confidences else 0.0
    avg_c = sum(confidences) / len(confidences) if confidences else 0.0
    # DocumentResult.confidence is already min — print both for clarity.
    print("── extract_pdf confidence (honest) ──")
    print(f"  pages: {len(doc.pages)}")
    print(f"  min confidence (weakest link): {min_c:.3f}")
    print(f"  mean confidence: {avg_c:.3f}")
    print(f"  doc.confidence property: {doc.confidence:.3f}")
    print(f"  note: healthy-only diagnoses are capped below 1.0 by design")
    if args.verbose:
        for p in doc.pages:
            print(
                f"  page {p.page_number:3d}  conf={p.repair.confidence:.3f}  "
                f"defects={p.repair.diagnosis.summary()}  "
                f"stages={[s.value for s in p.repair.stages_applied]}"
            )

    if not args.truth:
        print("── no --truth: extraction-only summary ──")
        print(f"  chars: {len(doc.text)}")
        print(f"  metadata: {doc.metadata}")
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(
                    {
                        "pages": len(doc.pages),
                        "min_confidence": min_c,
                        "mean_confidence": avg_c,
                        "chars": len(doc.text),
                        "page_confidences": confidences,
                        "metadata": doc.metadata,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        return 0

    ecfg = EvalConfig(
        ignore_diacritics=args.ignore_diacritics,
        ignore_punctuation=args.ignore_punctuation,
    )
    report = evaluate_pdf(args.pdf, args.truth, extractor=args.extractor, config=ecfg)
    # evaluate_pdf re-extracts; align hyp with our cfg for scientific block
    truth = _read(args.truth)
    hyp = doc.text

    print("── metrics vs truth ──")
    print(f"  {report}")
    print(f"  CER={_pct(report.cer.rate)}  WER={_pct(report.wer.rate)}")

    if args.scientific:
        print("── scientific ──")
        print(scientific_audit(truth, hyp, label=args.label or Path(args.pdf).name))

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "pdf": args.pdf,
                    "pages": len(doc.pages),
                    "min_confidence": min_c,
                    "mean_confidence": avg_c,
                    "cer": report.cer.rate,
                    "wer": report.wer.rate,
                    "page_confidences": confidences,
                    "metadata": doc.metadata,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return 0 if report.cer.rate < 0.05 else 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Unified arafix evaluation (honest confidence + CER/WER)"
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", help="PDF path to extract and score")
    src.add_argument("--text-hyp", help="Hypothesis text file (already repaired)")
    src.add_argument(
        "--repair-text",
        help="Broken text file — run repair_text then score",
    )
    p.add_argument("--truth", help="Reference text (optional for --pdf extraction-only)")
    p.add_argument("--extractor", default="auto")
    p.add_argument("--layout", default="auto", choices=["auto", "linear", "columns", "full"])
    p.add_argument("--label", default="")
    p.add_argument("--scientific", action="store_true")
    p.add_argument("--ignore-diacritics", action="store_true")
    p.add_argument("--ignore-punctuation", action="store_true")
    p.add_argument("--no-core-lexicon", action="store_true")
    p.add_argument("--json-out", help="Write machine-readable summary")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.pdf:
        if not Path(args.pdf).is_file():
            print(f"missing pdf: {args.pdf}", file=sys.stderr)
            return 2
        return _cmd_pdf(args)
    if not args.truth:
        print("--truth is required for text modes", file=sys.stderr)
        return 2
    return _cmd_text_pair(args)


if __name__ == "__main__":
    raise SystemExit(main())
