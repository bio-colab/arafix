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
    is_presentation_form,
)

__all__ = [
    "NormalizeConfig",
    "fold_presentation_forms",
    "fold_presentation_punctuation",
    "fold_simple_forms",
    "fold_pdf_homoglyphs",
    "expand_deferred_forms",
    "expand_ligatures",
    "strip_tatweel_among_presentation_forms",
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

    #: طيّ محارف PDF الهجينة الشائعة في خطوط عربية (ی/ھ → ي/ه).
    #: مفعّل افتراضاً: استرجاع عربي قياسي من ToUnicode رديء؛ أطفئه للنصّ الفارسي.
    fold_pdf_homoglyphs: bool = True

    #: حذف التشكيل. لا تفعّله إلا إن كنت تعرف لماذا.
    strip_diacritics: bool = False

    #: تطبيع المؤجَّل (ﻻ → لا، وU+FE79 → ُ). صحيحٌ لنصٍّ مستقرّ الترتيب.
    #: يطفئه الأنبوب **مؤقتاً** في تمريرته الأولى ليُبقي الرباط ذرّةً
    #: حتى تفرغ الدرجة ٢، ثم يشعله في تمريرةٍ ثانية. انظر pipeline.py.
    expand_ligatures: bool = True

    #: قبل طيّ الأشكال الرسومية: احذف الكشيدة الملاصقة لمحارف PF.
    #: يمنع تشويه سلاسل مثل ``ـﻪـﻠـﻟا`` → «الله» بدل «لله».
    #: لا يمسّ كشيدةً وسط حروف اسمية عادية (تبقى لـ ``strip_tatweel``).
    strip_tatweel_in_pf_runs: bool = True

    #: تطبيع NFC ختامي لضمّ المحارف المركّبة.
    apply_nfc: bool = True


_ALEF_VARIANTS = "أإآٱ"


def _build_presentation_punctuation_table() -> dict[int, str]:
    """Build a narrow NFKC map for punctuation presentation forms only."""
    table: dict[int, str] = {}
    for codepoint in range(0xFE10, 0xFE6C):
        char = chr(codepoint)
        if not unicodedata.category(char).startswith("P"):
            continue
        normalized = unicodedata.normalize("NFKC", char)
        if normalized != char:
            table[codepoint] = normalized
    return table


_PRESENTATION_PUNCTUATION_TABLE = _build_presentation_punctuation_table()
_ZERO_WIDTH = (ZWJ, ZWNJ, "\u200b", "\u200e", "\u200f", "\ufeff")

# PDF fonts often map Arabic yeh/heh to Farsi / Doachashmee codepoints.
_PDF_HOMOGLYPH_TABLE = str.maketrans(
    {
        "\u06cc": "\u064a",  # ARABIC LETTER FARSI YEH → YEH
        "\u06cd": "\u064a",  # YEH WITH TAIL → YEH
        "\u06be": "\u0647",  # HEH DOACHASHMEE → HEH
        "\u06c1": "\u0647",  # HEH GOAL → HEH
        "\u06c2": "\u0647",  # HEH GOAL WITH HAMZA → HEH
        "\u06a9": "\u0643",  # KEHEH → KAF
        "\u06c3": "\u0629",  # TEH MARBUTA GOAL → TEH MARBUTA
    }
)


def fold_presentation_punctuation(text: str) -> str:
    """Fold only Unicode punctuation presentation forms to base marks."""
    return text.translate(_PRESENTATION_PUNCTUATION_TABLE) if text else text


def fold_pdf_homoglyphs(text: str) -> str:
    """
    Fold PDF/font lookalikes to standard Arabic letters.

    Word and many CJK-oriented fonts encode Arabic yeh/heh as Farsi Yeh
    (U+06CC) and Heh Doachashmee (U+06BE). Readers see the right shapes;
    string equality, search, and CER do not.

    >>> fold_pdf_homoglyphs("ایران")
    'ايران'
    >>> fold_pdf_homoglyphs("ھل")
    'هل'
    """
    return text.translate(_PDF_HOMOGLYPH_TABLE) if text else text


_SIMPLE_TABLE = {ord(k): v for k, v in SIMPLE_PF_TO_BASE.items()}
_DEFERRED_TABLE = {ord(k): v for k, v in DEFERRED_PF_TO_BASE.items()}
_ALL_TABLE = {**_SIMPLE_TABLE, **_DEFERRED_TABLE}


def strip_tatweel_among_presentation_forms(text: str) -> str:
    """
    تحذف الكشيدة (U+0640) إن لاصقت شكلاً رسومياً (Presentation Form).

    الكشيدة وسط سلسلة PF تكسر تجاور الجليفات قبل الطيّ، فتنتج أشكالاً
    اسمية خاطئة بعد العكس (مثل «الحمد الله» بدل «الحمد لله»).

    >>> strip_tatweel_among_presentation_forms("\u0640\ufeea\u0640\ufee0")
    '\ufeea\ufee0'

    كشيدة بين حروف اسمية عادية تُترك هنا (تُعالَج لاحقاً بـ strip_tatweel)::

        "مـر" تبقى "مـر"
    """
    if not text or TATWEEL not in text:
        return text
    out: list[str] = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch == TATWEEL:
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < n else ""
            if (prev and is_presentation_form(prev)) or (
                nxt and is_presentation_form(nxt)
            ):
                continue
        out.append(ch)
    return "".join(out)


def fold_simple_forms(text: str, *, strip_pf_tatweel: bool = True) -> str:
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
    if not text:
        return text
    if strip_pf_tatweel:
        text = strip_tatweel_among_presentation_forms(text)
    return text.translate(_SIMPLE_TABLE)


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


def fold_presentation_forms(text: str, *, strip_pf_tatweel: bool = True) -> str:
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
    if not text:
        return text
    if strip_pf_tatweel:
        text = strip_tatweel_among_presentation_forms(text)
    return text.translate(_ALL_TABLE)


def normalize_text(text: str, config: NormalizeConfig | None = None) -> str:
    """يطبّق طبقات التطبيع المفعّلة بالترتيب. دالة نقيّة بلا آثار جانبية."""
    cfg = config or NormalizeConfig()
    out = text

    if cfg.fold_presentation_forms:
        out = fold_simple_forms(out, strip_pf_tatweel=cfg.strip_tatweel_in_pf_runs)
        out = fold_presentation_punctuation(out)
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

    if cfg.fold_pdf_homoglyphs:
        out = fold_pdf_homoglyphs(out)

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
