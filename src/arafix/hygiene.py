"""
نظافة ما بعد الاستخراج — ليست «درجة» علاجية بل بوابةُ نظافة.

محرّكات PDF (PyMuPDF وfont shaping) تُخرج محارفَ مسافةٍ وترقيمٍ
**صحيحة المعنى خاطئة الرمز**:

  * U+00A0 NO-BREAK SPACE  ← تُرسم مسافةً وتكسر ``"دراسة مقارنة" in text``
  * U+00AD SOFT HYPHEN     ← كثيراً ما يحلّ محلّ الشرطة الحقيقية ``-``
  * مسافات يونيكود الأخرى  ← U+2000–200A وU+202F وU+205F…

هذه **ليست** علّة عربية ولا علّة اتجاه. معالجتها داخل كاشف الاتجاه
خلطٌ. فنعالجها هنا، صراحةً، قبل التشخيص — ونُبلِّغ إن غيّرنا شيئاً.

القراران الحاسمان:

  ١. NBSP وأخواتها → مسافة عادية. المعنى واحد، والمقارنة والبحث ينجحان.
  ٢. soft hyphen → شرطة ``-``. في مسارنا الهندسيّ نادراً ما يكون
     فاصلاً اختيارياً حقيقياً؛ الغالب أنه hyphen-minus أفسدَه الخط.
     (إن ظهر mid-word كفاصل سطرٍ حقيقيّ، خسارته شرطةٌ لا حرفاً.)
"""

from __future__ import annotations

import re

__all__ = [
    "sanitize_extraction",
    "count_artifacts",
    "UNICODE_SPACES",
    "SOFT_HYPHEN",
    "NBSP",
]


NBSP = "\u00a0"
SOFT_HYPHEN = "\u00ad"

#: مسافات يونيكود التي لا معنى لها في نصٍّ مُسترجَع — تُسوَّى إلى U+0020.
UNICODE_SPACES = frozenset(
    {
        "\u00a0",  # NO-BREAK SPACE
        "\u1680",  # OGHAM SPACE MARK
        "\u2000",  # EN QUAD
        "\u2001",  # EM QUAD
        "\u2002",  # EN SPACE
        "\u2003",  # EM SPACE
        "\u2004",  # THREE-PER-EM SPACE
        "\u2005",  # FOUR-PER-EM SPACE
        "\u2006",  # SIX-PER-EM SPACE
        "\u2007",  # FIGURE SPACE
        "\u2008",  # PUNCTUATION SPACE
        "\u2009",  # THIN SPACE
        "\u200a",  # HAIR SPACE
        "\u202f",  # NARROW NO-BREAK SPACE
        "\u205f",  # MEDIUM MATHEMATICAL SPACE
        "\u3000",  # IDEOGRAPHIC SPACE
    }
)

_SPACE_TABLE = {ord(ch): " " for ch in UNICODE_SPACES}

#: مسافاتٌ متتالية (بعد التسوية) تُضغط — لا المعنى.
_MULTI_SPACE = re.compile(r"[^\S\n\r]+")


def count_artifacts(text: str) -> dict[str, int]:
    """يعدّ الآثار دون تعديل — للتشخيص والاختبار."""
    if not text:
        return {"nbsp_like": 0, "soft_hyphen": 0}
    nbsp_like = sum(1 for ch in text if ch in UNICODE_SPACES)
    return {"nbsp_like": nbsp_like, "soft_hyphen": text.count(SOFT_HYPHEN)}


def sanitize_extraction(
    text: str,
    *,
    fold_unicode_spaces: bool = True,
    soft_hyphen_to: str = "-",
    collapse_spaces: bool = False,
) -> str:
    """
    ينظّف نصّاً خرج من محرّك استخراج قبل أيّ تشخيص عربيّ.

    >>> sanitize_extraction("دراسة\\u00a0مقارنة")
    'دراسة مقارنة'
    >>> sanitize_extraction("[أ\\u00adج]")
    '[أ-ج]'
    >>> sanitize_extraction("سليم")
    'سليم'
    """
    if not text:
        return text

    out = text
    if fold_unicode_spaces:
        out = out.translate(_SPACE_TABLE)
    if soft_hyphen_to is not None:
        out = out.replace(SOFT_HYPHEN, soft_hyphen_to)
    if collapse_spaces:
        # لا نمسّ فواصل الأسطر — بنية الصفحة ملك المستعمل.
        out = _MULTI_SPACE.sub(" ", out)
    return out
