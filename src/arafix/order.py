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

#: مقاطع محايدة الاتجاه: تُقرأ يساراً فيميناً في الحالين، فلا تُعكس.
#: تشمل الأرقام العربية-الهندية (٠-٩) لأنها LTR أيضاً في يونيكود.
_LTR_RUN = re.compile(
    r"[0-9\u0660-\u0669\u06F0-\u06F9A-Za-z\u00C0-\u024F]"
    r"[0-9\u0660-\u0669\u06F0-\u06F9A-Za-z\u00C0-\u024F.,:/\\\-+%°'\u2019]*"
    r"[0-9\u0660-\u0669\u06F0-\u06F9A-Za-z\u00C0-\u024F]"
)


def grapheme_clusters(text: str) -> list[str]:
    """
    يقسم النصّ عناقيدَ: كلُّ حرفٍ أساس ومعه ما يليه من علاماتٍ لاصقة.

    **وحدةُ العكس هي العنقود لا المحرف** — وهذا ليس تدقيقاً نظرياً.
    علامات التشكيل (فئة Mn) عرضُها صفر وتشترك في موضع حرفها، فعكسُ
    نقاط الكود يفصل العلامة عن حرفها ويُلصقها بجارها:

        أولاً  →  [عكسٌ على المحارف]  →  أوًلا

    ونتّبع قاعدة يونيكود: العلامة تلي أساسها. فالعنقود = أساسٌ + ما بعده
    من علامات، ويُعكس ترتيب العناقيد ويبقى داخلُ كلٍّ منها كما هو.

    >>> grapheme_clusters("\u062b\u0627\u0646\u064a\u0627\u064b.")
    ['ث', 'ا', 'ن', 'ي', 'اً', '.']
    """
    out: list[str] = []
    for ch in text:
        if out and unicodedata.category(ch) == "Mn":
            out[-1] += ch
        else:
            out.append(ch)
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
