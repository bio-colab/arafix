"""Evaluate audit safety and reversibility on the repository stress corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from arafix import AuditMode, PipelineConfig, repair_text  # noqa: E402

DEFAULT_CORPUS = _ROOT / "tests" / "fixtures" / "stress" / "ultra_complex_corpus.json"


@dataclass
class AuditCaseResult:
    id: str
    kind: str
    safe_case: bool
    changed: bool
    exact_match: bool
    false_repair: bool
    abstentions: int
    events: int
    revert_ok: bool
    input_preview: str
    output_preview: str
    expected_preview: str


@dataclass
class AuditCorpusReport:
    corpus_path: str
    audit_mode: str
    n_cases: int
    safe_cases: int
    false_repairs: int
    false_repair_rate: float
    recovery_cases: int
    exact_recoveries: int
    exact_recovery_rate: float
    abstention_events: int
    changed_events: int
    revert_failures: int
    no_op_preservation: float
    failed_cases: list[str] = field(default_factory=list)
    skipped_cases: list[str] = field(default_factory=list)
    cases: list[dict] = field(default_factory=list)


def _preview(value: str, limit: int = 80) -> str:
    value = value.replace("\n", "\\n")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def evaluate_corpus(
    corpus: dict,
    *,
    include_perf: bool = False,
    corpus_path: str = str(DEFAULT_CORPUS),
) -> AuditCorpusReport:
    results: list[AuditCaseResult] = []
    safe_cases = 0
    false_repairs = 0
    recovery_cases = 0
    exact_recoveries = 0
    abstention_events = 0
    changed_events = 0
    revert_failures = 0
    skipped_cases: list[str] = []

    for case in corpus["cases"]:
        kind = case["kind"]
        if kind == "reverse_visual":
            skipped_cases.append(case["id"])
            continue
        if not include_perf and kind in {"perf", "perf_safe"}:
            continue
        source = case["input"]
        expected = case.get("expected", source)
        result = repair_text(source, PipelineConfig(audit_mode=AuditMode.FULL))
        audit = result.audit
        if audit is None or audit.patch is None:
            raise AssertionError(f"full audit did not produce a patch for {case['id']}")

        safe_case = bool(case.get("must_not_change")) or kind in {"safe", "perf_safe"}
        changed = result.text != source
        exact_match = result.text == expected
        false_repair = safe_case and (changed or not exact_match)
        if safe_case:
            safe_cases += 1
            false_repairs += int(false_repair)
        elif source != expected:
            recovery_cases += 1
            exact_recoveries += int(exact_match)

        revert_ok = audit.patch.revert(result.text) == source
        revert_failures += int(not revert_ok)
        abstention_events += audit.abstention_count
        changed_events += audit.changed_events
        results.append(
            AuditCaseResult(
                id=case["id"],
                kind=kind,
                safe_case=safe_case,
                changed=changed,
                exact_match=exact_match,
                false_repair=false_repair,
                abstentions=audit.abstention_count,
                events=audit.changed_events,
                revert_ok=revert_ok,
                input_preview=_preview(source),
                output_preview=_preview(result.text),
                expected_preview=_preview(expected),
            )
        )

    failed = [r.id for r in results if r.false_repair or not r.revert_ok]
    return AuditCorpusReport(
        corpus_path=corpus_path,
        audit_mode=AuditMode.FULL.value,
        n_cases=len(results),
        safe_cases=safe_cases,
        false_repairs=false_repairs,
        false_repair_rate=false_repairs / safe_cases if safe_cases else 0.0,
        recovery_cases=recovery_cases,
        exact_recoveries=exact_recoveries,
        exact_recovery_rate=exact_recoveries / recovery_cases if recovery_cases else 0.0,
        abstention_events=abstention_events,
        changed_events=changed_events,
        revert_failures=revert_failures,
        no_op_preservation=(safe_cases - false_repairs) / safe_cases if safe_cases else 1.0,
        failed_cases=failed,
        skipped_cases=skipped_cases,
        cases=[asdict(result) for result in results],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--include-perf", action="store_true")
    args = parser.parse_args(argv)
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    report = evaluate_corpus(
        corpus,
        include_perf=args.include_perf,
        corpus_path=str(args.corpus),
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        f"cases={report.n_cases} safe={report.safe_cases} "
        f"false_repairs={report.false_repairs} "
        f"fpr={report.false_repair_rate:.2%} "
        f"recovery={report.exact_recoveries}/{report.recovery_cases} "
        f"rar={report.exact_recovery_rate:.2%} "
        f"revert_failures={report.revert_failures}"
    )
    return 1 if report.false_repairs or report.revert_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
