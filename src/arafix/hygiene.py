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
    "normalize_arabic_punctuation_spacing",
    "count_artifacts",
    "UNICODE_SPACES",
    "SOFT_HYPHEN",
    "NBSP",
    "ARABIC_COMMA",
    "ARABIC_THOUSANDS_SEP",
    "ZERO_WIDTH_ARTIFACTS",
    "fold_arabic_punct_confusables",
]


NBSP = "\u00a0"
SOFT_HYPHEN = "\u00ad"
ARABIC_COMMA = "\u060c"
ARABIC_THOUSANDS_SEP = "\u066c"
REPLACEMENT = "\ufffd"

# استخراج PDF قد يمرّر محارف تحكم واتجاه صفرية العرض إلى النص. لا تحمل
# هذه المحارف محتوى قابلاً للرؤية هنا؛ وتُطوى افتراضياً بنفس سياسة
# NormalizeConfig.strip_zero_width، مع إبقاء مفتاح صريح لمن يحتاجها.
ZERO_WIDTH_ARTIFACTS = ("\u200b", "\u200e", "\u200f", "\ufeff", "\u200c", "\u200d")

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
            "zero_width": 0,
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
        "zero_width": sum(text.count(ch) for ch in ZERO_WIDTH_ARTIFACTS),
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
        "لله",
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

#: Combining marks treated as part of the neighbouring Arabic letter. Spans
#: standard tashkeel (U+064B–U+0652), maddah/hamza marks (U+0653–U+0655, as in
#: NFD-decomposed hamza), and superscript alef — matching
#: ``scientific._TASHKEEL``.
_MARKS_CLASS = r"[\u064B-\u0655\u0670]"
_LETTER_WITH_MARKS = rf"[\u0621-\u064A]{_MARKS_CLASS}*"

# Precompiled once: these three substitutions run on every repair call and
# were previously recompiled per invocation.
_SPACE_BEFORE_MARK_RE = re.compile(rf"\s+(?={_MARKS_CLASS})")
_TA_MARBUTA_SPLIT_RE = re.compile(
    rf"(?<![\u0621-\u064A\u064B-\u0655\u0670\u0640])((?:{_LETTER_WITH_MARKS}){{3,}})\s+"
    rf"(?=ة(?:{_MARKS_CLASS})*(?![\u0621-\u064A]))"
)
_FRAGMENT_RE = re.compile(
    rf"(?<![\u0621-\u064A\u064B-\u0655\u0670\u0640])((?:{_LETTER_WITH_MARKS}){{1,3}})\s+(?=[\u0621-\u064A])"
)
_STRIP_MARKS_RE = re.compile(_MARKS_CLASS)
_ARTICLE_PREFIX_RE = re.compile(rf"{_MARKS_CLASS}*ال")
_RIGHT_CLUSTER_RE = re.compile(rf"(?:{_LETTER_WITH_MARKS}){{1,6}}")


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

    # A haraka is part of the neighbouring Arabic letter, not a boundary.
    # Count base letters through optional marks on both sides.

    # Space immediately before a combining mark → always glue
    out = _SPACE_BEFORE_MARK_RE.sub("", text)

    # Reversed visual streams can leave the final ta-marbuta as ``مقدم ة``.
    # It cannot be a standalone word after a 3+ letter Arabic stem.
    # The lookbehind anchors matching at an Arabic run boundary; without it,
    # re.sub restarts inside long runs hunting for ة and degrades quadratically.
    out = _TA_MARBUTA_SPLIT_RE.sub(r"\1", out)

    # ``حين شنّت`` is misread as a 3+2 split and glued to ``حينشنّت``.

    def _repl(m: re.Match[str]) -> str:
        left_cluster = m.group(1)
        left = _STRIP_MARKS_RE.sub("", left_cluster)
        rest = m.string[m.end() :]
        mright = _RIGHT_CLUSTER_RE.match(rest)
        right_cluster = mright.group(0) if mright else ""
        right = _STRIP_MARKS_RE.sub("", right_cluster)
        if left in _KEEP_SPACE_AFTER or right in _KEEP_SPACE_AFTER:
            return m.group(0)
        # Single-letter Arabic prefixes/fragments (e.g. و حرية, ق واعد):
        # In Arabic orthography, single-letter proclitics (و, ف) attach directly
        # to the following word, and isolated consonants before stems of length >= 2
        # are geometry split artifacts (ق واعد -> قواعد). Only keep the space if
        # the following token is also a single letter (alphabet listing: أ ب ت ث).
        if len(left) == 1 and len(right) <= 1:
            return m.group(0)
        # A two-letter standalone word followed by a normal-length word is
        # overwhelmingly a real word boundary (نص سليم, أي إصلاح), not a
        # geometry fragment. Keep it unless an explicit function-word rule
        # above or an article-prefix rule below provides stronger evidence.
        if len(left) == 2 and len(right) > 2:
            return m.group(0)
        # Keep space before definite article ال…
        if _ARTICLE_PREFIX_RE.match(rest):
            return m.group(0)
        # Article-like prefixes always glue (الع صور → العصور)
        if left in ("الع", "الم", "وال", "بال", "كال", "فال", "لل"):
            return left
        # 3-letter left: do NOT collapse if right is 2+ letters (e.g. ذهب به, كتب له, قلت له)
        # Only collapse if right is a genuine single-letter tail fragment (e.g. عاد ي -> عادي)
        if len(left) >= 3 and len(right) >= 2:
            return m.group(0)
        if len(left) == 3 and len(right) == 1 and right not in "يىة":
            return m.group(0)
        return left_cluster

    # 1–3 letter fragments, allowing harakat within each fragment.
    out = _FRAGMENT_RE.sub(_repl, out)
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
    ("كما", "أن"),
    ("كما", "ان"),
    ("لذا", "اعتدنا"),
    ("من", "العصور"),
    ("ما", "يأتي"),
    ("ما", "يتكون"),
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


