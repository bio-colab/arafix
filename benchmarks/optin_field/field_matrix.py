"""الميدان 1 — مصفوفة PDF: افتراضي مقابل rescue مقابل density مقابل الاثنين.

على مدونات المستودع الحقيقية (قراءةً فقط) يجب أن يبقى النص متطابقاً
بايت-ببايت عبر الأوضاع الأربعة، وألا تُطلق قاعدة MIXED_LINE_RESCUE على أي
صفحة سليمة. أي اختلاف نصي = خروج 1.

    python benchmarks/optin_field/field_matrix.py [--quick]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from arafix import PipelineConfig, extract_pdf  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

CFGS: dict[str, dict] = {
    "default": {"extractor": "pymupdf"},
    "rescue": {"extractor": "pymupdf", "rescue_mixed_lines": True},
    "density": {"extractor": "pymupdf", "confidence_mode": "density"},
    "both": {"extractor": "pymupdf", "rescue_mixed_lines": True,
             "confidence_mode": "density"},
}

QUICK = [
    "human-rights.clean.pdf", "human-rights.pf.pdf", "human-rights.pf_visual.pdf",
    "salahaddin.clean.pdf",
]


def corpus_pdfs(quick: bool) -> list[Path]:
    pdfs = sorted((REPO / "benchmarks/wiki_eval/pdfs").glob("*.pdf"))
    pdfs += sorted((REPO / "benchmarks/wiki_eval/quran/pdfs").glob("*.pdf"))
    pdfs += [REPO / "tests/fixtures/real_pdf_narrative/file.pdf",
             REPO / "tests/fixtures/real_pdf_narrative/iraq_constitution.pdf"]
    if quick:
        names = set(QUICK)
        pdfs = [p for p in pdfs if p.name in names]
    return pdfs


def count_rule(doc, rule: str) -> int:
    n = 0
    for page in doc.pages:
        audit = getattr(page.repair, "audit", None)
        if audit is None:
            continue
        for event in getattr(audit, "events", ()):
            if getattr(event, "rule", "") == rule:
                n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true",
                        help="عينة فرعية سريعة بدل المدونة الكاملة")
    args = parser.parse_args()

    pdfs = corpus_pdfs(args.quick)
    print(f"corpus: {len(pdfs)} PDFs x {len(CFGS)} configs\n")
    header = (f"{'file':38} {'pages':>5} {'default_sha':>12} {'identical':>9} "
              f"{'rescue_rules':>13} {'conf_diffs':>10} {'sec':>6}")
    print(header)

    violations: list[str] = []
    for pdf in pdfs:
        results = {}
        base_sha = ""
        n_pages = 0
        t0 = time.perf_counter()
        for cname, kwargs in CFGS.items():
            doc = extract_pdf(str(pdf), PipelineConfig(**kwargs))
            sha = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()[:10]
            if cname == "default":
                base_sha = sha
                n_pages = len(doc.pages)
            results[cname] = (sha, doc)
        elapsed = time.perf_counter() - t0

        identical = all(results[c][0] == base_sha for c in CFGS)
        rescue_rules = count_rule(results["rescue"][1], "MIXED_LINE_RESCUE")
        d_default = results["default"][1]
        d_density = results["density"][1]
        conf_diffs = sum(
            1
            for p1, p2 in zip(d_default.pages, d_density.pages)
            if abs((p1.repair.confidence or 0) - (p2.repair.confidence or 0)) > 1e-9
        )
        if not identical:
            violations.append(pdf.name)
        print(f"{pdf.name:38} {n_pages:>5} {base_sha:>12} {str(identical):>9} "
              f"{rescue_rules:>13} {conf_diffs:>10} {elapsed:>6.1f}")

    print()
    if violations:
        print("VIOLATIONS — نصوص مختلفة بين الأوضاع:", violations)
        return 1
    print("ALL CLEAN: النص متطابق بايت-ببايت عبر الأوضاع الأربعة على كل المدونة")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
