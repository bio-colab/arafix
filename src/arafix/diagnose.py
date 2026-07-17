"""
الدرجة صفر — التشخيص. لا تعالج قبل أن تعرف.

كل كاشف هنا **حتميّ**: لا تخمين إحصائي ولا نموذج مدرَّب. يقرأ النص
ويعدّ شواهد قابلة للتحقق يدوياً. إن قالت المكتبة «معكوس» فبوسعك أن
تفتح التقرير وترى بأيّ شاهدٍ قالت.

الكواشف الأربعة:

  1. detect_mojibake       — اختبار جبري: أيعود النص إن أعدنا ترميزه؟
  2. detect_presentation_forms — عدّ نطاقيّ بحت.
  3. detect_pua            — عدّ نطاقيّ بحت.
  4. detect_visual_order   — ثلاثة شواهد لغوية مستقلة، مُصوَّتٌ عليها.

الكاشف الرابع وحده احتماليّ، ولذلك يُرجع درجةً في [-1, 1] لا حكماً
ثنائياً، ولا يُعتمد إلا فوق عتبة مصرَّح بها في `DEFAULT_THRESHOLDS`.
"""

from __future__ import annotations

import re

from .types import Defect, Diagnosis, Evidence
from .unicode_tables import (
    FINAL_ONLY_LETTERS,
    PF_JOINING_FORM,
    TATWEEL,
    JoiningForm,
    is_arabic,
    is_presentation_form,
    is_pua,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "detect_mojibake",
    "detect_presentation_forms",
    "detect_pua",
    "detect_visual_order",
    "diagnose",
]


#: عتبات القرار — مجموعة في مكان واحد عمداً كي تُضبَط دون لمس المنطق.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "presentation_forms": 0.02,  # ٢٪ من الحروف العربية تكفي — لا تظهر صدفةً
    "pua": 0.01,
    "visual_order": 0.30,        # درجة التصويت المركّبة
    "tatweel": 0.005,
    "min_arabic_chars": 8,       # أقلّ من ذلك: العيّنة أصغر من أن يُحكم عليها
}

_ARABIC_TOKEN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+")

#: توقيع الموجيبيك: بايتات UTF-8 عربية (0xD8/0xD9) مقروءة كـ Latin-1.
_MOJIBAKE_SIGNATURE = re.compile(r"[ØÙÚÛ][\u0080-\u00BF\u2000-\u206F]")


# ---------------------------------------------------------------------------
# ١) الموجيبيك — اختبار جبريّ لا إحصائي
# ---------------------------------------------------------------------------

def detect_mojibake(text: str) -> tuple[bool, str | None, Evidence]:
    """
    يكشف نصاً بايتاته UTF-8 لكنه فُكّ بـ Latin-1/CP1252 (Ø§Ù„Ù…...).

    الاختبار قاطع لا تخميني: إن أمكن إعادة الترميز `latin-1` ثم فكّه
    `utf-8` بنجاح، **وكان** الناتج عربياً أكثر من الأصل، فالنص موجيبيك.
    شرط «أكثر عربية» ضروريّ وإلا لَعُدَّ كل نص لاتيني سليم مُعطَلاً.

    يُرجع: (أموجيبيك؟، النص المُصحَّح أو None، الشاهد)

    ملاحظة تشخيصية مهمة: هذه العلّة **ليست** علّة PDF أصلاً، بل علّة
    أنبوب المعالجة عندك. خلطُها بـ CMap التالف خطأ شائع.
    """
    if not _MOJIBAKE_SIGNATURE.search(text):
        return False, None, Evidence("mojibake", 0.0, "لا توقيع لبايتات UTF-8 مفكوكة خطأً")

    try:
        recovered = text.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            recovered = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
        except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
            return False, None, Evidence("mojibake", 0.0, "التوقيع موجود لكن إعادة الترميز فشلت")

    before = sum(1 for c in text if is_arabic(c))
    after = sum(1 for c in recovered if is_arabic(c))
    if after <= before:
        return False, None, Evidence("mojibake", 0.0, "إعادة الترميز لم تزد النص عربية")

    ev = Evidence("mojibake", 1.0, f"إعادة الترميز رفعت الحروف العربية من {before} إلى {after}")
    return True, recovered, ev


# ---------------------------------------------------------------------------
# ٢) و ٣) الأشكال الرسومية و PUA — عدّ نطاقيّ
# ---------------------------------------------------------------------------

