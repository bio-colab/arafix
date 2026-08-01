"""
Scientific metrics — contracts, not cosmetics.

Each test documents what the metric is *for*. If you break a definition,
the test name says which decision you reversed.
"""

from __future__ import annotations

from arafix.scientific import (
    bidi_flow_entropy,
    diacritic_base_matrix,
    homoglyph_drift,
    morphological_continuity,
    scientific_audit,
)


class TestMCS:
    def test_identical_text_is_near_perfect(self):
        t = "دراسة مقارنة في السياسة العامة"
        r = morphological_continuity(t, t)
        assert r.score >= 0.99
        assert r.letter_fidelity >= 0.99

    def test_reversed_letters_hurt_mcs(self):
        ref = "مرحبا بكم"
        bad = ref[::-1]
        good = morphological_continuity(ref, ref).score
        bad_s = morphological_continuity(ref, bad).score
        assert good > bad_s + 0.3


class TestDBR:
    def test_perfect_attachment(self):
        t = "نُشِرَتْ هذه القصّة"
        r = diacritic_base_matrix(t, t)
        assert r.attachment_accuracy == 1.0
        assert r.leading_mark_rate == 0.0
        assert r.score >= 0.95

    def test_leading_marks_lower_score(self):
        ref = "حربَ سنواتٍ"
        hyp = "َحرب ٍسنوات"
        r = diacritic_base_matrix(ref, hyp)
        assert r.leading_mark_rate > 0.5
        assert r.score < diacritic_base_matrix(ref, ref).score


class TestBFE:
    def test_entropy_defined_and_bounded(self):
        r = bidi_flow_entropy("مرحبا 2024 GDP")
        assert r.entropy_bits >= 0
        assert 0.0 <= r.normalized <= 1.0
        assert r.n_runs >= 1

    def test_delta_to_self_is_zero(self):
        t = "نص عربي مع 2024"
        r = bidi_flow_entropy(t, reference=t)
        assert r.delta_to_ref == 0.0


class TestSHDR:
    def test_no_drift_on_standard_arabic(self):
        t = "ايران هل"
        r = homoglyph_drift(t, t)
        assert r.drift_rate == 0.0

    def test_farsi_yeh_is_drift(self):
        ref = "ايران"
        hyp = "ایران"  # Farsi Yeh
        r = homoglyph_drift(ref, hyp)
        assert r.drift_rate > 0
        assert r.true_letter_error_rate < r.raw_letter_error_rate + 1e-9


class TestAudit:
    def test_audit_smoke(self):
        rep = scientific_audit("مرحباً", "مرحباً", label="ok")
        assert rep.mcs.score >= 0.9
        assert "MCS" in str(rep)
