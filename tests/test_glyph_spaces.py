"""Geometric word-space insertion — calibrated on published book PDFs."""

from __future__ import annotations

from arafix.layout import Glyph, join_glyphs_preserving_ltr


def _line(chars: list[tuple[float, str]], size: float = 12.0) -> list[Glyph]:
    """chars: (x, text) on one baseline."""
    return [Glyph(y=100.0, x=x, text=t, size=size, seq=i) for i, (x, t) in enumerate(chars)]


class TestGlyphSpaces:
    def test_uniform_gaps_no_spurious_spaces(self):
        # Evenly spaced letters → one solid token (no word breaks invented).
        gs = _line([(i * 5.0, ch) for i, ch in enumerate("مرحبا")])
        assert join_glyphs_preserving_ltr(gs) == "مرحبا"

    def test_large_gap_inserts_space(self):
        # Two clusters separated by a clear gap (>> letter pitch).
        left = [(i * 5.0, ch) for i, ch in enumerate("مرحبا")]
        right = [(80.0 + i * 5.0, ch) for i, ch in enumerate("بكم")]
        text = join_glyphs_preserving_ltr(_line(left + right))
        assert " " in text
        assert text.replace(" ", "") == "مرحبابكم"

    def test_can_disable_spaces(self):
        left = [(i * 5.0, ch) for i, ch in enumerate("أب")]
        right = [(40.0 + i * 5.0, ch) for i, ch in enumerate("جد")]
        text = join_glyphs_preserving_ltr(_line(left + right), insert_spaces=False)
        assert " " not in text