def detect_presentation_forms(text: str) -> tuple[float, Evidence]:
    """نسبة الحروف المطبوخة (U+FB50–FEFF) إلى مجموع الحروف العربية."""
    pf = sum(1 for c in text if is_presentation_form(c))
    total = sum(1 for c in text if is_arabic(c) or is_presentation_form(c))
    ratio = pf / total if total else 0.0
    return ratio, Evidence(
        "presentation_forms", ratio, f"{pf} شكلاً رسومياً من {total} حرفاً عربياً"
    )


def detect_pua(text: str) -> tuple[float, Evidence]:
    """
    نسبة محارف منطقة الاستعمال الخاص.

    ظهورها بكثافة = ToUnicode CMap تالف أو مفقود: الخط يرسم صحيحاً
    والملف يخزّن أرقاماً بلا معنى قياسي. هذه هي الحالة الوحيدة التي
    لا يُنجيك منها إلا الدرجة ٣ (إعادة بناء الخريطة من الخط نفسه).
    """
    pua = sum(1 for c in text if is_pua(c))
    total = len(text) or 1
    ratio = pua / total
    return ratio, Evidence("pua", ratio, f"{pua} محرفاً في منطقة الاستعمال الخاص من {total}")


def detect_tatweel(text: str) -> tuple[float, Evidence]:
    """نسبة الكشيدة — زخرفة بصرية تفسد المطابقة والبحث."""
    n = text.count(TATWEEL)
    total = len(text) or 1
    return n / total, Evidence("tatweel", n / total, f"{n} كشيدة")


# ---------------------------------------------------------------------------
# ٤) الاتجاه — ثلاثة شواهد مستقلة، بتصويت مرجَّح
# ---------------------------------------------------------------------------

def _signal_final_only_letters(tokens: list[str]) -> tuple[float, str] | None:
    """
    الشاهد الأقوى: التاء المربوطة والألف المقصورة **لا تقعان إلا آخر الكلمة**.

    قاعدة إملائية صلبة لا استثناء لها في العربية. فإن وجدناهما أوّل
    الكلمات، فالنص مخزَّن معكوساً. هذا شاهد قاطع تقريباً.
    """
    head = tail = 0
    for t in tokens:
        if len(t) < 2:
            continue
        if t[0] in FINAL_ONLY_LETTERS:
            head += 1
        if t[-1] in FINAL_ONLY_LETTERS:
            tail += 1
    if head + tail == 0:
        return None
    score = (head - tail) / (head + tail)
    return score, f"ة/ى في أول {head} كلمة مقابل آخر {tail} كلمة"


def _signal_joining_forms(text: str) -> tuple[float, str] | None:
    """
    الشاهد الثاني: إن كان النص أشكالاً رسومية، فالشكل نفسه يفضح الترتيب.

    الشكل FINAL لا يقع إلا آخر الكلمة، وINITIAL لا يقع إلا أوّلها —
    هكذا صرّح يونيكود. فمواقعها في النص المخزَّن تكشف اتجاهه دون
    الحاجة إلى معجم ولا إلى معرفةٍ لغوية.
    """
    correct = wrong = 0
    for token in _ARABIC_TOKEN.findall(text):
        forms = [PF_JOINING_FORM.get(c) for c in token]
        forms = [f for f in forms if f and f != JoiningForm.UNKNOWN]
        if len(forms) < 2:
            continue
        first, last = forms[0], forms[-1]
        if first is JoiningForm.INITIAL:
            correct += 1
        elif first is JoiningForm.FINAL:
            wrong += 1
        if last is JoiningForm.FINAL:
            correct += 1
        elif last is JoiningForm.INITIAL:
            wrong += 1
    if correct + wrong == 0:
        return None
    score = (wrong - correct) / (correct + wrong)
    return score, f"صيغ الوصل: {wrong} في غير موضعها مقابل {correct} في موضعها"


def _signal_definite_article(tokens: list[str]) -> tuple[float, str] | None:
    """
    الشاهد الثالث: «ال» التعريف أشيع بادئة في العربية. معكوسةً تصير «لا» لاحقة.

    أضعف الشواهد الثلاثة — فـ«لا» النافية موجودة، و«ال» قد تكون أصلية.
    ولذلك وزنه أخفّ، ولا يُعتمد وحده أبداً.
    """
    pre = sum(1 for t in tokens if len(t) > 3 and t.startswith("ال"))
    post = sum(1 for t in tokens if len(t) > 3 and t.endswith("لا"))
    if pre + post == 0:
        return None
    score = (post - pre) / (pre + post)
    return score, f"«ال» بادئةً في {pre} كلمة، «لا» لاحقةً في {post}"


#: أوزان التصويت — مرتّبة بحسب صلابة القاعدة اللغوية خلف كل شاهد.
_ORDER_WEIGHTS = {
    "final_only_letters": 0.50,
    "joining_forms": 0.35,
    "definite_article": 0.15,
}


