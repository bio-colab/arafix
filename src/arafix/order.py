"""
الدرجة ٢ — الاتجاه: من الترتيب البصري إلى الترتيب المنطقي.

المسألة بدقّة: بعض مُصدِّرات PDF تخزّن الجليفات بترتيب رسمها على
الشاشة (يساراً فيميناً)، لا بترتيب قراءتها. فحين تقرأ الأداة الملف
تسلسلياً تحصل على «مرحبا» مكتوبةً «ابحرم».

الخطأ الشائع في العلاج: `text[::-1]`.

لِمَ هو خطأ؟ لأن الأرقام والمقاطع اللاتينية **لم تُعكس** أصلاً؛ فهي
LTR في نصٍّ بصريّ كما هي LTR في نصٍّ منطقيّ. فعكس السطر كلّه يصلح
العربية ويفسد «2024» فتصير «4202»، ويفسد «GDP» فتصير «PDG».

فالعلاج الصحيح:

  1. اعكس السطر (عناقيد grapheme).
  2. استعد جزر LTR بذكاء: عكس تقليدي ما لم تكن الجزيرة أصلاً سليمة
     (مبالغ/عملات بعد عكس codepoint كامل).
  3. اعكس المحارف المرآتية: ( ↔ ) و [ ↔ ] …
  4. أصلح أقواس المبالغ المنقلبة، ونطاقات الصفحات، وترقيم الجملة.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .types import RepairResult, Stage

__all__ = [
    "ReorderConfig",
    "reverse_visual_line",
    "fix_order",
    "MIRROR_PAIRS",
    "grapheme_clusters",
    "order_combining_marks",
    "normalize_page_ranges",
    "relocate_sentence_punctuation",
    "repair_inverted_ltr_parens",
]


#: المحارف التي يقلب العكس دلالتها فتجب مرآتها.
MIRROR_PAIRS = {
    "(": ")", ")": "(",
    "[": "]", "]": "[",
    "{": "}", "}": "{",
    "<": ">", ">": "<",
    "\u00ab": "\u00bb", "\u00bb": "\u00ab",   # « »
    "\u2039": "\u203a", "\u203a": "\u2039",   # ‹ ›
    "\u201c": "\u201d", "\u201d": "\u201c",   # “ ”
}

#: LTR atom + continuers (digits, Latin, hyphen/slash inside dates & codes).
_LTR_ATOM = r"[0-9\u0660-\u0669\u06F0-\u06F9A-Za-z\u00C0-\u024F]"
_LTR_CONT = (
    r"[0-9\u0660-\u0669\u06F0-\u06F9A-Za-z\u00C0-\u024F"
    r".,:/\\\-+%°'\u2019_\u2013\u2014]"
)
#: Currency/percent often sit on the edge of a number; after reverse they
#: land on the wrong side unless the island includes them (``3.5%`` ↔ ``%5.3``).
_LTR_EDGE = r"[%#$€£]"
#: Island: optional edge marks + LTR tokens separated by spaces
#: (``M/V Ever Lovely``, ``13-7``, ``GDP_2024``, ``3.5%``).
_LTR_RUN = re.compile(
    rf"{_LTR_EDGE}*{_LTR_ATOM}{_LTR_CONT}*"
    rf"(?:[ \t]+{_LTR_EDGE}*{_LTR_ATOM}{_LTR_CONT}*)*"
    rf"{_LTR_EDGE}*"
)

#: فرق الدرجة الذي يبرّر الإبقاء على الجزيرة بدل إعادة عكسها التقليدية.
_LTR_SCORE_MARGIN = 2.0

_CURRENCY_CODE = re.compile(
    r"\b(?:USD|EUR|GBP|IQD|SAR|AED|YER|OMR|KWD|BHD|QAR|EGP|JOD)\b",
    re.IGNORECASE,
)

_PAGE_RANGE_SAD = re.compile(r"(ص\s*\.?\s*)(\d+)\s*([-–—])\s*(\d+)")
_PAGE_RANGE_SAD_AFTER = re.compile(r"(\d+)\s*([-–—])\s*(\d+)(\s*\.?\s*ص\b)")
_PAGE_RANGE_P = re.compile(
    r"\b(p{1,2}\s*\.?\s*)(\d+)\s*([-–—])\s*(\d+)",
    re.IGNORECASE,
)
_INVERTED_PARENS = re.compile(r"\)([^()\n]{1,48})\(")
_LEADING_DOT_YEAR = re.compile(r"(?<![\d.])\.(\d{4})\b")
_LEADING_DOT_AFTER_AR = re.compile(
    r"(?<=[\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF])\.(\d{2,})\b"
)
_DOUBLE_SENTENCE_DOTS = re.compile(r"\.{2,}")

#: Arabic shadda — must precede vowel marks on the same base (UAX #9 / CLDR).
_SHADDA = "\u0651"
_ARABIC_VOWEL_MARKS = frozenset(
    "\u064b\u064c\u064d\u064e\u064f\u0650\u0652\u0653\u0657\u0658\u0670"
)


def _is_markable_base(ch: str) -> bool:
    """True if *ch* is a letter that may carry combining marks."""
    return bool(ch) and unicodedata.category(ch).startswith("L")


def order_combining_marks(marks: str) -> str:
    """
    Canonical mark order on one base: **shadda, then vowels/other Mn**.

    PDF streams and nearest-base binding can append marks in any order
    (``ُّ`` vs ``ُّ``). Stacked Arabic is conventionally shadda then vowel
    (``حَقٌّ`` not ``حٌّق`` with shadda after tanwin on the wrong slot).

    >>> order_combining_marks("\u064c\u0651")  # dammatan then shadda in
    '\u0651\u064c'
    >>> order_combining_marks("\u0651\u064e")  # already shadda + fatha
    '\u0651\u064e'
    """
    if not marks or len(marks) == 1:
        return marks
    shadda = [c for c in marks if c == _SHADDA]
    rest = [c for c in marks if c != _SHADDA]
    return "".join(shadda) + "".join(rest)


def _with_ordered_marks(cluster: str) -> str:
    """Reorder combining marks inside a base+marks cluster."""
    if len(cluster) < 2:
        return cluster
    base, marks = cluster[0], cluster[1:]
    if not marks:
        return cluster
    return base + order_combining_marks(marks)


def grapheme_clusters(text: str) -> list[str]:
    """
    Split *text* into grapheme clusters: base letter + its combining marks.

    **The reverse unit is the cluster, not the code point.** Combining marks
    (category Mn) have zero advance width and share their base's position;
    reversing code points tears a mark off its letter:

        أولاً  →  [code-point reverse]  →  أوًلا

    Unicode logical order puts marks *after* their base. Visual-order PDF
    streams often emit the mark *before* the base (or after a space). Naïvely
    gluing Mn onto whatever precedes it attaches harakat to spaces/punctuation;
    after reverse they become leading marks (``َحرب`` instead of ``حربَ``).

    **Grapheme Cluster Protection (P0):**

    * Mn after a letter base → glue to that base (logical Unicode).
    * Mn otherwise → hold as *pending* and glue onto the next letter base.
    * Never glue Mn onto whitespace or punctuation.
    * Orphan marks at end of line attach to the last letter base if any.
    * Marks on a base are ordered: shadda before vowels (P1).

    Within each cluster, marks stay in logical order (base then marks). Only
    the sequence of clusters is reversed by :func:`reverse_visual_line`.

    >>> grapheme_clusters("\u062b\u0627\u0646\u064a\u0627\u064b.")
    ['ث', 'ا', 'ن', 'ي', 'اً', '.']
    >>> grapheme_clusters("\u064e\u0628")  # visual: fatha before beh
    ['بَ']
    >>> grapheme_clusters(" \u064e\u0628")  # mark after space, before letter
    [' ', 'بَ']
    """
    out: list[str] = []
    pending: list[str] = []

    for ch in text:
        if unicodedata.category(ch) == "Mn":
            if out and _is_markable_base(out[-1][0]):
                out[-1] = _with_ordered_marks(out[-1] + ch)
            else:
                pending.append(ch)
            continue
        if _is_markable_base(ch):
            out.append(_with_ordered_marks(ch + "".join(pending)))
            pending.clear()
        else:
            out.append(ch)

    if pending:
        marks = "".join(pending)
        for i in range(len(out) - 1, -1, -1):
            if out[i] and _is_markable_base(out[i][0]):
                out[i] = _with_ordered_marks(out[i] + marks)
                break
        else:
            out.append(marks)
    return out


@dataclass
class ReorderConfig:
    """مفاتيح إصلاح الاتجاه."""

    protect_ltr_runs: bool = True
    mirror_brackets: bool = True

    #: اعكس العناقيد لا المحارف. لا تطفئه إلا لتشخيصٍ مقارن.
    cluster_aware: bool = True

    #: عالج كل سطر على حدة. صحيح دائماً تقريباً: الانعكاس ظاهرة سطرية،
    #: لأن مُصدِّر PDF يبني كل سطر مستقلاً.
    per_line: bool = True

    #: بعد العكس: فضّل الشكل الأحسن تشكيلاً للجزيرة LTR بدل عكس أعمى.
    smart_ltr_restore: bool = True

    #: صفّ نطاقات الصفحات بجانب «ص» / p. تصاعدياً.
    normalize_page_ranges: bool = True

    #: أعد أقواس المبالغ المنقلبة ``)…(`` → ``(…)`` حول LTR.
    repair_ltr_parens: bool = True

    #: انقل نقطة الجملة الملتصقة بسنة/رقم إلى طرف الجزيرة الصحيح.
    relocate_sentence_punct: bool = True


def _mirror(ch: str) -> str:
    return MIRROR_PAIRS.get(ch, ch)


def _ltr_wellformed_score(s: str) -> float:
    """
    درجة «معقولية» جزيرة LTR — أعلى = أجدر أن تُبقى دون إعادة عكس.

    تُميّز ``USD 1,250.00`` عن ``00.052,1 DSU`` و``2024`` عن ``4202``.
    """
    if not s:
        return -100.0
    score = 0.0
    t = s.strip()

    # أصفار بادئة مشبوهة (041، 00.052) لا في الكسور العشرية السليمة.
    if re.search(r"(?:^|[^0-9.])0\d", t):
        score -= 5.0

    if re.search(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", t):
        score += 6.0
    if re.search(r"\d+\.\d{2}\b", t):
        score += 3.0
    if _CURRENCY_CODE.search(t):
        score += 5.0
    if any(c in t for c in "$€£"):
        score += 2.0

    # نسبة مئوية: الرقم ثم % لا العكس.
    if re.search(r"\d(?:\.\d+)?%\s*$", t):
        score += 3.0
    if t.startswith("%"):
        score -= 1.5

    core = t.strip(".,;:%")
    if re.fullmatch(r"(?:19|20)\d{2}", core):
        score += 6.0

    m = re.fullmatch(r"(\d+)\s*([-–—])\s*(\d+)", t)
    if m:
        left, right = m.group(1), m.group(3)
        if left.startswith("0") or right.startswith("0"):
            score -= 4.0
        # لا نفضّل التصاعد بقوة: تواريخ 13-7 شائعة؛ هامش صغير فقط.
        try:
            if int(left) <= int(right):
                score += 0.3
        except ValueError:
            pass

    if t[:1] in ",":
        score -= 4.0
    if t.startswith(".") and not re.match(r"\.\d+$", t):
        score -= 2.0

    for w in re.findall(r"[A-Za-z]+", t):
        if w.isupper() and 2 <= len(w) <= 5:
            score += 2.0
        elif len(w) >= 3:
            vowels = sum(c in "aeiouAEIOU" for c in w)
            score += 0.5 if vowels else -1.0

    return score


def _restore_one_ltr_run(run: str, *, smart: bool) -> str:
    """استعادة جزيرة LTR بعد عكس السطر."""
    if not smart:
        return run[::-1]
    flipped = run[::-1]
    s0 = _ltr_wellformed_score(run)
    s1 = _ltr_wellformed_score(flipped)
    # إن تفوّقت الصيغة الحالية بهامش واضح أبقِها (مبلغ سليم بعد عكس كامل).
    if s0 > s1 + _LTR_SCORE_MARGIN:
        return run
    if s1 > s0 + _LTR_SCORE_MARGIN:
        return flipped
    # الافتراضي الهندسي: أعد عكس LTR.
    return flipped


def _restore_ltr_runs(text: str, *, smart: bool) -> str:
    return _LTR_RUN.sub(lambda m: _restore_one_ltr_run(m.group(0), smart=smart), text)


def _looks_ltr_heavy(inner: str) -> bool:
    s = inner.strip()
    if not s:
        return False
    if _CURRENCY_CODE.search(s) or any(c in s for c in "$€£%"):
        return True
    ltr = sum(
        1
        for c in s
        if c.isdigit()
        or ("A" <= c <= "Z")
        or ("a" <= c <= "z")
        or c in ".,-+/$€£% \t"
    )
    return (ltr / len(s)) >= 0.65 and any(c.isdigit() or c.isalpha() for c in s)


def repair_inverted_ltr_parens(text: str) -> str:
    """
    ``) -USD 1,250.00 (`` بعد المرآة → ``(-USD 1,250.00)``.

    >>> repair_inverted_ltr_parens("الصافي )-USD 1,250.00(")
    'الصافي (-USD 1,250.00)'
    """
    if ")" not in text or "(" not in text:
        return text

    def repl(m: re.Match[str]) -> str:
        inner = m.group(1)
        if _looks_ltr_heavy(inner):
            return f"({inner})"
        return m.group(0)

    return _INVERTED_PARENS.sub(repl, text)


def _swap_range_if_descending(a: str, b: str) -> tuple[str, str]:
    try:
        ia, ib = int(a), int(b)
    except ValueError:
        return a, b
    if ia > ib:
        return b, a
    return a, b


def normalize_page_ranges(text: str) -> str:
    """
    صفّ نطاقات الصفحات بجانب «ص» / p. من الأصغر للأكبر.

    >>> normalize_page_ranges("مرجع البحث (ص. 140-125)")
    'مرجع البحث (ص. 125-140)'
    """
    if not text:
        return text

    def sad(m: re.Match[str]) -> str:
        a, b = _swap_range_if_descending(m.group(2), m.group(4))
        return f"{m.group(1)}{a}{m.group(3)}{b}"

    def sad_after(m: re.Match[str]) -> str:
        a, b = _swap_range_if_descending(m.group(1), m.group(3))
        return f"{a}{m.group(2)}{b}{m.group(4)}"

    def pfx(m: re.Match[str]) -> str:
        a, b = _swap_range_if_descending(m.group(2), m.group(4))
        return f"{m.group(1)}{a}{m.group(3)}{b}"

    out = _PAGE_RANGE_SAD.sub(sad, text)
    out = _PAGE_RANGE_SAD_AFTER.sub(sad_after, out)
    out = _PAGE_RANGE_P.sub(pfx, out)
    return out


def relocate_sentence_punctuation(text: str) -> str:
    """
    انقل النقطة الملتصقة بمقدمة سنة/رقم إلى نهايتها (ترقيم جملة).

    >>> relocate_sentence_punctuation("يتم في عام .2024")
    'يتم في عام 2024.'
    """
    if not text or "." not in text:
        return text
    out = _LEADING_DOT_YEAR.sub(r"\1.", text)
    out = _LEADING_DOT_AFTER_AR.sub(r"\1.", out)
    # نقاط جملة مكررة شاردة.
    out = _DOUBLE_SENTENCE_DOTS.sub(".", out)
    return out


def reverse_visual_line(line: str, config: ReorderConfig | None = None) -> str:
    """
    يحوّل سطراً مخزَّناً بصرياً إلى ترتيبه المنطقي.

    >>> reverse_visual_line("ابحرم")
    'مرحبا'

    ويحمي الأرقام من الانقلاب:

    >>> reverse_visual_line("2024 ماع")
    'عام 2024'

    والعلامة تلزم حرفها ولا تنفصل عنه:

    >>> reverse_visual_line(".\u0627\u064b\u064a\u0646\u0627\u062b")
    'ثانياً.'
    """
    cfg = config or ReorderConfig()

    units = grapheme_clusters(line) if cfg.cluster_aware else list(line)
    out = "".join(reversed(units))

    if cfg.protect_ltr_runs:
        # بعد عكس السطر: استعد LTR (ذكي أو تقليدي).
        out = _restore_ltr_runs(out, smart=cfg.smart_ltr_restore)

    if cfg.mirror_brackets:
        out = "".join(_mirror(c) for c in out)

    if cfg.repair_ltr_parens:
        out = repair_inverted_ltr_parens(out)

    if cfg.normalize_page_ranges:
        out = normalize_page_ranges(out)

    if cfg.relocate_sentence_punct:
        out = relocate_sentence_punctuation(out)

    return out


def fix_order(text: str, config: ReorderConfig | None = None) -> str:
    """يطبّق `reverse_visual_line` على النص، سطراً سطراً افتراضياً."""
    cfg = config or ReorderConfig()
    if not cfg.per_line:
        return reverse_visual_line(text, cfg)
    return "\n".join(reverse_visual_line(ln, cfg) for ln in text.split("\n"))


def fix_order_result(text: str, config: ReorderConfig | None = None) -> RepairResult:
    """
    غلافٌ يشخّص أوّلاً ثم يصلح **إن لزم فقط**.

    قاعدة صريحة: لا يعكس هذه الدالة نصاً سليماً. الدرجة ٢ لا تُطبَّق
    إلا بشاهدٍ من الدرجة ٠، وإلا خرّبنا بأيدينا ما كان صحيحاً.
    """
    from .diagnose import DEFAULT_THRESHOLDS, detect_visual_order, diagnose

    dg = diagnose(text)
    score, _ = detect_visual_order(text)

    if score <= DEFAULT_THRESHOLDS["visual_order"]:
        return RepairResult(
            text=text,
            original=text,
            diagnosis=dg,
            stages_applied=[],
            confidence=1.0,
            notes=[f"لم يُعكس: درجة الاتجاه {score:.2f} دون العتبة"],
        )

    return RepairResult(
        text=fix_order(text, config),
        original=text,
        diagnosis=dg,
        stages_applied=[Stage.REORDER],
        confidence=round(min(1.0, abs(score)), 3),
        notes=[f"عُكس بدرجة اتجاه {score:.2f}"],
    )
