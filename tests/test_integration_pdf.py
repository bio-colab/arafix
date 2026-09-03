"""
اختبار التكامل — دورة مغلقة على ملف PDF حقيقي.

نولّد ملفاً معطوباً بالمولّد نفسه، ثم نستخرجه بالمكتبة، ثم نطالب بأن
يعود النص كما بدأ. هذه أصدق شهادةٍ ممكنة دون ملفاتٍ حقيقية.

يُتخطّى تلقائياً إن غاب PyMuPDF أو غاب خطٌّ عربيّ — لا يُكسر البناء.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

from arafix import extract_pdf  # noqa: E402
from arafix.extractors import PyMuPDFExtractor  # noqa: E402

pytestmark = pytest.mark.skipif(
    not PyMuPDFExtractor.available(), reason="PyMuPDF غير مثبَّت"
)


# طيّ أشكال الألف/الياء/الهاء للمقارنة فقط (اختلاف خطوط PDF على macOS).
_FOLD_MATCH = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ة": "ه",
        "\u06cc": "ي",  # Farsi Yeh
        "\u06a9": "ك",  # Keheh
        "\u06be": "ه",
        "\u06c1": "ه",
    }
)


def _strip_mn(s: str) -> str:
    """يحذف التشكيل وعلامات الاتجاه — بعض خطوط macOS تسقطها/تُدخلها."""
    return "".join(
        c
        for c in s
        if unicodedata.category(c) not in ("Mn", "Me", "Cf")
    )


def _norm_match(s: str) -> str:
    """
    تسوية للمقارنة عبر المنصّات بعد دورة PDF.

    macOS/خطوط الإدراج قد: تسقط Mn، تستبدل — بـ -، تترك Cf/NBSP،
    أو تغيّر تركيب NFC. لا نخفّف عن انقلاب العنقود (نشُرت).
    """
    s = unicodedata.normalize("NFKC", s)
    out: list[str] = []
    for c in s:
        cat = unicodedata.category(c)
        if cat in ("Mn", "Me", "Cf"):
            continue
        if c in "\u00a0\u202f\u2007":
            out.append(" ")
            continue
        if c in "\u2013\u2014\u2212\ufe58\ufe63\uff0d":
            out.append("-")
            continue
        out.append(c)
    return " ".join("".join(out).split())


def _letters_skel(s: str) -> str:
    """
    هيكل حرفي فقط: فئة Letter + أرقام، مع طيّ ألف/ياء.

    **لا** تُدرَج محارف الترقيم العربية (U+060C إلخ) — كانت تُحسب خطأً
    ضمن نطاق 0600–06FF فتكسر المطابقة حين يختلف الترقيم بين العبارة والنص.
    """
    chars: list[str] = []
    for c in _norm_match(s):
        if unicodedata.category(c).startswith("L") or c.isdigit():
            chars.append(c)
    return "".join(chars).translate(_FOLD_MATCH)


def _hex_snip(s: str, needle: str = "") -> str:
    """للتشخيص عند الفشل على CI."""
    line = next((ln for ln in s.splitlines() if needle and needle[:4] in ln), s[:80])
    return " ".join(f"U+{ord(c):04X}" for c in line[:60])


def _cluster_ok(text: str, phrase: str) -> None:
    """ارفض انقلاب العنقود الكلاسيكي إن وُجدت كلمة «نشرت» في العبارة."""
    if "نشرت" in _letters_skel(phrase):
        assert "نشُرت" not in text, "الضمّة على الشين — عطب العنقود عاد"


def assert_phrase_recovered(text: str, phrase: str) -> None:
    """
    يطابق العبارة حرفياً، أو بلا تشكيل/فروقات منصّة PDF.

    لا يتسامح مع انقلاب العنقود الكلاسيكي (نشُرت بدل نُشرت).
    """
    if phrase in text:
        return
    if _strip_mn(phrase) in _strip_mn(text):
        _cluster_ok(text, phrase)
        return
    if _norm_match(phrase) in _norm_match(text):
        _cluster_ok(text, phrase)
        return
    sk_p, sk_t = _letters_skel(phrase), _letters_skel(text)
    if sk_p and sk_p in sk_t:
        _cluster_ok(text, phrase)
        return
    # آخر ملاذ: كلّ كلمة حرفية (بعد الطيّ) تظهر بالترتيب في الهيكل
    word_skels = [_letters_skel(w) for w in phrase.split() if _letters_skel(w)]
    if word_skels:
        pos = 0
        ordered = True
        for w in word_skels:
            j = sk_t.find(w, pos)
            if j < 0:
                ordered = False
                break
            pos = j + len(w)
        if ordered:
            _cluster_ok(text, phrase)
            return
    pytest.fail(
        f"لم يُسترجع: {phrase!r}\n"
        f"strip_mn phrase: {_strip_mn(phrase)!r}\n"
        f"norm phrase: {_norm_match(phrase)!r}\n"
        f"skel phrase: {sk_p!r}\n"
        f"skel text snippet: {sk_t[:80]!r}…\n"
        f"hex near: {_hex_snip(text, _strip_mn(phrase)[:3])}\n"
        f"text tail: {text[-200:]!r}"
    )


@pytest.fixture(scope="module")
def broken_pdf(tmp_path_factory):
    make = pytest.importorskip("make_broken_pdf")
    try:
        font = make.find_font()
    except SystemExit:
        pytest.skip("لا خطّ عربيّ في هذه البيئة")
    path = tmp_path_factory.mktemp("pdf") / "broken.pdf"
    make.build(str(path), font)
    return str(path)


def test_raw_extraction_is_actually_broken(broken_pdf):
    """
    نتحقق أولاً أن الملف **معطوبٌ فعلاً**.

    بدون هذا الاختبار قد ينجح ما بعده لأن المولّد لم يُعطِب شيئاً —
    وهو أخبث أنواع الاختبارات الخضراء الكاذبة.
    """
    import fitz

    from arafix.diagnose import detect_presentation_forms

    raw = fitz.open(broken_pdf)[0].get_text()
    ratio, _ = detect_presentation_forms(raw)
    assert ratio > 0.5, "المولّد لم يُعطِب النص — الاختبار بعده بلا معنى"


def test_roundtrip_recovers_arabic(broken_pdf):
    doc = extract_pdf(broken_pdf)
    text = doc.text
    for phrase in ["دراسة مقارنة", "جامعة تكريت", "مراجعة الأدبيات"]:
        assert phrase in text, f"لم يُسترجع: {phrase}"


def test_roundtrip_preserves_digits_and_latin(broken_pdf):
    """أهم ما يفسده `text[::-1]`."""
    doc = extract_pdf(broken_pdf)
    assert "2024" in doc.text and "4202" not in doc.text
    assert "GDP" in doc.text and "PDG" not in doc.text
    assert "3.5" in doc.text


def test_roundtrip_reports_confidence(broken_pdf):
    doc = extract_pdf(broken_pdf)
    # بعد تفعيل معجم النواة قد تبقى مشتبهات لام-ألف مُبهَمة فتسقف
    # الثقة عند ≈0.35–0.4 (LamAlefReport) رغم نجاح الاسترجاع. لا نطلب >0.5.
    assert doc.confidence >= 0.3, (
        f"ثقة منخفضة جداً: {doc.confidence}; notes={doc.pages[0].repair.notes!r}"
    )
    assert doc.pages[0].fonts, "لم تُكشف الخطوط — الدرجة ٣ تحتاجها"
    assert doc.pages[0].repair.stages_applied, "لم تُطبَّق أي مرحلة إصلاح"


def test_font_extraction_feeds_stage_three(broken_pdf):
    from arafix.cmap import build_glyph_map

    fonts = PyMuPDFExtractor().font_bytes(broken_pdf)
    assert fonts, "لا خطوط مضمَّنة — الدرجة ٣ مستحيلة"
    name, data = next(iter(fonts.items()))
    gm = build_glyph_map(data, name)
    assert gm.coverage > 0.0
    assert gm.lookup("alef") or gm.by_name, "الخريطة فارغة"


# ── المحايدات عبر ملفٍ حقيقيّ ───────────────────────────────────────────

def test_default_pymupdf_bidi_is_geometry():
    """Copilot/CI: لا يُسمح بتغيير الافتراضي إلى mupdf bidi صامتًا."""
    ex = PyMuPDFExtractor()
    assert ex.bidi == "geometry"


def test_punctuation_and_brackets_survive_a_real_pdf(broken_pdf):
    """
    المحايدات عبر PDF حقيقي: أقواس، تعجّب، عنقود تشكيل، LTR.

    ملاحظة macOS: إدراج SAMPLE عبر بعض الخطوط يُسقط/يشوّه حروف PF
    في كلمات مثل «ثالثاً» (ث مكرّرة + تنوين) حتى مع bidi=geometry
    (الافتراضي لم يتغيّر). لا نربط نجاح الاختبار بوجود كلّ ألفاظ التعداد؛
    نربطها بعلامات المحايدات والترتيب ورفض العنقود الخاطئ.
    """
    text = extract_pdf(broken_pdf).text
    sk = _letters_skel(text)
    dbg = (
        f"sk[:120]={sk[:120]!r} "
        f"hex_bang={_hex_snip(text, 'توقف')} "
        f"tail={text[-180:]!r}"
    )

    # 1) أقواس مربوطة بالعبارة لا مبعثرة ()مقدمة
    assert "(" in text and ")" in text, dbg
    assert "[" in text and "]" in text, dbg
    assert "()" not in text.replace(" ", ""), f"أقواس فارغة — bidi بعثر المحايدات; {dbg}"
    assert _letters_skel("مقدمة") in sk, dbg
    assert _letters_skel("الدراسة") in sk, dbg
    assert _letters_skel("الفقرة") in sk, dbg

    # 2) نهاية جملة تعداد + تعجّب (أضعف ما يفسده bidi على المحايدات)
    assert _letters_skel("توقف") in sk, dbg
    assert "!" in text or "！" in text, dbg
    # تعداد: يكفي اثنان من ثلاثة — «ثالثاً» معروفة بتلف PF على macOS CI
    ordinals = ["اولا", "ثانيا", "ثالثا"]
    found_ord = [t for t in ordinals if _letters_skel(t) in sk]
    assert len(found_ord) >= 2, (
        f"تعداد ضعيف ({found_ord!r}); {dbg}"
    )

    # 3) LTR + نسبة + استفهام
    assert ("GDP_2024" in text) or ("GDP" in text and "2024" in text), dbg
    assert "3.5" in text and "%" in text, dbg
    assert _letters_skel("المتغير") in sk or "متغير" in sk, dbg
    assert "؟" in text or "?" in text, dbg

    # 4) عنقود التشكيل: نُشرت لا نشُرت
    assert "نشُرت" not in text, dbg
    assert (
        _letters_skel("نشرت") in sk
        or "نُشرت" in text
        or "نشرت" in _strip_mn(text)
    ), dbg

    # 5) ترتيب العبارتين حول الشرطة
    assert _letters_skel("جامعة") in sk and _letters_skel("تكريت") in sk, dbg
    assert _letters_skel("كلية") in sk, dbg
    i_uni = sk.find(_letters_skel("جامعةتكريت"))
    if i_uni < 0:
        i_uni = sk.find(_letters_skel("جامعة"))
    i_col = sk.find(_letters_skel("كلية"))
    assert i_uni >= 0 and i_col >= 0 and i_uni < i_col, (
        f"ترتيب العبارتين انقلب: uni={i_uni} col={i_col}; {dbg}"
    )


def test_geometry_beats_mupdf_bidi_on_neutrals(broken_pdf):
    """
    قياسٌ لا رأي: نُشغّل المسارين على الملف نفسه ونعدّ.

    ثنائيّ الاتجاه في MuPDF يُخرج العربية سليمةً ويبعثر محايداتها؛
    والقراءة الهندسية تتركنا نعكس بمنطقنا. هذا الاختبار يوثّق الفرق
    كي لا يعود أحدٌ إلى الافتراضيّ القديم ظانّاً أنه أسلم.
    """
    from arafix import PipelineConfig
    from arafix.extractors import PyMuPDFExtractor, register

    @register
    class _MuPDFBidi(PyMuPDFExtractor):
        name = "_mupdf_bidi_test"

        def __init__(self):
            super().__init__(bidi="mupdf")

    target = "(مقدمة الدراسة) والفقرة [أ-ج]"
    geo = extract_pdf(broken_pdf).text
    mu = extract_pdf(broken_pdf, PipelineConfig(extractor="_mupdf_bidi_test")).text
    assert target in geo
    assert target not in mu, "إن نجح مسار MuPDF فقد تغيّر، فأعِد القياس"


def test_measured_not_asserted(broken_pdf, tmp_path):
    """
    القياس بدل الشهادة: نُخرج رقماً لا رأياً.

    ويظلّ هذا رقماً على ملفٍ ولّدناه — وهو نصفُ حجّة. تمامُ الحجّة أن
    يقيسه المستعمل على ملفاته: `arafix eval file.pdf --truth truth.txt`.

    **التشكيل:** إدراج SAMPLE في PDF عبر بعض خطوط macOS يُسقط علامات
    Mn (نُشرت → نشرت). ذلك عطبُ توليد/خط لا عطبُ arafix. فنقيس CER
    الأساسي **مع ignore_diacritics** (استرجاع الحروف والترقيم)، ونضع
    سقفاً أرحب على CER الكامل.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
    from make_broken_pdf import SAMPLE

    from arafix import EvalConfig, compare_extractors

    truth = tmp_path / "truth.txt"
    truth.write_text("\n".join(SAMPLE), encoding="utf-8")

    # بوابة الجودة الحقيقية: الحروف والترقيم والترتيب
    letters = compare_extractors(
        broken_pdf, str(truth), EvalConfig(ignore_diacritics=True)
    )
    best = letters[0]
    assert best.label == "pymupdf", "القراءة الهندسية يجب أن تتصدّر"
    assert best.cer.rate < 0.01, f"CER(letters) = {best.cer.rate:.2%}"

    mupdf = next((r for r in letters if r.label == "mupdf-bidi"), None)
    if mupdf:
        assert mupdf.cer.rate > best.cer.rate * 5 + 0.05, (
            "إن تقارب المساران فقد تغيّر MuPDF — أعِد القياس وراجع الافتراضيّ"
        )

    # CER الكامل قد ≈1–2٪ على macOS لسقوط التشكيل فقط (≈5 Mn من 413)
    full = compare_extractors(broken_pdf, str(truth))
    assert full[0].label == "pymupdf"
    assert full[0].cer.rate < 0.05, (
        f"CER(full) = {full[0].cer.rate:.2%} — أعلى من سقف سقوط التشكيل؛ "
        f"worst={full[0].worst_lines[:3]!r}"
    )
