"""Seeded text mutation engine for auditable recovery evaluation.

This first layer intentionally mutates text only.  It does not pretend that
text mutations reproduce font/CMap/layout failures; those belong to a later
PDF fixture layer with explicit provenance.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

_ARABIC = r"\u0621-\u064A"


@dataclass(frozen=True)
class MutationSpec:
    name: str
    category: str
    description: str
    recoverability: str


@dataclass(frozen=True)
class MutationCase:
    case_id: str
    source_id: str
    category: str
    mutation: str
    seed: int
    original: str
    mutated: str
    expected: str
    recoverability: str


SPECS = (
    MutationSpec(
        "unicode_space",
        "spacing",
        "Replace one ordinary space with NBSP.",
        "supported",
    ),
    MutationSpec(
        "punctuation_attachment",
        "punctuation",
        "Attach an Arabic comma to the following word.",
        "supported",
    ),
    MutationSpec(
        "pdf_homoglyph",
        "glyph_substitution",
        "Replace Arabic Yeh with the common PDF Persian-Yeh homoglyph.",
        "supported",
    ),
    MutationSpec(
        "presentation_form",
        "presentation_forms",
        "Replace a Meem with its isolated Arabic presentation form.",
        "conditional-density",
    ),
    MutationSpec(
        "ligature_form",
        "ligature",
        "Replace Lam-Alef with the Arabic Lam-Alef ligature.",
        "supported",
    ),
    MutationSpec(
        "pdf_al_meem_confusion",
        "font_encoding",
        "Reverse the closed-list امل→الم PDF confusion on a long stem.",
        "supported",
    ),
    MutationSpec(
        "midword_kerning_split",
        "spacing",
        "Split an Arabic word at a non-connecting letter like PDF advance artifacts.",
        "supported",
    ),
    MutationSpec(
        "inverted_parentheses",
        "punctuation",
        "Invert parentheses around Arabic text as seen in visual streams.",
        "supported",
    ),
    MutationSpec(
        "reversed_visual_run",
        "direction",
        "Reverse an Arabic line into visual stream.",
        "supported",
    ),
)


def _replace_once(text: str, old: str, new: str) -> str | None:
    index = text.find(old)
    if index < 0:
        return None
    return text[:index] + new + text[index + len(old) :]


def apply_mutation(text: str, spec_name: str) -> str | None:
    """Apply one named mutation, returning None when its evidence is absent."""
    if spec_name == "unicode_space":
        return _replace_once(text, " ", "\u00a0")
    if spec_name == "punctuation_attachment":
        return _replace_once(text, "، ", "،")
    if spec_name == "pdf_homoglyph":
        return _replace_once(text, "ي", "ی")
    if spec_name == "presentation_form":
        return _replace_once(text, "م", "ﻡ")
    if spec_name == "ligature_form":
        return _replace_once(text, "لا", "ﻻ")
    if spec_name == "pdf_al_meem_confusion":
        mutated = re.sub(rf"الم(?=[{_ARABIC}][{_ARABIC}])", "امل", text, count=1)
        return mutated if mutated != text else None
    if spec_name == "midword_kerning_split":
        m = re.search(rf"(?<=[{_ARABIC}])([دوذرز])(?=[{_ARABIC}]{{2,}})", text)
        if m:
            idx = m.end()
            return text[:idx] + " " + text[idx:]
        return None
    if spec_name == "inverted_parentheses":
        m = re.search(rf"\(([{_ARABIC}\s]+)\)", text)
        if m:
            return text[: m.start()] + ")" + m.group(1) + "(" + text[m.end() :]
        return None
    if spec_name == "reversed_visual_run":
        words = text.split()
        if len(words) >= 2 and all(re.search(rf"[{_ARABIC}]", w) for w in words):
            return text[::-1]
        return None
    raise ValueError(f"unknown mutation: {spec_name}")


def generate_cases(
    texts: list[tuple[str, str]], *, seed: int = 0, max_cases: int | None = None
) -> list[MutationCase]:
    """Generate reproducible cases from caller-supplied clean text."""
    cases: list[MutationCase] = []
    ordered_specs = SPECS[seed % len(SPECS) :] + SPECS[: seed % len(SPECS)]
    for source_id, original in texts:
        for spec in ordered_specs:
            mutated = apply_mutation(original, spec.name)
            if mutated is None or mutated == original:
                continue
            cases.append(
                MutationCase(
                    case_id=f"{source_id}::{spec.name}",
                    source_id=source_id,
                    category=spec.category,
                    mutation=spec.name,
                    seed=seed,
                    original=original,
                    mutated=mutated,
                    expected=original,
                    recoverability=spec.recoverability,
                )
            )
            if max_cases is not None and len(cases) >= max_cases:
                return cases
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON list of {id,text}")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=None)
    args = parser.parse_args(argv)
    source = json.loads(args.input.read_text(encoding="utf-8"))
    texts = [(str(item["id"]), str(item["text"])) for item in source]
    cases = generate_cases(texts, seed=args.seed, max_cases=args.max_cases)
    payload = {
        "schema": "arafix.mutation-corpus.v1",
        "seed": args.seed,
        "specs": [asdict(spec) for spec in SPECS],
        "cases": [asdict(case) for case in cases],
        "pdf_level_deferred": [
            "cmap_reconstruction",
            "watermark_geometry",
            "column_order",
            "multi_page_table_layout",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"generated={len(cases)} seed={args.seed} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
