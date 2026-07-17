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
    DEFERRED_PF_TO_BASE,
    SIMPLE_PF_TO_BASE,
    TATWEEL,
    ZWJ,
    ZWNJ,
    is_arabic_diacritic,
)

__all__ = [
    "NormalizeConfig",
    "fold_presentation_forms",
    "fold_simple_forms",
    "expand_deferred_forms",
    "expand_ligatures",
    "normalize_text",
]


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

    #: تطبيع المؤجَّل (ﻻ → لا، وU+FE79 → ُ). صحيحٌ لنصٍّ مستقرّ الترتيب.
    #: يطفئه الأنبوب **مؤقتاً** في تمريرته الأولى ليُبقي الرباط ذرّةً
    #: حتى تفرغ الدرجة ٢، ثم يشعله في تمريرةٍ ثانية. انظر pipeline.py.
    expand_ligatures: bool = True

    #: تطبيع NFC ختامي لضمّ المحارف المركّبة.
    apply_nfc: bool = True


_ALEF_VARIANTS = "أإآٱ"
_ZERO_WIDTH = (ZWJ, ZWNJ, "\u200b", "\u200e", "\u200f", "\ufeff")


_SIMPLE_TABLE = {ord(k): v for k, v in SIMPLE_PF_TO_BASE.items()}
_DEFERRED_TABLE = {ord(k): v for k, v in DEFERRED_PF_TO_BASE.items()}
_ALL_TABLE = {**_SIMPLE_TABLE, **_DEFERRED_TABLE}


def fold_simple_forms(text: str) -> str:
    """
    يطبّع الأشكال **المفردة** وحدها، ويترك الرباطات ذرّاتٍ لا تُشقّ.

    هذه هي التمريرة التي تسبق إصلاح الاتجاه. تكفي لفتح عين الدرجة ٢
    (فالتاء المربوطة شكلٌ مفرد يظهر بعدها)، ولا تسلّمها سكيناً.

    >>> fold_simple_forms("\ufee3\ufeae\ufea3\ufe92\ufe8e")
    'مرحبا'

    والرباط يبقى كما هو — وهذا هو المقصود بالضبط:

    >>> fold_simple_forms("\ufefb") == "\ufefb"
    True
    """
    return text.translate(_SIMPLE_TABLE) if text else text


def expand_deferred_forms(text: str) -> str:
    """
    يطبّع ما أُجِّل: الرباطات وأشكال التشكيل الفاصلة.

    **لا تنادها قبل استقرار الترتيب** — فهذه بعينها هي الأشكال التي
    يغيّر تطبيعُها بنيةَ العنقود، فيقلب العكسُ ما فكّكناه.

    >>> expand_deferred_forms("\ufefb")
    'لا'
    >>> expand_deferred_forms("\ufef5")
    'لآ'
    >>> expand_deferred_forms("\ufe79")   # ضمّةٌ فاصلة ← علامةٌ لاصقة
    'ُ'
    """
    return text.translate(_DEFERRED_TABLE) if text else text


#: اسمٌ قديم أُبقي للتوافق. المظلّة أوسع من الرباطات، فالاسم الأدقّ أعلاه.
expand_ligatures = expand_deferred_forms


def fold_presentation_forms(text: str) -> str:
    """
    يطبّع كل الأشكال — المفردة والرباطات معاً.

    آمنةٌ للنصّ المستقرّ الترتيب فقط. إن كان نصّك بصريّ الترتيب، فهذه
    الدالة **تُعطِبه**: تفكّ «ﻻ» إلى «لا» ثم يعكسها العكسُ إلى «ال».
    استعمل `repair_text()` وهي تتولّى التوقيت عنك.

    >>> fold_presentation_forms("\ufee3\ufeae\ufea3\ufe92\ufe8e")
    'مرحبا'
    >>> fold_presentation_forms("\ufefb")
    'لا'
    """
    return text.translate(_ALL_TABLE) if text else text


def normalize_text(text: str, config: NormalizeConfig | None = None) -> str:
    """يطبّق طبقات التطبيع المفعّلة بالترتيب. دالة نقيّة بلا آثار جانبية."""
    cfg = config or NormalizeConfig()
    out = text

    if cfg.fold_presentation_forms:
        out = fold_simple_forms(out)
        if cfg.expand_ligatures:
            out = expand_deferred_forms(out)

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
