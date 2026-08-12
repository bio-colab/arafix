"""Geometric word-space insertion — calibrated on published book PDFs."""

from __future__ import annotations

from arafix.hygiene import collapse_midword_spaces
from arafix.layout import Glyph, join_glyphs_preserving_ltr


def _line(chars: list[tuple[float, str]], size: float = 12.0) -> list[Glyph]:
    """chars: (x, text) on one baseline."""
    return [Glyph(y=100.0, x=x, text=t, size=size, seq=i) for i, (x, t) in enumerate(chars)]


class TestGlyphSpaces:
    def test_uniform_gaps_no_spurious_spaces(self):
        # Evenly spaced letters → one solid token (no word breaks invented).
        gs = _line([(i * 5.0, ch) for i, ch in enumerate("مرحبا")])
        assert join_glyphs_preserving_ltr(gs) == "مرحبا"

    def test_large_gap_inserts_space_percentile(self):
        # Two clusters separated by a clear gap (>> letter pitch).
        left = [(i * 5.0, ch) for i, ch in enumerate("مرحبا")]
        right = [(80.0 + i * 5.0, ch) for i, ch in enumerate("بكم")]
        text = join_glyphs_preserving_ltr(
            _line(left + right), space_mode="percentile", space_percentile=0.78
        )
        assert " " in text
        assert text.replace(" ", "") == "مرحبابكم"

    def test_can_disable_spaces(self):
        left = [(i * 5.0, ch) for i, ch in enumerate("أب")]
        right = [(40.0 + i * 5.0, ch) for i, ch in enumerate("جد")]
        text = join_glyphs_preserving_ltr(_line(left + right), insert_spaces=False)
        assert " " not in text

    def test_explicit_pdf_spaces_disable_inferred_letter_spaces(self):
        # Advances in shaped Arabic fonts vary by glyph width. Once a line
        # contains explicit whitespace glyphs, inferring additional geometry
        # spaces fragments valid words.
        gs = _line([
            (0.0, "د"), (7.0, "ر"), (16.0, "ا"), (21.0, "س"), (31.0, "ة"),
            (38.0, " "),
            (45.0, "م"), (57.0, "ق"), (67.0, "ا"), (72.0, "ر"), (81.0, "ن"), (90.0, "ة"),
        ], size=16.0)
        assert join_glyphs_preserving_ltr(gs) == "دراسة مقارنة"


class TestCollapseMidword:
    def test_collapses_false_split(self):
        assert collapse_midword_spaces("مو ضع") == "موضع"
        assert collapse_midword_spaces("أي ضًا") == "أيضًا"
        assert collapse_midword_spaces("عاد ي") == "عادي"
        assert collapse_midword_spaces("الع صور") == "العصور"

    def test_keeps_function_word_space(self):
        assert collapse_midword_spaces("في السجن") == "في السجن"
        assert collapse_midword_spaces("من الناس") == "من الناس"

    def test_keeps_short_real_words_before_normal_words(self):
        assert collapse_midword_spaces("نص سليم") == "نص سليم"
        assert collapse_midword_spaces("أي إصلاح") == "أي إصلاح"

    def test_keeps_word_boundary_before_diacritized_normal_word(self):
        # Counting only contiguous base letters mistakes شنّت for a 2-letter
        # fragment because shadda interrupts the regex before the third base.
        assert collapse_midword_spaces("حين شنّت") == "حين شنّت"
        assert collapse_midword_spaces("مَن قرّر") == "مَن قرّر"


class TestSpacingPipelineStage:
    def test_spacing_stage_fires_when_a_midword_gap_is_repaired(self):
        from arafix import Stage, repair_text

        result = repair_text("مو ضع")

        assert result.text == "موضع"
        assert Stage.REPAIR_SPACING in result.stages_applied

    def test_spacing_stage_can_be_disabled(self):
        from arafix import PipelineConfig, Stage, repair_text

        result = repair_text("مو ضع", PipelineConfig(enable_spacing_repair=False))

        assert result.text == "مو ضع"
        assert Stage.REPAIR_SPACING not in result.stages_applied


class TestParticleSpaces:
    def test_inserts_after_particles(self):
        from arafix.hygiene import insert_particle_spaces

        assert "كما أن" in insert_particle_spaces("كماأن")
        assert "لذا اعتدنا" in insert_particle_spaces("لذااعتدنا")
        assert "من العصور" in insert_particle_spaces("منالعصور")

    def test_inserts_between_safe_function_word_boundaries(self):
        from arafix.hygiene import insert_particle_spaces

        assert insert_particle_spaces("فيهذهالحال") == "في هذهالحال"
        assert insert_particle_spaces("هوالذييهب") == "هو الذييهب"
        assert insert_particle_spaces("أنهذاالقول") == "أن هذاالقول"
        assert insert_particle_spaces("لايمكنتمييز") == "لا يمكنتمييز"
        assert insert_particle_spaces("مندونإعادة") == "من دونإعادة"

    def test_does_not_split_ordinary_words_on_particle_prefixes(self):
        from arafix.hygiene import insert_particle_spaces

        assert insert_particle_spaces("لاعبكرة") == "لاعبكرة"

    def test_inserts_between_safe_name_and_honorific_boundaries(self):
        from arafix.hygiene import insert_particle_spaces

        text = "سليمانبنعبدالملكرضيالله"
        assert insert_particle_spaces(text) == "سليمان بن عبد الملك رضي الله"
