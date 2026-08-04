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
import unicodedata

from .lamalef import detect_lam_alef_transposition
from .types import DETERMINISTIC_DEFECTS, Defect, Diagnosis, Evidence
from .unicode_tables import (
    FINAL_ONLY_LETTERS,
    PF_JOINING_FORM,
    PF_TO_BASE,
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

#: توقيع الموجيبيك: بايتات UTF-8 عربية (0xD8/0xD9) مقروءة كـ Latin-1/CP1252.
#: النطاق \u2000–\u206F يلتقط «…» و«„» حين فُكّت بايتات الاستمرار عبر CP1252.
_MOJIBAKE_SIGNATURE = re.compile(r"[ØÙÚÛ][\u0080-\u00BF\u2000-\u206F]")

#: رؤوس UTF-8 العربية الشائعة كما تظهر بعد فكّ خاطئ.
_MOJIBAKE_LEAD = frozenset("ØÙÚÛ")

#: أقصى طول لنافذة الاسترجاع الجزئي (محارف، لا بايتات).
_MOJIBAKE_WINDOW_MAX = 48

#: ترميزات موروثة عربية — بايتات فُكّت كـ Latin-1/CP1252.
_LEGACY_ARABIC_ENCODINGS = ("cp1256", "iso8859_6", "iso8859-6")


# ---------------------------------------------------------------------------
# ١) الموجيبيك — كامل أو هجين (نوافذ)
# ---------------------------------------------------------------------------

def _count_arabic(s: str) -> int:
    return sum(1 for c in s if is_arabic(c))


def _to_mojibake_bytes(span: str) -> bytes | None:
    """
    يحوّل مقطع الموجيبيك إلى بايتات كما خُزِّنت خطأً.

    نفضّل CP1252 لأن بايتات الاستمرار (0x80–0x9F) تُفكّ غالباً إلى
    علامات طباعية (… „) لا إلى محارف Latin-1 التحكمية.
    """
    for enc in ("cp1252", "latin-1"):
        try:
            return span.encode(enc)
        except (UnicodeEncodeError, LookupError):
            continue
    return None


def _try_utf8_from_misread(span: str) -> str | None:
    """latin-1/cp1252 → UTF-8. يُرجع None إن فشل التسلسل."""
    raw = _to_mojibake_bytes(span)
    if raw is None:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _legacy_recovery_plausible(original: str, recovered: str) -> bool:
    """
    يحمي اللاتينية (café, résumé) من مسار ISO-8859-6 الزائف.

    يشترط ربحاً عربياً واضحاً وأن تكون أغلب المحارف غير البيضاء عربية.
    """
    before = _count_arabic(original)
    after = _count_arabic(recovered)
    if after < before + 3:
        return False
    non_space = [c for c in recovered if not c.isspace()]
    if len(non_space) < 3:
        return False
    ar_ns = sum(1 for c in non_space if is_arabic(c))
    return (ar_ns / len(non_space)) >= 0.5


def _try_legacy_arabic_from_misread(span: str) -> str | None:
    """
    بايتات CP1256 / ISO-8859-6 فُكّت كـ Latin-1/CP1252.

    مسار إضافي للنصوص القديمة (مواقع، قواعد، بريد) بجانب موجيبيك UTF-8.
    يُفضَّل CP1256؛ ISO-8859-6 أخطر على اللاتينية فيُقيَّد بعتبة صارمة.
    """
    raw = _to_mojibake_bytes(span)
    if raw is None or not raw:
        return None
    before = _count_arabic(span)
    best: str | None = None
    best_gain = 0
    for enc in _LEGACY_ARABIC_ENCODINGS:
        try:
            rec = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if not _legacy_recovery_plausible(span, rec):
            continue
        gain = _count_arabic(rec) - before
        if gain > best_gain:
            best_gain = gain
            best = rec
    return best


def _recover_span(span: str) -> str | None:
    """
    أفضل استرجاع لمقطع واحد.

    - إن وُجدت رؤوس موجيبيك UTF-8 (ØÙÚÛ) نُصرّ على مسار UTF-8 فقط —
      مسار CP1256 على نفس البايتات يُنتج عربية زائفة (``ط§ظ„…``).
    - الترميز الموروث يُجرَّب فقط لمقاطع بلا هذا التوقيع.
    """
    utf = _try_utf8_from_misread(span)
    if utf is not None and _count_arabic(utf) > _count_arabic(span):
        return utf
    if any(c in _MOJIBAKE_LEAD for c in span):
        return None
    return _try_legacy_arabic_from_misread(span)


def _is_mojibake_start(text: str, i: int) -> bool:
    if i >= len(text):
        return False
    ch = text[i]
    if ch in _MOJIBAKE_LEAD:
        return True
    # بداية توقيع ثنائي عند i
    return bool(_MOJIBAKE_SIGNATURE.match(text, i))


def _windowed_mojibake_recover(text: str) -> str | None:
    """
    يسترجع موجيبيكاً **هجييناً**: مقاطع معطوبة وسط ASCII/عربي سليم.

    من كل موضع مرشّح يأخذ أطول نافذة ناجحة ذات ربح عربي، ويتجاوز
    رؤوس UTF-8 اليتيمة (``Ù`` قبل ``Customer`` في FLAW_04).
    """
    n = len(text)
    out: list[str] = []
    i = 0
    changed = False

    while i < n:
        if not _is_mojibake_start(text, i):
            out.append(text[i])
            i += 1
            continue

        best_rec: str | None = None
        best_end = i
        best_gain = 0
        max_end = min(n, i + _MOJIBAKE_WINDOW_MAX)
        for end in range(i + 1, max_end + 1):
            # لا تمدّ النافذة داخل لاتيني طويل بلا فائدة بعد فشل متتالٍ.
            span = text[i:end]
            rec = _recover_span(span)
            if rec is None:
                continue
            gain = _count_arabic(rec) - _count_arabic(span)
            if gain > best_gain or (gain == best_gain and end > best_end and gain > 0):
                best_gain = gain
                best_rec = rec
                best_end = end

        if best_rec is not None and best_gain > 0:
            out.append(best_rec)
            i = best_end
            changed = True
            continue

        # رأس UTF-8 يتيم (لا استمرار صالح) — يُحذف لا يُترك يشوّه اللاتيني.
        if text[i] in _MOJIBAKE_LEAD:
            nxt = text[i + 1] if i + 1 < n else ""
            if not nxt or ord(nxt) < 0x80 or ("A" <= nxt <= "Z") or ("a" <= nxt <= "z"):
                i += 1
                changed = True
                continue

        out.append(text[i])
        i += 1

    if not changed:
        return None
    return "".join(out)


def detect_mojibake(text: str) -> tuple[bool, str | None, Evidence]:
    """
    يكشف نصاً بايتاته UTF-8 (أو CP1256/ISO-8859-6) فُكّت بـ Latin-1/CP1252.

    المسارات بالترتيب:

    1. **كامل السطر** — encode→decode صارم (الحالة الكلاسيكية ``Ø§Ù„…``).
    2. **نوافذ هجينة** — استرجاع جزئي حين يختلط الموجيبيك بـ ASCII أو
       بعربي سليم، أو حين يقطع رأس UTF-8 يتيم التسلسل
       (``Ø§Ù„Ù…ÙCustomer`` → ``المCustomer``).
    3. **ترميز موروث** — CP1256 / ISO-8859-6 داخل النافذة نفسها.

    شرط القبول: زيادة صافية في الحروف العربية. لا نلمّس لاتينياً سليماً.

    >>> detect_mojibake("Ø§Ù„Ø³Ù„Ø§Ù…")[1]
    'السلام'
    >>> detect_mojibake("Ø§Ù„Ù…ÙCustomer Report")[1]
    'المCustomer Report'

    ملاحظة: هذه العلّة **ليست** علّة PDF، بل علّة أنبوب الترميز عندك.
    """
    if not text:
        return False, None, Evidence("mojibake", 0.0, "نص فارغ")

    has_sig = bool(_MOJIBAKE_SIGNATURE.search(text))
    has_high_latin = any(0x80 <= ord(c) <= 0xFF for c in text)
    # ØÙÚÛ قد تظهر في CP1256 المُساء فهمه أيضاً — لا نجعلها مانعاً للمسار الموروث.
    has_utf8_mojibake_hint = has_sig or bool(
        _MOJIBAKE_SIGNATURE.search(text)
    ) or (
        any(c in _MOJIBAKE_LEAD for c in text)
        and any(0x80 <= ord(c) <= 0xFF or 0x2000 <= ord(c) <= 0x206F for c in text)
    )
    if not has_sig and not has_high_latin and not any(c in _MOJIBAKE_LEAD for c in text):
        return False, None, Evidence("mojibake", 0.0, "لا توقيع لبايتات UTF-8 مفكوكة خطأً")

    before = _count_arabic(text)
    mode = ""
    recovered: str | None = None

    # --- 1) كامل: UTF-8 قُرئ Latin-1/CP1252 ---
    utf = _try_utf8_from_misread(text)
    if utf is not None and _count_arabic(utf) > before:
        recovered = utf
        mode = "full-utf8"

    # --- 2) كامل: CP1256 / ISO-8859-6 قُرئ Latin-1 ---
    if recovered is None:
        leg = _try_legacy_arabic_from_misread(text)
        if leg is not None:
            recovered = leg
            mode = "full-legacy"

    # --- 3) نوافذ هجينة (موجيبيك UTF-8 وسط ASCII/عربي سليم) ---
    if recovered is None and (has_sig or any(c in _MOJIBAKE_LEAD for c in text)):
        hybrid = _windowed_mojibake_recover(text)
        if hybrid is not None and hybrid != text and _count_arabic(hybrid) > before:
            recovered = hybrid
            mode = "hybrid-window"

    if recovered is None or recovered == text:
        if has_sig or has_utf8_mojibake_hint:
            detail = "التوقيع موجود لكن الاسترجاع الكامل والجزئي فشلا"
        elif has_high_latin:
            detail = "بايتات عالية بلا استرجاع عربي موثوق (UTF-8/CP1256)"
        else:
            detail = "لا موجيبيك قابل للاسترجاع"
        return False, None, Evidence("mojibake", 0.0, detail)

    after = _count_arabic(recovered)
    if after <= before:
        return False, None, Evidence("mojibake", 0.0, "إعادة الترميز لم تزد النص عربية")

    conf = 1.0 if mode.startswith("full") else 0.92
    ev = Evidence(
        "mojibake",
        conf,
        f"استرجاع {mode}: الحروف العربية {before} → {after}",
    )
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


def _joins_forward(f: JoiningForm) -> bool:
    return f in (JoiningForm.INITIAL, JoiningForm.MEDIAL)


def _joins_backward(f: JoiningForm) -> bool:
    return f in (JoiningForm.MEDIAL, JoiningForm.FINAL)


def _signal_joining_forms(text: str) -> tuple[float, str] | None:
    """
    الشاهد الثاني: هويّةُ الوصل — وهي **برهانٌ** لا أمارة.

    في العربية قاعدةٌ لا تتخلّف: إن وصلَ حرفٌ بما بعده، فتاليه موصولٌ
    بما قبله ولا بدّ. وبلغة صيغ يونيكود:

        joins_forward(a)  ==  joins_backward(b)      لكل حرفين متجاورين

    هذه هويّةٌ تصدق في **كل** نصٍّ منطقيّ الترتيب بلا استثناء. فخرقُها
    مرّةً واحدة يُثبت أن الترتيب ليس منطقياً. ولذلك الشاهد **لا تماثليّ**:

        خرقٌ واحد        →  برهانُ انعكاس     (يقين)
        صفرُ خروق        →  اتّساقٌ مع المنطقيّ (لا برهانَ عليه)

    وهذا أقوى من فحص طرفَي الكلمة وحدهما — وقد كلّفنا ضعفُ الفحص
    القديم عطباً: «الإجراء» طرفاها منفصلان فلا ينطقان، فأفلتت.

    ونستثني التشكيل: أشكاله (U+FE70–FE7F) تحمل وسوماً لا تصف وصلاً
    فتكسر السلسلة كذباً.
    """
    correct = wrong = 0
    for token in _ARABIC_TOKEN.findall(text):
        forms = []
        for c in token:
            f = PF_JOINING_FORM.get(c)
            if f is None or f is JoiningForm.UNKNOWN:
                continue
            base = PF_TO_BASE.get(c, c)
            if base and unicodedata.category(base[0]) == "Mn":
                continue  # تشكيل — لا شهادة له في الوصل
            forms.append(f)
        for a, b in zip(forms, forms[1:]):
            if _joins_forward(a) == _joins_backward(b):
                correct += 1
            else:
                wrong += 1

    pairs = correct + wrong
    if pairs == 0:
        return None
    if wrong:
        # خرقٌ واحد يكفي برهاناً؛ وكثرتها ترفع الثقة لا أصل الحكم.
        score = min(1.0, 0.6 + 0.4 * wrong / pairs)
        return score, f"خُرقت هويّة الوصل {wrong} مرة من {pairs} تجاوراً — برهانُ انعكاس"
    return -1.0, f"هويّة الوصل سليمة في {pairs} تجاوراً — متّسقٌ مع الترتيب المنطقي"


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


def detect_visual_order(
    text: str, shaped_source: str | None = None
) -> tuple[float, list[Evidence]]:
    """
    يُرجع درجة في [-1, 1]:  +1 معكوس يقيناً، -1 منطقيّ يقيناً، 0 لا دليل.

    :param shaped_source: النصّ **قبل** التطبيع، إن توفّر.

    ولِمَ معاملان لنصٍّ واحد؟ لأن الشواهد الثلاثة لا تعيش في طبقةٍ واحدة:

      * `final_only_letters` و`definite_article` يحتاجان الحروف **الأصلية**،
        فالتاء المربوطة مخبوءةٌ خلف U+FE93 ما لم تُطبَّع.
      * `joining_forms` يحتاج الأشكال **الرسومية**، فالتطبيع يمحوها ويمحو
        شهادتها معها.

    فالتطبيع يفتح عيناً ويفقأ أخرى. وقد كلّفنا هذا الدرسُ عطباً حقيقياً:
    كانت كلمةٌ مفردةٌ بلا تاءٍ مربوطة تُفلت من الكشف بعد التطبيع، لأن
    شاهدها الوحيد (صيغ الوصل) كان قد مُحي قبل أن يُستشهَد به.

    فمرِّر الطبقتين معاً تشهدا معاً.
    """
    tokens = _ARABIC_TOKEN.findall(text)
    signals = {
        "final_only_letters": _signal_final_only_letters(tokens),
        "joining_forms": _signal_joining_forms(
            shaped_source if shaped_source is not None else text
        ),
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
        dg.evidence.append(Evidence("empty", 1.0, "لا طبقة نصية — الدرجة ٤ غير منفَّذة"))
        dg.confidence = _confidence(dg)  # لا مخرجَ يتخطّى حاسب الثقة
        return dg

    # الموجيبيك أولاً: إن وُجد فكل قياس بعده على نصٍّ مشوّه لا معنى له.
    is_moji, _, ev = detect_mojibake(text)
    dg.evidence.append(ev)
    if is_moji:
        dg.defects.append(Defect.MOJIBAKE)
        dg.metrics["mojibake"] = True
        dg.confidence = _confidence(dg)  # لا مخرجَ يتخطّى حاسب الثقة
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

    # انقلاب لام-ألف: يُفحص على الأصل لأن شاهده (الألف المزدوجة) قاطع،
    # ولأنه إن وُجد فقد وقع **قبل** أن يصلنا النص — أي أن أداةً أخرى
    # فكّت الرباط ثم عكست. نحن لا نُوقعه، لكنّا نرثه.
    decisive, ambiguous, ev = detect_lam_alef_transposition(text)
    dg.evidence.append(ev)
    dg.metrics["lam_alef_decisive"] = decisive
    dg.metrics["lam_alef_ambiguous"] = ambiguous
    if decisive:
        dg.defects.append(Defect.LAM_ALEF_TRANSPOSED)

    tw_ratio, ev = detect_tatweel(text)
    dg.evidence.append(ev)
    if tw_ratio > th["tatweel"]:
        dg.defects.append(Defect.TATWEEL_NOISE)

    # نطبّع المفردات هنا لأجل الشواهد الحرفية وحدها، ونُبقي الخام شاهداً
    # على الوصل. وبدون هذا يعمى شاهدان من ثلاثة — والتاء المربوطة أقواها
    # وزناً — لأنها مخبوءةٌ خلف شكلها الرسومي U+FE93. قِسناه على سطرٍ
    # واحد: 0.79 بشاهدٍ واحد، مقابل 0.93 بالثلاثة.
    #
    # ولا يُغيّر هذا النصَّ ولا يُطبّعه: `diagnose` لا يكتب شيئاً أبداً،
    # وإنما يفتح عينه على طبقتين معاً كما يفعل الأنبوب.
    from .normalize import fold_simple_forms

    order_score, order_ev = detect_visual_order(
        fold_simple_forms(text), shaped_source=text
    )
    # حارسُ كفاية العيّنة يحرس الإحصاء وحده. أما هويّة الوصل فبرهانٌ،
    # والبرهانُ لا يحتاج عيّنةً: خرقٌ واحد في «توقف!» يكفي كخرقٍ في صفحة.
    proof = next(
        (e for e in order_ev if e.name == "joining_forms" and e.value > 0), None
    )
    if arabic_chars >= th["min_arabic_chars"] or proof:
        dg.evidence.extend(order_ev)
        dg.metrics["order_score"] = order_score
        if order_score > th["visual_order"]:
            dg.defects.append(Defect.VISUAL_ORDER)
    else:
        dg.evidence.append(
            Evidence("visual_order", 0.0, "العيّنة العربية أصغر من عتبة الحكم، ولا برهان")
        )
        dg.metrics["order_score"] = 0.0

    if not dg.defects:
        dg.defects.append(Defect.NONE)

    dg.confidence = _confidence(dg)
    return dg


def _confidence(dg: Diagnosis) -> float:
    """
    يملأ `defect_confidence` ويُرجع أضعفَ حلقةٍ فيه.

    القاعدة التي كانت غائبة: **افصل القاطع عن الظنّيّ.**

    كانت الدالة تضرب كلَّ ثقةٍ في «كفاية العيّنة»، فتُخرج ٠٫٥٢ لتشخيصٍ
    قاطعٍ لا شكّ فيه (فحصُ نطاقٍ حتميّ على «ﻣﺮﺣﺒﺎ»)، و٠٫٤٤ لنصٍّ سليم.
    رقمٌ لا يعني شيئاً — والمكتبة التي تُصدر شهادات ثقة لا تُصدَّق إن كانت
    شهادتُها لا تفرّق بين اليقين والظنّ.

    والقسمة ثلاثيّة:

      * **قاطعٌ** (نطاقٌ أو اختبارٌ جبريّ): ١٫٠ دائماً. حجمُ العيّنة لا
        دخل له: فحصُ نطاقٍ على خمسة محارف قاطعٌ كفحصه على خمسة آلاف.
      * **ظنّيّ** (الاتجاه): بدرجة شاهده.
      * **شهادةُ نفي** («سليم»): وحدَها يحكمها حجمُ العيّنة، إذ هي
        استدلالٌ بغياب الدليل. ولا تبلغ اليقين أبداً مهما طال النصّ —
        فغيابُ العلّة ليس برهانَ سلامة. وهذا التماثلُ نفسه الذي نطبّقه
        على الأدلّة في سائر المكتبة: **نَدحض ولا نُزكّي.**
    """
    if Defect.NONE in dg.defects:
        sample = min(1.0, dg.char_count / 300.0)
        conf = round(0.30 + 0.60 * sample, 3)  # سقفُها ٠٫٩ عمداً
        dg.defect_confidence[Defect.NONE] = conf
        return conf

    for d in dg.defects:
        if d in DETERMINISTIC_DEFECTS:
            dg.defect_confidence[d] = 1.0
        elif d is Defect.VISUAL_ORDER:
            dg.defect_confidence[d] = round(
                min(1.0, abs(dg.metrics.get("order_score", 0.0))), 3
            )
        else:  # pragma: no cover - علّةٌ جديدة لم تُصنَّف بعد
            dg.defect_confidence[d] = 0.5

    return round(min(dg.defect_confidence.values()), 3)
