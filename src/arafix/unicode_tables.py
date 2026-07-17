"""
جداول اليونيكود العربية — تُولَّد اشتقاقاً من `unicodedata` لا يدوياً.

الفلسفة هنا مقصودة: كل جدول في هذا الملف مبنيّ من قاعدة بيانات
اليونيكود المرفقة ببايثون، لا مكتوباً بخط اليد. الفائدة:

  * لا أخطاء مطبعية في ٦٠٠+ نقطة كود.
  * يتحدّث الجدول تلقائياً مع تحديث نسخة يونيكود في بايثون.
  * الاستثناءات وحدها مكتوبة يدوياً، وهي قليلة ومُبرَّرة سطراً سطراً.

المصطلحات:
  Presentation Form : الشكل الرسومي «المطبوخ» للحرف (U+FB50–FEFF).
  Base / Nominal    : الحرف الأصلي في الكتلة العربية (U+0600–06FF).
  Joining form      : ISOLATED / INITIAL / MEDIAL / FINAL.
"""

from __future__ import annotations

import sys
import unicodedata
from collections.abc import Iterable
from enum import Enum

__all__ = [
    "JoiningForm",
    "ARABIC_RANGES",
    "PRESENTATION_RANGES",
    "PUA_RANGES",
    "TATWEEL",
    "ZWJ",
    "ZWNJ",
    "PF_TO_BASE",
    "PF_JOINING_FORM",
    "SIMPLE_PF_TO_BASE",
    "LIGATURE_PF_TO_BASE",
    "ALEF_FORMS",
    "LAM",
    "FINAL_ONLY_LETTERS",
    "is_arabic",
    "is_presentation_form",
    "is_pua",
    "is_arabic_diacritic",
    "in_ranges",
    "unicode_version",
]


# ---------------------------------------------------------------------------
# نطاقات
# ---------------------------------------------------------------------------

#: الكتل العربية الأساسية (الحروف الاسمية المنطقية).
ARABIC_RANGES: tuple[tuple[int, int], ...] = (
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
)

#: كتل الأشكال الرسومية — هنا يقع أصل الداء.
PRESENTATION_RANGES: tuple[tuple[int, int], ...] = (
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
)

#: مناطق الاستعمال الخاص — ظهورها يعني CMap تالف أو خط بترميز خاص.
PUA_RANGES: tuple[tuple[int, int], ...] = (
    (0xE000, 0xF8FF),  # BMP Private Use Area
    (0xF0000, 0xFFFFD),  # Supplementary PUA-A
    (0x100000, 0x10FFFD),  # Supplementary PUA-B
)

TATWEEL = "\u0640"  # ـ  الكشيدة: زخرفة بصرية بلا معنى دلالي
ZWJ = "\u200d"
ZWNJ = "\u200c"

#: حروف لا تقع إلا في آخر الكلمة — أقوى إشارة على الترتيب المنطقي.
FINAL_ONLY_LETTERS = frozenset("ةى")

#: صور الألف كلها. تجاورُ اثنتين منها **مستحيلٌ إملائياً** في العربية،
#: وهذا الاستحالة بعينها هي ما يكشف انقلاب رباط لام-ألف لاحقاً.
ALEF_FORMS = frozenset("اأإآٱ")

LAM = "\u0644"


def in_ranges(cp: int, ranges: Iterable[tuple[int, int]]) -> bool:
    """هل نقطة الكود `cp` واقعة في أحد النطاقات المعطاة؟"""
    return any(lo <= cp <= hi for lo, hi in ranges)


def is_arabic(ch: str) -> bool:
    """حرف عربي اسمي (لا شكل رسومي)."""
    return in_ranges(ord(ch), ARABIC_RANGES)


def is_presentation_form(ch: str) -> bool:
    """شكل رسومي «مطبوخ» يحتاج تطبيعاً."""
    return in_ranges(ord(ch), PRESENTATION_RANGES)


def is_pua(ch: str) -> bool:
    """محرف في منطقة الاستعمال الخاص — لا معنى قياسياً له."""
    return in_ranges(ord(ch), PUA_RANGES)


def is_arabic_diacritic(ch: str) -> bool:
    """تشكيل أو علامة تُركَّب فوق/تحت الحرف (فئة Mn)."""
    return unicodedata.category(ch) == "Mn" and is_arabic(ch)


# ---------------------------------------------------------------------------
# بناء خريطة: شكل رسومي  →  (حرف أساسي، صيغة الوصل)
# ---------------------------------------------------------------------------

class JoiningForm(str, Enum):
    """صيغة وصل الحرف كما تصرّح بها قاعدة يونيكود."""

    ISOLATED = "isolated"
    INITIAL = "initial"
    MEDIAL = "medial"
    FINAL = "final"
    UNKNOWN = "unknown"


