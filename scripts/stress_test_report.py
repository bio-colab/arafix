#!/usr/bin/env python3
"""
Ultra-Complex Stress Test for arafix 0.9.3+

Loads ``tests/fixtures/stress/ultra_complex_corpus.json`` (50 packages / 6 axes),
measures:

  * FPR  — False Positive Rate on must_not_change / safe cases
  * RAR  — Recovery Accuracy Rate on damaged cases (exact ground-truth match)
  * CER  — mean character error rate on recovery cases
  * Throughput — lines/sec and ms/line on axis-6 blocks

Decision rules (strict)::

  FPR  == 0.00%          → PASS  (else BLOCK release)
  RAR  >= 98.0%          → PASS
  mean CER reported
  Throughput always reported

Usage::

    python scripts/stress_test_report.py
    python scripts/stress_test_report.py --json-out reports/stress_0.9.3.json
    python scripts/stress_test_report.py --skip-perf   # skip 10k-line block
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from arafix import __version__ as ARAFIX_VERSION  # noqa: E402
from arafix import repair_text  # noqa: E402
from arafix.evaluate import cer as cer_metric  # noqa: E402
from arafix.order import reverse_visual_line  # noqa: E402

CORPUS_DEFAULT = _ROOT / "tests" / "fixtures" / "stress" / "ultra_complex_corpus.json"

FPR_LIMIT = 0.0
RAR_MIN = 0.98


@dataclass
class CaseResult:
    id: str
    axis: int
    title: str
    kind: str
    must_not_change: bool
    changed: bool
    exact_match: bool
    cer: float
    ms: float
    false_positive: bool
    recovery_ok: bool | None
    input_preview: str
    output_preview: str
    expected_preview: str
    notes: str = ""


@dataclass
class StressReport:
    library_version: str
    corpus_path: str
    n_cases: int
    n_safe: int
    n_recovery: int
    n_perf: int
    false_positives: int
    fpr: float
    fpr_pass: bool
    recovery_ok: int
    recovery_total: int
    rar: float
    rar_pass: bool
    mean_cer: float
    mean_cer_pass: bool
    lines_per_sec: float | None
    ms_per_line: float | None
    perf_details: list[dict] = field(default_factory=list)
    failed_safe: list[str] = field(default_factory=list)
    failed_recovery: list[str] = field(default_factory=list)
    case_results: list[dict] = field(default_factory=list)
    decision: str = "BLOCK"
    decision_reason: str = ""


def _preview(s: str, n: int = 72) -> str:
    s = s.replace("\n", "\\n")
    return s if len(s) <= n else s[: n - 1] + "…"


def _run_case(case: dict) -> tuple[str, float]:
    """Return (output_text, elapsed_ms)."""
    kind = case["kind"]
    text = case["input"]
    t0 = time.perf_counter()
    if kind in ("repair_text", "safe"):
        out = repair_text(text).text
    elif kind == "reverse_visual":
        out = reverse_visual_line(text)
    elif kind in ("perf", "perf_safe"):
        # line-by-line repair for realistic pipeline load
        lines = text.split("\n")
        out_lines = []
        for ln in lines:
            out_lines.append(repair_text(ln).text)
        out = "\n".join(out_lines)
    else:
        out = repair_text(text).text
    ms = (time.perf_counter() - t0) * 1000.0
    return out, ms


def evaluate_corpus(
    corpus: dict,
    *,
    skip_perf: bool = False,
    skip_ultra: bool = False,
) -> StressReport:
    cases = list(corpus["cases"])
    results: list[CaseResult] = []
    failed_safe: list[str] = []
    failed_recovery: list[str] = []
    perf_details: list[dict] = []

    safe_total = 0
    fp_count = 0
    rec_ok = 0
    rec_total = 0
    cer_sum = 0.0
    cer_n = 0

    total_perf_lines = 0
    total_perf_sec = 0.0

    for case in cases:
        kind = case["kind"]
        if skip_perf and kind in ("perf", "perf_safe"):
            continue
        if skip_ultra and case.get("id") == "A6-03":
            continue

        out, ms = _run_case(case)
        expected = case.get("expected", case["input"])
        must_not = bool(case.get("must_not_change"))
        changed = out != case["input"]
        exact = out == expected

        # CER on recovery cases (not pure safe / not volume perf_safe)
        is_recovery = (
            not must_not
            and kind not in ("perf", "perf_safe")
            and case["input"] != expected
        )
        is_safe_metric = must_not or kind == "safe" or kind == "perf_safe"

        case_cer = 0.0
        if is_recovery or (not must_not and kind == "reverse_visual"):
            case_cer = cer_metric(expected, out).rate
            cer_sum += case_cer
            cer_n += 1

        fp = False
        recovery_ok: bool | None = None

        if is_safe_metric:
            safe_total += 1
            if changed or not exact:
                fp = True
                fp_count += 1
                failed_safe.append(
                    f"{case['id']}: changed={changed} exact={exact} "
                    f"out={_preview(out, 60)}"
                )
        elif kind in ("perf",):
            n_lines = case["input"].count("\n") + (1 if case["input"] else 0)
            sec = ms / 1000.0
            total_perf_lines += n_lines
            total_perf_sec += sec
            lps = n_lines / sec if sec > 0 else float("inf")
            perf_details.append(
                {
                    "id": case["id"],
                    "title": case["title"],
                    "lines": n_lines,
                    "ms": round(ms, 3),
                    "lines_per_sec": round(lps, 2),
                    "ms_per_line": round(ms / max(n_lines, 1), 4),
                }
            )
        else:
            # recovery functional case
            rec_total += 1
            recovery_ok = exact
            if exact:
                rec_ok += 1
            else:
                failed_recovery.append(
                    f"{case['id']}: expected={_preview(expected, 50)} "
                    f"got={_preview(out, 50)} cer={case_cer:.4f}"
                )

        results.append(
            CaseResult(
                id=case["id"],
                axis=case["axis"],
                title=case["title"],
                kind=kind,
                must_not_change=must_not,
                changed=changed,
                exact_match=exact,
                cer=round(case_cer, 6),
                ms=round(ms, 4),
                false_positive=fp,
                recovery_ok=recovery_ok,
                input_preview=_preview(case["input"]),
                output_preview=_preview(out),
                expected_preview=_preview(expected),
            )
        )

    fpr = (fp_count / safe_total) if safe_total else 0.0
    rar = (rec_ok / rec_total) if rec_total else 1.0
    mean_cer = (cer_sum / cer_n) if cer_n else 0.0
    lps = (total_perf_lines / total_perf_sec) if total_perf_sec > 0 else None
    mspl = (1000.0 / lps) if lps else None

    fpr_pass = fpr <= FPR_LIMIT + 1e-15
    rar_pass = rar + 1e-15 >= RAR_MIN
    # CER soft gate: not in hard decision but reported; hard is FPR+RAR
    mean_cer_pass = mean_cer <= 0.05

    if not fpr_pass:
        decision = "BLOCK — FALSE POSITIVES DETECTED"
        reason = (
            f"FPR={fpr*100:.2f}% > 0; safe cases mutated: {failed_safe[:5]}"
        )
    elif not rar_pass:
        decision = "BLOCK — RECOVERY BELOW THRESHOLD"
        reason = (
            f"RAR={rar*100:.2f}% < 98%; failures: {failed_recovery[:8]}"
        )
    else:
        decision = "APPROVED FOR V1.0.0 RELEASE"
        reason = "FPR=0 and RAR>=98% on ultra-complex stress corpus"

    return StressReport(
        library_version=ARAFIX_VERSION,
        corpus_path=str(CORPUS_DEFAULT),
        n_cases=len(results),
        n_safe=safe_total,
        n_recovery=rec_total,
        n_perf=len(perf_details),
        false_positives=fp_count,
        fpr=fpr,
        fpr_pass=fpr_pass,
        recovery_ok=rec_ok,
        recovery_total=rec_total,
        rar=rar,
        rar_pass=rar_pass,
        mean_cer=mean_cer,
        mean_cer_pass=mean_cer_pass,
        lines_per_sec=round(lps, 2) if lps is not None else None,
        ms_per_line=round(mspl, 4) if mspl is not None else None,
        perf_details=perf_details,
        failed_safe=failed_safe,
        failed_recovery=failed_recovery,
        case_results=[asdict(r) for r in results],
        decision=decision,
        decision_reason=reason,
    )


def _flag(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def print_report(rep: StressReport) -> None:
    bar = "=" * 70
    print(bar)
    print("           ARAFIX REAL-WORLD STRESS TEST REPORT".center(70))
    print(f"                    library {rep.library_version}".center(70))
    print(bar)
    print(
        f"1. False Positive Rate (FPR)  : {rep.fpr*100:6.2f}%   "
        f"[{_flag(rep.fpr_pass)}] "
        f"({rep.false_positives}/{rep.n_safe} safe mutated)"
    )
    print(
        f"2. Recovery Accuracy (RAR)    : {rep.rar*100:6.2f}%   "
        f"[{_flag(rep.rar_pass)}] "
        f"({rep.recovery_ok}/{rep.recovery_total} cases restored)"
    )
    print(
        f"3. Average Character Error    : {rep.mean_cer*100:6.2f}%   "
        f"[{_flag(rep.mean_cer_pass)}]"
    )
    if rep.lines_per_sec is not None:
        print(
            f"4. Processing Speed           : "
            f"{rep.lines_per_sec:,.2f} lines/sec "
            f"({rep.ms_per_line:.4f} ms/line)"
        )
    else:
        print("4. Processing Speed           : (perf skipped)")
    print("-" * 70)
    if rep.perf_details:
        print("   Perf packages:")
        for p in rep.perf_details:
            print(
                f"     · {p['id']}: {p['lines']} lines, "
                f"{p['lines_per_sec']:,.1f} lines/sec, "
                f"{p['ms_per_line']:.4f} ms/line"
            )
    if rep.failed_safe:
        print("-" * 70)
        print("   FALSE POSITIVE DETAILS:")
        for line in rep.failed_safe:
            print(f"     ! {line}")
    if rep.failed_recovery:
        print("-" * 70)
        print("   RECOVERY FAILURES (integrate into fixtures if blocking):")
        for line in rep.failed_recovery:
            print(f"     ! {line}")
    print("-" * 70)
    print(f"STATUS DECISION:  {rep.decision}")
    print(f"REASON: {rep.decision_reason}")
    print(bar)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="arafix ultra-complex stress test")
    ap.add_argument(
        "--corpus",
        type=Path,
        default=CORPUS_DEFAULT,
        help="Path to ultra_complex_corpus.json",
    )
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--skip-perf", action="store_true")
    ap.add_argument(
        "--skip-ultra",
        action="store_true",
        help="Skip 10k-line package A6-03 only",
    )
    args = ap.parse_args(argv)

    if not args.corpus.is_file():
        print(f"Corpus not found: {args.corpus}", file=sys.stderr)
        return 2

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    rep = evaluate_corpus(
        corpus, skip_perf=args.skip_perf, skip_ultra=args.skip_ultra
    )
    print_report(rep)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(rep)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON written to {args.json_out}")

    # Exit codes: 0 approved, 3 blocked metrics, 1 internal
    if rep.decision.startswith("APPROVED"):
        return 0
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
