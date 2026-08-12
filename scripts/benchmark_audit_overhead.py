"""Measure audit mode overhead and output equivalence on repository gold text."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from arafix import AuditMode, PipelineConfig, repair_text, sha256_text  # noqa: E402

DEFAULT_FILES = (
    _ROOT / "tests" / "fixtures" / "real_pdf_narrative" / "original.txt",
    _ROOT
    / "tests"
    / "fixtures"
    / "real_pdf_narrative"
    / "iraq_constitution_original.txt",
)


def _run(text: str, mode: AuditMode, repeats: int) -> tuple[float, str, int, int]:
    cfg = PipelineConfig(audit_mode=mode)
    repair_text(text, cfg)
    outputs: list[str] = []
    event_count = 0
    abstention_count = 0
    start = time.perf_counter()
    for _ in range(repeats):
        result = repair_text(text, cfg)
        outputs.append(result.text)
        if result.audit is not None:
            event_count += result.audit.changed_events
            abstention_count += result.audit.abstention_count
    elapsed = time.perf_counter() - start
    if len(set(outputs)) != 1:
        raise AssertionError(f"non-deterministic output in audit mode {mode.value}")
    return elapsed, outputs[0], event_count // repeats, abstention_count // repeats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args(argv)

    rows: list[dict] = []
    for path in DEFAULT_FILES:
        text = path.read_text(encoding="utf-8-sig")
        off_elapsed, off_text, _, _ = _run(text, AuditMode.OFF, args.repeats)
        for mode in (AuditMode.SUMMARY, AuditMode.FULL):
            elapsed, output, events, abstentions = _run(text, mode, args.repeats)
            rows.append(
                {
                    "file": path.name,
                    "chars": len(text),
                    "mode": mode.value,
                    "repeats": args.repeats,
                    "seconds": elapsed,
                    "seconds_per_run": elapsed / args.repeats,
                    "overhead_vs_off": elapsed / off_elapsed - 1.0,
                    "output_matches_off": output == off_text,
                    "output_sha256": sha256_text(output),
                    "events_per_run": events,
                    "abstentions_per_run": abstentions,
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "schema": "arafix.audit-overhead.v1",
                "files": [str(path) for path in DEFAULT_FILES],
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    for row in rows:
        print(
            f"{row['file']} mode={row['mode']} "
            f"overhead={row['overhead_vs_off']:.2%} "
            f"matches={row['output_matches_off']} "
            f"events={row['events_per_run']} abstentions={row['abstentions_per_run']}"
        )
    return 0 if all(row["output_matches_off"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