_TAG_TO_FORM = {
    "<isolated>": JoiningForm.ISOLATED,
    "<initial>": JoiningForm.INITIAL,
    "<medial>": JoiningForm.MEDIAL,
    "<final>": JoiningForm.FINAL,
}


def _build_pf_tables() -> tuple[dict[str, str], dict[str, JoiningForm]]:
    """
    يبني الجدولين من تفكيك التوافق (compatibility decomposition).

    كل شكل رسومي في يونيكود يحمل تفكيكاً على هيئة:
        U+FEDF  ARABIC LETTER LAM INITIAL FORM  →  <initial> 0644

    فنستخرج منه أمرين معاً في مرور واحد:
        1. الحرف/الحروف الأصلية  (لِمَ الجمع؟ لأن لام-ألف تُفكّ إلى حرفين)
        2. وسم الصيغة  (<initial> …)

    ملاحظة مقصودة: نحتفظ بالتفكيك سلسلةً لا حرفاً واحداً، وهذا ما
    يجعل U+FEF5 (لآ) يعود حرفين صحيحين بدل حرف واحد مشوّه.
    """
    to_base: dict[str, str] = {}
    to_form: dict[str, JoiningForm] = {}

    for lo, hi in PRESENTATION_RANGES:
        for cp in range(lo, hi + 1):
            ch = chr(cp)
            decomp = unicodedata.decomposition(ch)
            if not decomp:
                continue  # نقاط غير مُسنَدة، أو محارف تحكّم كـ U+FEFF
            parts = decomp.split()
            tag = parts[0] if parts[0].startswith("<") else None
            hex_parts = parts[1:] if tag else parts
            if not hex_parts:
                continue
            to_base[ch] = "".join(chr(int(h, 16)) for h in hex_parts)
            to_form[ch] = _TAG_TO_FORM.get(tag or "", JoiningForm.UNKNOWN)

    # --- استثناءات مقصودة -------------------------------------------------
    # U+FEFF هو ZERO WIDTH NO-BREAK SPACE (BOM) لا شكلٌ عربي؛ يقع في النطاق
    # صدفةً تاريخية. نحذفه صراحةً كي لا يُعامَل معاملة الحروف.
    to_base.pop("\ufeff", None)
    to_form.pop("\ufeff", None)

    # U+FE70..FE7F أشكال التشكيل المسبوقة بكشيدة (مثل «ـً»). تفكيكها يعطي
    # كشيدة + تشكيل. نُبقي التشكيل وحده ونطرح الكشيدة، فهي زخرفة.
    for ch, base in list(to_base.items()):
        if base.startswith(TATWEEL) and len(base) > 1:
            to_base[ch] = base[1:]

    return to_base, to_form


PF_TO_BASE, PF_JOINING_FORM = _build_pf_tables()


# ---------------------------------------------------------------------------
# القسمة الحاسمة: أشكالٌ مفردة  ضدّ  رباطات
# ---------------------------------------------------------------------------
#
# هذه القسمة ليست ترتيباً تنظيمياً، بل **شرط سلامة**.
#
# «ﻻ» في ملف الـ PDF جليفٌ واحد لا جليفان — والرباط إلزاميّ في العربية
# لا اختياريّ كـ «ﬁ» في اللاتينية. فإن فككناه إلى حرفين **قبل** إصلاح
# الاتجاه، عكسَ إصلاحُ الاتجاه الحرفين معه، فصارت «لا» → «ال»:
#
#     المجلات  →  ﺍﻟﻤﺠﻼﺕ  →  [تفكيك مبكر]  →  تلاجملا  →  [عكس]  →  المجالت
#                                                                    ‾‾‾‾‾‾‾
# فالقاعدة: **الرباط ذرّةٌ لا تُشقّ حتى يستقرّ الترتيب.**
#
# ولذلك نقسم الجدول قسمين بمعيارٍ مشتقّ لا مكتوبٍ بيد: طولُ التفكيك.
# ما فُكّ إلى حرفٍ واحد شكلٌ مفرد يُطبَّع في أيّ وقت، وما فُكّ إلى أكثر
# رباطٌ يُؤجَّل إلى ما بعد الدرجة ٢.

SIMPLE_PF_TO_BASE = {k: v for k, v in PF_TO_BASE.items() if len(v) == 1}
LIGATURE_PF_TO_BASE = {k: v for k, v in PF_TO_BASE.items() if len(v) > 1}


def unicode_version() -> str:
    """نسخة قاعدة بيانات يونيكود التي بُنيت منها الجداول (للتقارير)."""
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    return f"{unicodedata.unidata_version} (python {py})"
