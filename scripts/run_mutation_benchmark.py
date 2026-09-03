"""Run the supported text-level mutation benchmark on repository gold text."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for path in (_ROOT, _SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from arafix import AuditMode, PipelineConfig, repair_text, sha256_text  # noqa: E402
from scripts.mutation_engine import generate_cases  # noqa: E402

DEFAULT_OUTPUT = _ROOT / "reports" / "audit" / "mutation-l0.json"


def _sources() -> list[tuple[str, str]]:
    files = (
        _ROOT / "tests" / "fixtures" / "real_pdf_narrative" / "original.txt",
        _ROOT
        / "tests"
        / "fixtures"
        / "real_pdf_narrative"
        / "iraq_constitution_original.txt",
    )
    clean_sources: list[tuple[str, str]] = []
    for path in files:
        raw = path.read_text(encoding="utf-8-sig")
        clean_sources.append((path.name, repair_text(raw).text))
    return clean_sources


def run(output: Path, *, seed: int = 0) -> dict:
    sources = _sources()
    cases = generate_cases(sources, seed=seed)
    by_category: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "exact": 0, "revert": 0}
    )
    details: list[dict] = []
    for case in cases:
        result = repair_text(
            case.mutated,
            PipelineConfig(audit_mode=AuditMode.FULL),
        )
        audit = result.audit
        if audit is None or audit.patch is None:
            raise AssertionError(f"missing full audit for {case.case_id}")
        exact = result.text == case.expected
        reverted = audit.patch.revert(result.text) == case.mutated
        category = by_category[case.category]
        category["cases"] += 1
        category["exact"] += int(exact)
        category["revert"] += int(reverted)
        details.append(
            {
                **asdict(case),
                "output": result.text,
                "exact_recovery": exact,
                "revert_ok": reverted,
                "expected_behavior": (
                    "exact-recovery"
                    if case.recoverability == "supported"
                    else "abstain-or-recover"
                ),
                "audit_events": audit.changed_events,
                "audit_abstentions": audit.abstention_count,
            }
        )
    report = {
        "schema": "arafix.mutation-evaluation.v1",
        "level": "L0-text",
        "seed": seed,
        "source_hashes": {source_id: sha256_text(text) for source_id, text in sources},
        "source_files": [source_id for source_id, _ in sources],
        "source_policy": "mutation cases are applied to each source's default repair_text baseline",
        "n_cases": len(cases),
        "supported_cases": sum(
            item["recoverability"] == "supported" for item in details
        ),
        "supported_exact_recovery": sum(
            item["exact_recovery"] and item["recoverability"] == "supported"
            for item in details
        ),
        "conditional_cases": sum(
            item["recoverability"] != "supported" for item in details
        ),
        "conditional_abstentions": sum(
            item["recoverability"] != "supported" and item["audit_abstentions"] > 0
            for item in details
        ),
        "exact_recovery": sum(item["exact_recovery"] for item in details),
        "revert_success": sum(item["revert_ok"] for item in details),
        "by_category": dict(sorted(by_category.items())),
        "deferred_pdf_level": [
            "cmap_reconstruction",
            "watermark_geometry",
            "column_order",
            "multi_page_table_layout",
        ],
        "cases": details,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    report = run(args.output, seed=args.seed)
    print(
        f"cases={report['n_cases']} supported_exact="
        f"{report['supported_exact_recovery']}/{report['supported_cases']} "
        f"conditional_abstentions={report['conditional_abstentions']}/"
        f"{report['conditional_cases']} revert={report['revert_success']} "
        f"output={args.output}"
    )
    return 0 if (
        report["supported_exact_recovery"] == report["supported_cases"]
        and report["conditional_abstentions"] == report["conditional_cases"]
        and report["revert_success"] == report["n_cases"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
