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
    "collapse_midword_spaces",
    "insert_particle_spaces",
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


#: Short Arabic function words that must keep a following space when
#: geometry inserts one (do not glue ``في السجن`` → ``فيالسجن``).
_KEEP_SPACE_AFTER = frozenset(
    {
        "في",
        "من",
        "عن",
        "على",
        "إلى",
        "الى",
        "أو",
        "او",
        "لا",
        "ما",
        "أن",
        "إن",
        "لم",
        "لن",
        "قد",
        "بل",
        "كي",
        "مع",
        "هو",
        "هي",
        "ثم",
        "كل",
        "حتى",
        "هذا",
        "هذه",
        "ذلك",
        "تلك",
        "بين",
        "عند",
        "قبل",
        "بعد",
        "غير",
        "سوى",
        "منذ",
        "نحو",
        "كان",
        "قال",
        "وقد",
        "فقد",
        "كما",
        "لذا",
        "لكن",
        "ولو",
        "ولا",
        "وما",
        "وهو",
        "وهي",
        "أنا",
        "أنت",
        "نحن",
        "هم",
        "هن",
    }
)

#: Particles that often glue to the next word in book PDFs; insert a space
#: after them when missing. Longest first. Avoid short stems that begin
#: ordinary words (لا/ما/قد/أن…). Evidence: thumb_red gold loop 3.
_PARTICLE_SPACE_AFTER: tuple[str, ...] = (
    "كذلك",
    "لذلك",
    "عندما",
    "بينما",
    "حيثما",
    "بعدما",
    "قبلما",
    "وكذلك",
    "كما",
    "لذا",
    "فقد",
    "وقد",
    "ولكن",
    "لكن",
    "ولو",
    "حتى",
    "على",
    "إلى",
    "الى",
    "عند",
    "بين",
    "قبل",
    "بعد",
    "نحو",
    "منذ",
    "غير",
    "سوى",
    "هذا",
    "هذه",
    "ذلك",
    "تلك",
    "كان",
    "قال",
    "ثم",
    "أو",
    "او",
    "في",
    "من",
    "عن",
    "مع",
)


#: Single letters that often end a real word before a space (do not glue
#: ``صلَّى الله`` → ``صلَّىالله``).
_NO_COLLAPSE_SINGLE = frozenset("اأإآةىوويف")


def collapse_midword_spaces(text: str) -> str:
    """
    Remove geometry-inserted spaces that sit *inside* Arabic words.

    Book PDFs often yield false splits like ``مو ضع`` / ``أي ضًا`` / ``عاد ي``
    when glyph advances vary. Keep spaces after/before function words and
    before the article ``ال``.

    Evidence: thumb_red (بصمة الإبهام الحمراء) spacing loops vs manual gold.
    """
    if not text or " " not in text:
        return text

    # Space immediately before a combining mark → always glue
    out = re.sub(r"\s+(?=[\u064B-\u0652\u0670])", "", text)

    def _repl(m: re.Match[str]) -> str:
        left = m.group(1)
        rest = m.string[m.end() :]
        mright = re.match(r"[\u0621-\u064A]{1,6}", rest)
        right = mright.group(0) if mright else ""
        if left in _KEEP_SPACE_AFTER or right in _KEEP_SPACE_AFTER:
            return m.group(0)
        if len(left) == 1 and left in _NO_COLLAPSE_SINGLE:
            return m.group(0)
        # A two-letter standalone word followed by a normal-length word is
        # overwhelmingly a real word boundary (نص سليم, أي إصلاح), not a
        # geometry fragment. Keep it unless an explicit function-word rule
        # above or an article-prefix rule below provides stronger evidence.
        if len(left) <= 2 and len(right) > 2:
            return m.group(0)
        # Keep space before definite article ال…
        if re.match(r"[\u064B-\u0652\u0670]*ال", rest):
            return m.group(0)
        # Article-like prefixes always glue (الع صور → العصور)
        if left in ("الع", "الم", "وال", "بال", "كال", "فال", "لل"):
            return left
        # 3-letter left: only collapse when right is short (1–2) mid-word junk
        # (``عاد ي``) — not ``بكم في`` (right is a function word, already kept)
        if len(left) == 3 and len(right) > 2:
            return m.group(0)
        return left

    # 1–3 letter left fragment + space + Arabic letter
    out = re.sub(
        r"(?<![\u0621-\u064A])([\u0621-\u064A]{1,3})\s+(?=[\u0621-\u064A])",
        _repl,
        out,
    )
    return out