def detect_visual_order(text: str) -> tuple[float, list[Evidence]]:
    """
    يُرجع درجة في [-1, 1]:  +1 معكوس يقيناً، -1 منطقيّ يقيناً، 0 لا دليل.

    الدرجة مرجَّحة بأوزان الشواهد المتوفرة **فقط**، فغياب شاهدٍ لا
    يُحسب صفراً (وهو خطأ شائع يمُيّع النتيجة)، بل يُعاد التطبيع على
    مجموع أوزان الحاضرين.
    """
    tokens = _ARABIC_TOKEN.findall(text)
    signals = {
        "final_only_letters": _signal_final_only_letters(tokens),
        "joining_forms": _signal_joining_forms(text),
        "definite_article": _signal_definite_article(tokens),
    }

    evidence: list[Evidence] = []
    weighted = 0.0
    total_weight = 0.0
    for name, result in signals.items():
        if result is None:
            evidence.append(Evidence(name, 0.0, "لا شاهد في هذه العيّنة"))
            continue
        score, detail = result
        w = _ORDER_WEIGHTS[name]
        weighted += score * w
        total_weight += w
        evidence.append(Evidence(name, score, detail))

    final = weighted / total_weight if total_weight else 0.0
    return final, evidence


# ---------------------------------------------------------------------------
# الواجهة
# ---------------------------------------------------------------------------

def diagnose(text: str, thresholds: dict[str, float] | None = None) -> Diagnosis:
    """
    يشخّص نصاً مستخرَجاً ويُرجع `Diagnosis` كاملاً بشواهده.

    >>> d = diagnose("ﺎﺒﺣﺮﻣ")
    >>> Defect.PRESENTATION_FORMS in d.defects
    True
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    dg = Diagnosis(char_count=len(text))

    arabic_chars = sum(1 for c in text if is_arabic(c) or is_presentation_form(c))
    dg.arabic_ratio = arabic_chars / len(text) if text else 0.0

    if not text.strip():
        dg.defects.append(Defect.NO_TEXT_LAYER)
        dg.confidence = 1.0
        dg.evidence.append(Evidence("empty", 1.0, "لا طبقة نصية — مرشّح للدرجة ٤ (OCR)"))
        return dg

    # الموجيبيك أولاً: إن وُجد فكل قياس بعده على نصٍّ مشوّه لا معنى له.
    is_moji, _, ev = detect_mojibake(text)
    dg.evidence.append(ev)
    if is_moji:
        dg.defects.append(Defect.MOJIBAKE)
        dg.confidence = 1.0
        dg.metrics["mojibake"] = True
        return dg

    pf_ratio, ev = detect_presentation_forms(text)
    dg.evidence.append(ev)
    dg.metrics["pf_ratio"] = pf_ratio
    if pf_ratio > th["presentation_forms"]:
        dg.defects.append(Defect.PRESENTATION_FORMS)

    pua_ratio, ev = detect_pua(text)
    dg.evidence.append(ev)
    dg.metrics["pua_ratio"] = pua_ratio
    if pua_ratio > th["pua"]:
        dg.defects.append(Defect.BROKEN_CMAP)

    tw_ratio, ev = detect_tatweel(text)
    dg.evidence.append(ev)
    if tw_ratio > th["tatweel"]:
        dg.defects.append(Defect.TATWEEL_NOISE)

    if arabic_chars >= th["min_arabic_chars"]:
        order_score, order_ev = detect_visual_order(text)
        dg.evidence.extend(order_ev)
        dg.metrics["order_score"] = order_score
        if order_score > th["visual_order"]:
            dg.defects.append(Defect.VISUAL_ORDER)
    else:
        dg.evidence.append(
            Evidence("visual_order", 0.0, "العيّنة العربية أصغر من عتبة الحكم")
        )
        dg.metrics["order_score"] = 0.0

    if not dg.defects:
        dg.defects.append(Defect.NONE)

    dg.confidence = _confidence(dg)
    return dg


def _confidence(dg: Diagnosis) -> float:
    """
    ثقة التشخيص = قوة أوضح شاهدٍ حاضر، مضروبةً في كفاية العيّنة.

    مقصود ألّا تبلغ ١٫٠ إلا بعيّنةٍ وافية وشاهدٍ صريح.
    """
    if Defect.NONE in dg.defects:
        base = 0.6
    else:
        base = max((abs(e.value) for e in dg.evidence), default=0.0)
    sample = min(1.0, dg.char_count / 200.0)
    return round(min(1.0, 0.5 * base + 0.5 * (base * sample) + 0.25 * sample), 3)
