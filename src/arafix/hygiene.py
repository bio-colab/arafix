"""
نظافة ما بعد الاستخراج — ليست «درجة» علاجية بل بوابةُ نظافة.

محرّكات PDF (PyMuPDF وfont shaping) تُخرج محارفَ مسافةٍ وترقيمٍ
**صحيحة المعنى خاطئة الرمز**:

  * U+00A0 NO-BREAK SPACE  ← تُرسم مسافةً وتكسر ``"دراسة مقارنة" in text``
  * U+00AD SOFT HYPHEN     ← كثيراً ما يحلّ محلّ الشرطة الحقيقية ``-``
  * مسافات يونيكود الأخرى  ← U+2000–200A وU+202F وU+205F…
  * U+066C ARABIC THOUSANDS SEPARATOR ← بدل الفاصلة العربية ``،`` (macOS)
  * U+FFFD REPLACEMENT ← جليف بلا خريطة؛ يُحذف

**تشكيل Presentation Forms (U+FE70–FE7F) لا يُطوى هنا عمداً.**
تحويلُها مبكراً إلى Mn يُلصق العلامة بالجار قبل العكس → ``نشُرت``.
التأجيل إلى ``expand_deferred_forms`` بعد الاتجاه هو العلاج الصحيح
(انظر اختبار ``test_deferring_them_preserves_the_diacritic``).
وما أُصلح في الجداول: الأشكال المعزولة كانت تُفكَّك إلى مسافة+علامة.
"""

from __future__ import annotations

import re
import unicodedata

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
ARABIC_COMMA = "\u060c"
ARABIC_THOUSANDS_SEP = "\u066c"
REPLACEMENT = "\ufffd"

UNICODE_SPACES = frozenset(
    {
        "\u00a0",
        "\u1680",
        "\u2000",
        "\u2001",
        "\u2002",
        "\u2003",
        "\u2004",
        "\u2005",
        "\u2006",
        "\u2007",
        "\u2008",
        "\u2009",
        "\u200a",
        "\u202f",
        "\u205f",
        "\u3000",
    }
)

_SPACE_TABLE = {ord(ch): " " for ch in UNICODE_SPACES}
_MULTI_SPACE = re.compile(r"[^\S\n\r]+")
_DIGIT_CHARS = frozenset("0123456789٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹")


def _is_digit(ch: str) -> bool:
    return ch in _DIGIT_CHARS


def fold_arabic_punct_confusables(text: str) -> str:
    """
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
    if not text:
        return {
            "nbsp_like": 0,
            "soft_hyphen": 0,
            "thousands_as_comma": 0,
            "replacement": 0,
            "spacing_diacritic_pf": 0,
        }
    nbsp_like = sum(1 for ch in text if ch in UNICODE_SPACES)
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
        "replacement": text.count(REPLACEMENT),
        "spacing_diacritic_pf": sum(1 for c in text if 0xFE70 <= ord(c) <= 0xFE7F),
    }


def sanitize_extraction(
    text: str,
    *,
    fold_unicode_spaces: bool = True,
    soft_hyphen_to: str = "-",
    fold_punct_confusables: bool = True,
    strip_replacement: bool = True,
    apply_nfc: bool = True,
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
    if strip_replacement:
        out = out.replace(REPLACEMENT, "")
    if apply_nfc:
        out = unicodedata.normalize("NFC", out)
    if collapse_spaces:
        out = _MULTI_SPACE.sub(" ", out)
    return out