#: Glued particles safe to split only when followed by ال… or a long stem
#: (avoids منثورة → من ثورة, أولاً → أو لاً).
# Boundaries repeatedly lost by glyph geometry in the independent book
# benchmark. Each pair is explicit rather than a generic prefix rule: Arabic
# function words are productive stems too, so broad splitting would corrupt
# ordinary words. The tuple is deliberately small and easy to audit.
_SAFE_GLUED_FUNCTION_BOUNDARIES: tuple[tuple[str, str], ...] = (
    ("في", "هذا"),
    ("في", "هذه"),
    ("هو", "الذي"),
    ("هو", "التي"),
    ("أن", "هذا"),
    ("أن", "هذه"),
    ("أن", "يكون"),
    ("لا", "يمكن"),
    ("من", "دون"),
    ("لم", "يكن"),
    ("إلى", "أن"),
    ("الى", "أن"),
    ("إن", "كان"),
    ("غير", "أن"),
)


# Name-link and honorific pairs occur in a restricted written form, so they
# are safe to restore as explicit pairs without attempting general NER.
_SAFE_GLUED_NAME_BOUNDARIES: tuple[tuple[str, str], ...] = (
    ("بن", "عبد"),
    ("عبد", "الملك"),
    ("عبد", "العزيز"),
    ("رضي", "الله"),
)

# These prefixes and suffixes seed an otherwise unbounded name chain, then
# the pairs above complete it after a real space has been restored.
_SAFE_GLUED_NAME_ANCHORS: tuple[tuple[str, str], ...] = (
    ("سليمانبن", "سليمان بن"),
    ("عمربن", "عمر بن"),
    ("الملكرضي", "الملك رضي"),
    ("العزيزرضي", "العزيز رضي"),
)


_GLUE_SPLIT_SAFE: tuple[str, ...] = (
    "وكذلك",
    "كذلك",
    "لذلك",
    "عندما",
    "بينما",
    "حيثما",
    "بعدما",
    "قبلما",
    "كما",
    "لذا",
    "فقد",
    "وقد",
    "ولكن",
    "لكن",
    "ولو",
)


def insert_particle_spaces(text: str) -> str:
    """
    Insert a space after common Arabic particles glued to the next word.

    Conservative: punctuation spaces always; particle split only for a small
    safe list when followed by ``ال…`` or a stem of length ≥ 3
    (``كماأن``، ``لذااعتدنا``، ``منالعصور``).

    Evidence: thumb_red gold loop 3 — not applied blindly to healthy text.
    """
    if not text:
        return text
    out = text
    # punctuation often lacks following space in book extracts
    out = re.sub(r"([.،؛:!?؟»])(?=[\u0621-\u064A])", r"\1 ", out)
    _B = r"\u0621-\u064A"
    # من/في/على… + ال
    for p in ("من", "في", "عن", "على", "إلى", "الى", "مع", "بين", "عند", "بعد", "قبل"):
        out = re.sub(
            rf"(?<![{_B}]){re.escape(p)}(?=ال[{_B}])",
            p + " ",
            out,
        )
    # High-confidence glued pairs observed in real PDF output. Require a
    # non-Arabic left boundary so a pair is never cut out of a larger word.
    for left, right in _SAFE_GLUED_FUNCTION_BOUNDARIES:
        out = re.sub(
            rf"(?<![{_B}]){re.escape(left)}(?={re.escape(right)})",
            left + " ",
            out,
        )

    # A first restored boundary exposes the next one in long name chains
    # (e.g. سليمانبنعبدالملكرضيالله). Two passes are sufficient for the
    # fixed, audited patterns below and avoid an unbounded rewrite loop.
    for _ in range(2):
        for glued, restored in _SAFE_GLUED_NAME_ANCHORS:
            out = re.sub(
                rf"(?<![{_B}]){re.escape(glued)}",
                restored,
                out,
            )
        for left, right in _SAFE_GLUED_NAME_BOUNDARIES:
            out = re.sub(
                rf"(?<![{_B}]){re.escape(left)}(?={re.escape(right)})",
                left + " ",
                out,
            )

    # safe multi-char particles + any Arabic stem ≥ 2 letters
    for p in _GLUE_SPLIT_SAFE:
        out = re.sub(
            rf"(?<![{_B}]){re.escape(p)}(?=[{_B}]{{2,}})",
            p + " ",
            out,
        )
    out = re.sub(r"[^\S\n\r]{2,}", " ", out)
    return out


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
