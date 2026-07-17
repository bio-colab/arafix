"""
الدرجة ١ — التطبيع: إعادة الحروف المطبوخة إلى أصولها.

لِمَ لا نكتفي بـ `unicodedata.normalize("NFKC", text)`؟

NFKC يحلّ المشكلة، نعم — ويحلّ معها عشرين مشكلةً لم تطلبها:
يقلب «①» إلى «1»، و«ﬁ» إلى «fi»، و«㎡» إلى «m2»، ويسوّي المسافات
غير الفاصلة. في نصٍّ أكاديمي فيه رموز رياضية أو مراجع لاتينية، هذا
تخريبٌ صامت.

فنحن نطبّع **نطاق الأشكال العربية وحده**، ونترك ما عداه كما هو.
التطبيع المُوجَّه أطول سطراً وأقصر أثراً، وهذا هو المطلوب.

الطبقات الثلاث في هذا الملف مستقلة، وكلٌّ منها مفتاح في `NormalizeConfig`:

  1. fold_presentation_forms — إلزامية عملياً
  2. strip_tatweel          — مستحبّة
  3. strip_diacritics       — اختيارية، ومطفأة افتراضاً (تفقد المعنى)
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .types import RepairResult, Stage
from .unicode_tables import (
    PF_TO_BASE,
    TATWEEL,
    ZWJ,
    ZWNJ,
    is_arabic_diacritic,
)

__all__ = ["NormalizeConfig", "fold_presentation_forms", "normalize_text"]


@dataclass
class NormalizeConfig:
    """مفاتيح التطبيع. كل مفتاح طبقة مستقلة يمكن إطفاؤها وحدها."""

    fold_presentation_forms: bool = True
    strip_tatweel: bool = True
    strip_zero_width: bool = True

    #: توحيد أشكال الألف (أ إ آ ا) — يعين البحث، ويفقد الدقة الإملائية.
    #: مطفأ افتراضاً: مهمّة المكتبة **استرجاع** النص لا تعديله.
    unify_alef: bool = False

    #: توحيد التاء المربوطة بالهاء والألف المقصورة بالياء — نفس التحفّظ.
    unify_taa_marbuta: bool = False
    unify_alef_maqsura: bool = False

    #: حذف التشكيل. لا تفعّله إلا إن كنت تعرف لماذا.
    strip_diacritics: bool = False

    #: تطبيع NFC ختامي لضمّ المحارف المركّبة.
    apply_nfc: bool = True


_ALEF_VARIANTS = "أإآٱ"
_ZERO_WIDTH = (ZWJ, ZWNJ, "\u200b", "\u200e", "\u200f", "\ufeff")


def fold_presentation_forms(text: str) -> str:
    """
    يعيد كل شكل رسومي إلى حرفه الأصلي، وحده دون أن يمسّ سواه.

    >>> fold_presentation_forms("\ufee3\ufeae\ufea3\ufe92\ufe8e")
    'مرحبا'

    ويفكّ لام-ألف إلى حرفين كما ينبغي:

    >>> fold_presentation_forms("\ufefb")
    'لا'
    """
    if not text:
        return text
    # `str.translate` بجدولٍ مبنيّ مسبقاً أسرع من الحلقة، والقيمة سلسلة
    # فتُفكّ لام-ألف إلى حرفين تلقائياً.
    return text.translate(_TRANSLATE_TABLE)


_TRANSLATE_TABLE = {ord(k): v for k, v in PF_TO_BASE.items()}


def normalize_text(text: str, config: NormalizeConfig | None = None) -> str:
    """يطبّق طبقات التطبيع المفعّلة بالترتيب. دالة نقيّة بلا آثار جانبية."""
    cfg = config or NormalizeConfig()
    out = text

    if cfg.fold_presentation_forms:
        out = fold_presentation_forms(out)

    if cfg.strip_tatweel:
        out = out.replace(TATWEEL, "")

    if cfg.strip_zero_width:
        for ch in _ZERO_WIDTH:
            out = out.replace(ch, "")

    if cfg.strip_diacritics:
        out = "".join(c for c in out if not is_arabic_diacritic(c))

    if cfg.unify_alef:
        for v in _ALEF_VARIANTS:
            out = out.replace(v, "ا")
    if cfg.unify_taa_marbuta:
        out = out.replace("ة", "ه")
    if cfg.unify_alef_maqsura:
        out = out.replace("ى", "ي")

    if cfg.apply_nfc:
        out = unicodedata.normalize("NFC", out)

    return out


def normalize_result(text: str, config: NormalizeConfig | None = None) -> RepairResult:
    """غلافٌ يُرجع `RepairResult` بدل نصٍّ عارٍ — للاستعمال داخل الأنبوب."""
    from .diagnose import diagnose

    out = normalize_text(text, config)
    return RepairResult(
        text=out,
        original=text,
        diagnosis=diagnose(text),
        stages_applied=[Stage.NORMALIZE],
        confidence=1.0 if out != text else 1.0,
        notes=["تطبيع موجَّه لنطاق الأشكال العربية وحده (لا NFKC عام)"],
    )
