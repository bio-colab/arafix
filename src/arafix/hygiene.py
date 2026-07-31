"""
نظافة ما بعد الاستخراج — ليست «درجة» علاجية بل بوابةُ نظافة.

محرّكات PDF (PyMuPDF وfont shaping) تُخرج محارفَ مسافةٍ وترقيمٍ
**صحيحة المعنى خاطئة الرمز**:

  * U+00A0 NO-BREAK SPACE  ← تُرسم مسافةً وتكسر ``"دراسة مقارنة" in text``
  * U+00AD SOFT HYPHEN     ← كثيراً ما يحلّ محلّ الشرطة الحقيقية ``-``
  * مسافات يونيكود الأخرى  ← U+2000–200A وU+202F وU+205F…
  * U+066C ARABIC THOUSANDS SEPARATOR ← يحلّ محلّ الفاصلة العربية
    ``،`` (U+060C) على بعض المنصّات/الخطوط (وُثِّق على macOS CI).

هذه **ليست** علّة عربية ولا علّة اتجاه. معالجتها داخل كاشف الاتجاه
خلطٌ. فنعالجها هنا، صراحةً، قبل التشخيص — ونُبلِّغ إن غيّرنا شيئاً.
"""

from __future__ import annotations

import re

__all__ = [
    "sanitize_extraction",
    "count_artifacts",
    "UNICODE_SPACES",
    "SOFT_HYPHEN",
    "NBSP",
    "ARABIC_COMMA",
    "ARABIC_THOUSANDS_SEP",
    "fold_arabic_punct_confusables",
]


NBSP = "\u00a0"
SOFT_HYPHEN = "\u00ad"
ARABIC_COMMA = "\u060c"  # ،
ARABIC_THOUSANDS_SEP = "\u066c"  # ٬  — confusable with Arabic comma in PDFs
ARABIC_DECIMAL_SEP = "\u066b"  # ٫

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

#: أرقام أوروبية وعربية-هندية وفارسية — جوار فاصل الآلاف الحقيقي.
_DIGIT_CHARS = frozenset("0123456789٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹")


def _is_digit(ch: str) -> bool:
    return ch in _DIGIT_CHARS


def fold_arabic_punct_confusables(text: str) -> str:
    """
    يطوي محارف الترقيم المتشابهة التي تُفسدها خرائط الخطوط.

    ``U+066C`` (فاصل الآلاف) يظهر بدل ``U+060C`` (الفاصلة العربية) بعد
    الاستخراج على بعض أنظمة الماك/الخطوط. إن كان المحرف **بين رقمين**
    نُبقيه — فهناك وظيفته الحقيقية (١٬٠٠٠). وفي غير ذلك نردّه فاصلةً.

    >>> fold_arabic_punct_confusables("أولاً\\u066c ثانياً")
    'أولاً، ثانياً'
    >>> fold_arabic_punct_confusables("١\\u066c٠٠٠")
    '١٬٠٠٠'
    """
    if ARABIC_THOUSANDS_SEP not in text:
        return text

    out: list[str] = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch == ARABIC_THOUSANDS_SEP:
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < n else ""
            if _is_digit(prev) and _is_digit(nxt):
                out.append(ch)
            else:
                out.append(ARABIC_COMMA)
        else:
            out.append(ch)
    return "".join(out)


def count_artifacts(text: str) -> dict[str, int]:
    """يعدّ الآثار دون تعديل — للتشخيص والاختبار."""
    if not text:
        return {"nbsp_like": 0, "soft_hyphen": 0, "thousands_as_comma": 0}
    nbsp_like = sum(1 for ch in text if ch in UNICODE_SPACES)
    # مرشّحات ٬ التي *ستُطوى* (ليست بين رقمين)
    thousands_as_comma = 0
    n = len(text)
    for i, ch in enumerate(text):
        if ch != ARABIC_THOUSANDS_SEP:
            continue
        prev = text[i - 1] if i > 0 else ""
        nxt = text[i + 1] if i + 1 < n else ""
        if not (_is_digit(prev) and _is_digit(nxt)):
            thousands_as_comma += 1
    return {
        "nbsp_like": nbsp_like,
        "soft_hyphen": text.count(SOFT_HYPHEN),
        "thousands_as_comma": thousands_as_comma,
    }


def sanitize_extraction(
    text: str,
    *,
    fold_unicode_spaces: bool = True,
    soft_hyphen_to: str = "-",
    fold_punct_confusables: bool = True,
    collapse_spaces: bool = False,
) -> str:
    """
    ينظّف نصّاً خرج من محرّك استخراج قبل أيّ تشخيص عربيّ.

    >>> sanitize_extraction("دراسة\\u00a0مقارنة")
    'دراسة مقارنة'
    >>> sanitize_extraction("[أ\\u00adج]")
    '[أ-ج]'
    >>> sanitize_extraction("أولاً\\u066c ثانياً")
    'أولاً، ثانياً'
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
    if fold_punct_confusables:
        out = fold_arabic_punct_confusables(out)
    if collapse_spaces:
        # لا نمسّ فواصل الأسطر — بنية الصفحة ملك المستعمل.
        out = _MULTI_SPACE.sub(" ", out)
    return out
