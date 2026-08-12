"""
P2b — Scientific regression floors on the real narrative corpus.

These gates must not regress. They encode measured quality after P0–P2a:

  MCS  ≥ 0.99   morphological letter skeleton
  DBR  ≥ 0.99   diacritic inventory + attachment (attach ≥ 0.99)
  BFE  Δref ≤ 0.02
  SHDR drift == 0  (PDF lookalikes folded in output)

If a change lowers a floor, either the change is wrong or the floor must be
updated with an explicit, documented reason — never silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from arafix import extract_pdf, scientific_audit
from arafix.extractors import PyMuPDFExtractor

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "real_pdf_narrative"
PDF = FIXTURE / "file.pdf"
TRUTH = FIXTURE / "original.txt"

# Locked floors (P2b) — do not lower without a design note.
_MCS_FLOOR = 0.99
_DBR_FLOOR = 0.99
_DBR_ATTACH_FLOOR = 0.99
_BFE_DELTA_CEILING = 0.02
_SHDR_DRIFT_CEILING = 0.0

pytestmark = [
    pytest.mark.skipif(
        not PyMuPDFExtractor.available(),
        reason="PyMuPDF not installed",
    ),
    pytest.mark.skipif(
        not PDF.is_file() or not TRUTH.is_file(),
        reason="real_pdf_narrative fixture missing",
    ),
]


@pytest.fixture(scope="module")
def audit():
    truth = TRUTH.read_text(encoding="utf-8-sig")
    hyp = extract_pdf(str(PDF)).text
    return scientific_audit(truth, hyp, label="arafix")


class TestScientificFloors:
    def test_mcs_floor(self, audit):
        assert audit.mcs.score >= _MCS_FLOOR, (
            f"MCS={audit.mcs.score} < {_MCS_FLOOR}: {audit.mcs}"
        )

    def test_dbr_floor(self, audit):
        assert audit.dbr.score >= _DBR_FLOOR, (
            f"DBR={audit.dbr.score} < {_DBR_FLOOR}: {audit.dbr}"
        )

    def test_dbr_attachment_floor(self, audit):
        """P2a acceptance: attachment accuracy ≥ 0.99."""
        assert audit.dbr.attachment_accuracy >= _DBR_ATTACH_FLOOR, (
            f"DBR attach={audit.dbr.attachment_accuracy} < {_DBR_ATTACH_FLOOR}"
        )

    def test_dbr_no_leading_marks(self, audit):
        assert audit.dbr.leading_mark_rate == 0.0

    def test_bfe_matches_reference(self, audit):
        assert audit.bfe.delta_to_ref is not None
        assert audit.bfe.delta_to_ref <= _BFE_DELTA_CEILING, (
            f"BFE Δref={audit.bfe.delta_to_ref} > {_BFE_DELTA_CEILING}"
        )

    def test_shdr_zero_drift(self, audit):
        assert audit.shdr.drift_rate <= _SHDR_DRIFT_CEILING, (
            f"SHDR drift={audit.shdr.drift_rate} > {_SHDR_DRIFT_CEILING}"
        )
        assert audit.shdr.n_homoglyphs == 0