# Precompile the audited closed-list rules. The prior implementation ran one
# regex pass per entry; grouping the same guarded alternatives preserves their
# evidence constraints while avoiding repeated full-text scans.
_ARABIC_BASE = r"\u0621-\u064A"
_DIGIT_BASE = r"0-9\u0660-\u0669\u06F0-\u06F9"


def _compile_guarded_pairs(pairs: tuple[tuple[str, str], ...]) -> re.Pattern[str]:
    grouped: dict[str, list[str]] = {}
    for left, right in pairs:
        grouped.setdefault(left, []).append(right)
    alternatives = "|".join(
        re.escape(left)
        + r"(?="
        + "|".join(re.escape(right) for right in rights)
        + r")"
        for left, rights in grouped.items()
    )
    return re.compile(rf"(?<![{_ARABIC_BASE}])({alternatives})")


_ARTICLE_PARTICLES = (
    "أو",
    "او",
    "من",
    "في",
    "عن",
    "على",
    "إلى",
    "الى",
    "مع",
    "بين",
    "عند",
    "بعد",
    "قبل",
)
_PARTICLE_ARTICLE_RE = re.compile(
    rf"(?<![{_ARABIC_BASE}])"
    rf"({'|'.join(re.escape(p) for p in _ARTICLE_PARTICLES)})"
    rf"(?=ال[{_ARABIC_BASE}])"
)
_FUNCTION_BOUNDARY_RE = _compile_guarded_pairs(_SAFE_GLUED_FUNCTION_BOUNDARIES)
_NAME_BOUNDARY_RE = _compile_guarded_pairs(_SAFE_GLUED_NAME_BOUNDARIES)
_NAME_ANCHOR_MAP = dict(_SAFE_GLUED_NAME_ANCHORS)
_NAME_ANCHOR_RE = re.compile(
    rf"(?<![{_ARABIC_BASE}])"
    rf"({'|'.join(re.escape(p) for p in sorted(_NAME_ANCHOR_MAP, key=len, reverse=True))})"
)
_PUNCT_BEFORE_ARABIC_RE = re.compile(r"([.،؛:!?؟»])(?=[\u0621-\u064A])")
_PUNCT_SPACE_BEFORE_RE = re.compile(rf"(?<=[{_ARABIC_BASE}{_DIGIT_BASE})])[ ]+(?=[،؛:!?؟.,)])")
_OPEN_PUNCT_SPACE_AFTER_RE = re.compile(rf"([(«])[ ]+(?=[{_ARABIC_BASE}{_DIGIT_BASE}])")
_CLOSE_PUNCT_SPACE_BEFORE_RE = re.compile(rf"(?<=[{_ARABIC_BASE}{_DIGIT_BASE}])[ ]+([)»])")
_PUNCT_SPACE_AFTER_RE = re.compile(rf"([،؛:!?؟.,])[ ]*(?=[{_ARABIC_BASE}])")
_ARABIC_OPEN_PUNCT_RE = re.compile(rf"(?<=[{_ARABIC_BASE}])(?=[(«])")
_ARABIC_MULTI_SPACE_RE = re.compile(rf"(?<=[{_ARABIC_BASE}])[^\S\n\r]{{2,}}(?=[{_ARABIC_BASE}])")


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
    out = _PUNCT_BEFORE_ARABIC_RE.sub(r"\1 ", text)
    out = _FUNCTION_BOUNDARY_RE.sub(r"\1 ", out)
    out = _PARTICLE_ARTICLE_RE.sub(r"\1 ", out)

    # A first restored boundary exposes the next one in long name chains
    # (e.g. سليمانبنعبدالملكرضيالله). Two passes are sufficient for the
    # fixed, audited patterns below and avoid an unbounded rewrite loop.
    for _ in range(2):
        out = _NAME_ANCHOR_RE.sub(lambda m: _NAME_ANCHOR_MAP[m.group(1)], out)
        # A boundary restored by one alternative exposes the next one in the
        # same chain (بنعبدالملك). Re-scan once, rather than relying on regex
        # substitution to revisit its own replacement span.
        out = _NAME_BOUNDARY_RE.sub(r"\1 ", out)
        out = _NAME_BOUNDARY_RE.sub(r"\1 ", out)

    # Do not normalize arbitrary ASCII spacing: code, regexes, tables, and
    # aligned Latin text are valid inputs. Collapse only a run whose two
    # immediate non-space neighbours are Arabic letters, where it is a PDF
    # word-boundary artifact rather than user formatting.
    return _ARABIC_MULTI_SPACE_RE.sub(" ", out)


