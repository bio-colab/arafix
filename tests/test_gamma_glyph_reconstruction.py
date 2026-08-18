from arafix.layout import Glyph, join_glyphs_preserving_ltr


def test_same_origin_lam_alef_pair_is_reordered_before_text_repair():
    glyphs = [
        Glyph(y=100, x=0, text="د"),
        Glyph(y=100, x=6, text="ل"),
        Glyph(y=100, x=6, text="ا"),
        Glyph(y=100, x=12, text="و"),
        Glyph(y=100, x=18, text="أ"),
        Glyph(y=100, x=24, text="ب"),
    ]
    assert join_glyphs_preserving_ltr(glyphs, insert_spaces=False) == "دالوأب"
