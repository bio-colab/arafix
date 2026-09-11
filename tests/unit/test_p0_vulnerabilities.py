"""Unit tests for P0 algorithmic vulnerability fixes.

1. Plain Unicode Direction Detection Blind Spot (diagnose.py / detect_visual_order):
   - Texts encoded in plain Arabic Unicode (U+0621-U+064A) without presentation forms,
     without taa-marbuta / alif-maqsura, and without "الـ" articles.
   - Texts with inverted terminal markers (tanwin, hamza on nabra/waw).
   - Invariant check: logical forward text remains completely untouched.

2. Explicit Space Adequacy in Geometry Space Inference (layout.py):
   - Hybrid lines containing a solitary explicit space (e.g. after a prefix)
     must still infer spaces across large coordinate gaps for the remaining Arabic words.
   - Normal lines with adequate explicit spaces must not fragment words like "دراسة".
"""
from __future__ import annotations

import pytest

from arafix import PipelineConfig, repair_text
from arafix.diagnose import Defect, detect_visual_order, diagnose
from arafix.layout import Glyph, join_glyphs_preserving_ltr


# ---------------------------------------------------------------------------
# 1. Plain Unicode Direction Detection Tests
# ---------------------------------------------------------------------------

def test_plain_unicode_reversed_sentence_detection() -> None:
    """A sentence of plain Arabic letters without presentation forms, without ة/ى,

    and without 'الـ' should be detected and reversed via lexicon hypothesis.
    Original: 'كتب محمد درس قواعد'
    Reversed: 'دعاق سرد دمحم بتك'
    """
    # 'كتب محمد درس قواعد'[::-1]
    reversed_plain = "\u062f\u0639\u0627\u0648\u0642 \u0633\u0631\u062f \u062f\u0645\u062d\u0645 \u0628\u062a\u0643"
    score, evidence = detect_visual_order(reversed_plain)
    assert score > 0.30, f"Expected reversal score > 0.30, got {score}"

    diag = diagnose(reversed_plain)
    assert Defect.VISUAL_ORDER in diag.defects

    result = repair_text(reversed_plain)
    assert result.text == "كتب محمد درس قواعد"


def test_plain_unicode_forward_sentence_preserved() -> None:
    """Logical forward Arabic text must score negative or zero, never falsely reversed."""
    forward_plain = "كتب محمد درس قواعد"
    score, evidence = detect_visual_order(forward_plain)
    assert score < 0.0, f"Expected negative score for logical text, got {score}"

    diag = diagnose(forward_plain)
    assert Defect.VISUAL_ORDER not in diag.defects

    result = repair_text(forward_plain)
    assert result.text == forward_plain


def test_inverted_tanwin_terminal_marker_detection() -> None:
    """Tanwin on the leading character/alif is a decisive physical proof of reversal.

    Original: 'واحداً' -> Reversed: 'اًدحاو'
    """
    reversed_tanwin = "اًدحاو ناك"  # 'كان واحداً'
    score, evidence = detect_visual_order(reversed_tanwin)
    assert score > 0.30

    diag = diagnose(reversed_tanwin)
    assert Defect.VISUAL_ORDER in diag.defects


def test_inverted_terminal_hamza_detection() -> None:
    """Hamza on yaa/nabra (ئ) or on waw (ؤ) never starts an Arabic word.

    'ئطاش' is 'شاطئ' reversed.
    """
    reversed_word = "ئطاش رمحب"  # 'ببحر شاطئ'
    score, evidence = detect_visual_order(reversed_word)
    assert score > 0.30


# ---------------------------------------------------------------------------
# 2. Explicit Space Adequacy in layout.py
# ---------------------------------------------------------------------------

def test_hybrid_line_with_solitary_space_infers_arabic_spaces() -> None:
    """A line with 1 explicit space after an English prefix, followed by multiple

    Arabic words separated only by coordinate gaps, must infer spaces for the Arabic words.
    """
    # Simulate glyphs: "1. " then Arabic words with wide coordinate gaps (24pt) between words,
    # and narrow gaps (8pt) between letters. Font size = 10pt.
    glyphs: list[Glyph] = [
        # LTR island: "1."
        Glyph(y=100.0, x=10.0, text="1", size=10.0),
        Glyph(y=100.0, x=16.0, text=".", size=10.0),
        # Explicit space glyph
        Glyph(y=100.0, x=22.0, text=" ", size=10.0),
        # Word 1: "ذهب" (x: 30, 38, 46)
        Glyph(y=100.0, x=30.0, text="ذ", size=10.0),
        Glyph(y=100.0, x=38.0, text="ه", size=10.0),
        Glyph(y=100.0, x=46.0, text="ب", size=10.0),
        # Word 2: "الولد" (gap from 46 to 70 is 24pt > th)
        Glyph(y=100.0, x=70.0, text="ا", size=10.0),
        Glyph(y=100.0, x=78.0, text="ل", size=10.0),
        Glyph(y=100.0, x=86.0, text="و", size=10.0),
        Glyph(y=100.0, x=94.0, text="ل", size=10.0),
        Glyph(y=100.0, x=102.0, text="د", size=10.0),
        # Word 3: "سريعا" (gap from 102 to 130 is 28pt > th)
        Glyph(y=100.0, x=130.0, text="س", size=10.0),
        Glyph(y=100.0, x=138.0, text="ر", size=10.0),
        Glyph(y=100.0, x=146.0, text="ي", size=10.0),
        Glyph(y=100.0, x=154.0, text="ع", size=10.0),
        Glyph(y=100.0, x=162.0, text="ا", size=10.0),
    ]

    text = join_glyphs_preserving_ltr(glyphs, insert_spaces=True)
    # The Arabic words must have spaces between them, not be glued into "ذهبالولدسريعا"
    assert "ذهب الولد سريعا" in text, f"Expected spaced Arabic text, got: {text!r}"


def test_adequate_explicit_spaces_does_not_fragment_darasa() -> None:
    """A line with adequate explicit spaces must NOT fragment words like 'دراسة'."""
    # Line: "في دراسة شاملة" with explicit spaces between each word
    glyphs: list[Glyph] = [
        Glyph(y=100.0, x=10.0, text="ف", size=10.0),
        Glyph(y=100.0, x=18.0, text="ي", size=10.0),
        Glyph(y=100.0, x=26.0, text=" ", size=10.0),
        # "دراسة" with natural cursive intra-word gap between disconnected letters
        Glyph(y=100.0, x=36.0, text="د", size=10.0),
        Glyph(y=100.0, x=46.0, text="ر", size=10.0),
        Glyph(y=100.0, x=56.0, text="ا", size=10.0),
        Glyph(y=100.0, x=66.0, text="س", size=10.0),
        Glyph(y=100.0, x=74.0, text="ة", size=10.0),
        Glyph(y=100.0, x=82.0, text=" ", size=10.0),
        Glyph(y=100.0, x=92.0, text="ش", size=10.0),
        Glyph(y=100.0, x=100.0, text="ا", size=10.0),
        Glyph(y=100.0, x=108.0, text="م", size=10.0),
        Glyph(y=100.0, x=116.0, text="ل", size=10.0),
        Glyph(y=100.0, x=124.0, text="ة", size=10.0),
    ]

    text = join_glyphs_preserving_ltr(glyphs, insert_spaces=True)
    assert "دراسة" in text, f"Word 'دراسة' was fragmented in: {text!r}"
    assert "د راسة" not in text
    assert "د را سة" not in text