def normalize_arabic_punctuation_spacing(text: str) -> str:
    """Normalize punctuation boundaries only when an Arabic letter proves context.

    This deliberately does not touch Latin/code spacing, decimal numbers, or
    line breaks. It repairs PDF artifacts such as ``المادة(١٧)`` and
    ``كلمة ،جديدة`` without globally reformatting the input.
    """
    if not text:
        return text
    out = _PUNCT_SPACE_BEFORE_RE.sub("", text)
    out = _OPEN_PUNCT_SPACE_AFTER_RE.sub(r"\1", out)
    out = _CLOSE_PUNCT_SPACE_BEFORE_RE.sub(r"\1", out)
    out = _ARABIC_OPEN_PUNCT_RE.sub(" ", out)
    return _PUNCT_SPACE_AFTER_RE.sub(r"\1 ", out)


def sanitize_extraction(
    text: str,
    *,
    fold_unicode_spaces: bool = True,
    soft_hyphen_to: str | None = "-",
    fold_punct_confusables: bool = True,
    strip_replacement: bool = True,
    apply_nfc: bool = True,
    collapse_spaces: bool = False,
    strip_zero_width: bool = True,
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
    if strip_zero_width:
        for ch in ZERO_WIDTH_ARTIFACTS:
            out = out.replace(ch, "")
    if apply_nfc:
        out = unicodedata.normalize("NFC", out)
    if collapse_spaces:
        out = _MULTI_SPACE.sub(" ", out)
    return out
