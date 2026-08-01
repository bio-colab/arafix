"""
الدرجة ٢ — الاتجاه: من الترتيب البصري إلى الترتيب المنطقي.

المسألة بدقّة: بعض مُصدِّرات PDF تخزّن الجليفات بترتيب رسمها على
الشاشة (يساراً فيميناً)، لا بترتيب قراءتها. فحين تقرأ الأداة الملف
تسلسلياً تحصل على «مرحبا» مكتوبةً «ابحرم».

الخطأ الشائع في العلاج: `text[::-1]`.

لِمَ هو خطأ؟ لأن الأرقام والمقاطع اللاتينية **لم تُعكس** أصلاً؛ فهي
LTR في نصٍّ بصريّ كما هي LTR في نصٍّ منطقيّ. فعكس السطر كلّه يصلح
العربية ويفسد «2024» فتصير «4202»، ويفسد «GDP» فتصير «PDG».

فالعلاج الصحيح ثلاث خطوات:
  1. اعكس السطر كلّه.
  2. أعِد عكس كل مقطع محايد الاتجاه (أرقام، لاتيني) إلى وضعه.
  3. اعكس المحارف المرآتية: ( ↔ ) و [ ↔ ] و « ↔ ».

الخطوة ٣ ضرورية لأن يونيكود يعرّف «القوس الافتتاحي» دلالةً لا شكلاً؛
فعكس السلسلة يقلب دلالته.
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

    >>> order_combining_marks("\u064c\u0651")  # dammatan + shadda
    'ٌّ'
    >>> order_combining_marks("\u0651\u064e")  # already shadda + fatha
    'َّ'
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


def _mirror(ch: str) -> str:
    return MIRROR_PAIRS.get(ch, ch)


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
    if cfg.mirror_brackets:
        out = "".join(_mirror(c) for c in out)

    if cfg.protect_ltr_runs:
        # بعد عكس السطر، صارت المقاطع المحايدة معكوسةً بدورها؛ نعيدها.
        out = _LTR_RUN.sub(lambda m: m.group(0)[::-1], out)

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
