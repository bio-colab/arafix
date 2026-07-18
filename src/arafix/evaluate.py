"""
القياس — CER و WER في مقابل حقيقةٍ مرجعية.

**لِمَ هذه الوحدة موجودة أصلاً؟**

لأن قولنا «٠ إخفاق من ١٢» كان مقيساً على ملفاتٍ ولّدناها بأنفسنا. وهذا
يقارب الاختبار الدائريّ: أثبتنا أن مولّدنا معكوسُ مصلِحنا، لا أن مصلِحنا
يطابق الواقع. والمقارنةُ بمشاريع أخرى في هذا الباب (وكلُّها تحمل هراوةَ
`evaluate`) كشفت الثغرة: **رقمٌ على ملفاتك أنت، أصدقُ من كل شهاداتنا.**

فهذه الوحدة لا تُصلح شيئاً — تقيس فقط. وهي عمداً:

  * **بلا تبعيّات** — لا `jiwer` ولا `Levenshtein`. تعمل في أيّ بيئة.
  * **تقارن المسارات** — لا تسألك أيّ محرّك أفضل لملفاتك، بل تقيسه.
  * **تُطبِّع قبل المقارنة** — بخياراتٍ مصرَّحة، فلا تُخفي فرقاً وراء تسوية.

الاستعمال:

    arafix eval thesis.pdf --truth thesis.txt --compare
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import NormalizeConfig, normalize_text

__all__ = [
    "EditDistance",
    "levenshtein_reference",
    "EvalConfig",
    "EvalReport",
    "levenshtein",
    "cer",
    "wer",
    "evaluate_text",
    "evaluate_pdf",
    "compare_extractors",
]


_WS = re.compile(r"\s+")


@dataclass
class EvalConfig:
    """
    ما الذي نتسامح فيه قبل أن نعدّ الخطأ خطأً.

    كلُّ مفتاحٍ هنا **يُخفي** فرقاً، فكلٌّ منها مطفأ إلا ما لا غنى عنه.
    من يقيس بعد تسويةِ كل شيء يقيس تسويتَه لا مكتبتَه.
    """

    #: توحيد المسافات المتتالية. لا غنى عنه: تباعدُ PDF ليس معنى.
    collapse_whitespace: bool = True

    #: تجاهل التشكيل. يرفع الدرجة كذباً إن كان مرجعُك مشكولاً.
    ignore_diacritics: bool = False

    #: توحيد صور الألف والتاء المربوطة. للبحث لا للاسترجاع.
    ignore_orthographic_variants: bool = False

    #: تجاهل الترقيم. **لا تفعّله لتقييم هذه المكتبة**: المحايدات أهشُّ
    #: ما فيها، وإخفاؤها يمحو أصدق ما يقيسه هذا الاختبار.
    ignore_punctuation: bool = False


@dataclass
class EditDistance:
    """مسافةُ تحرير مفصَّلة — العدد وحده لا يقول أين الخلل."""

    distance: int
    length: int

    @property
    def rate(self) -> float:
        return self.distance / self.length if self.length else 0.0

    @property
    def accuracy(self) -> float:
        return max(0.0, 1.0 - self.rate)


def _trim_common(a: list, b: list) -> tuple[list, list]:
    """
    يقتطع البادئة واللاحقة المشتركتين — فهما لا تُسهمان في المسافة.

    مجّانيّ (O(n) مقارنات) وقاطع الأثر في حالتنا: نحن نقيس مُستخرَجاً
    جيّداً في مقابل مرجعه، فأكثرُهما متطابق.
    """
    i, n = 0, min(len(a), len(b))
    while i < n and a[i] == b[i]:
        i += 1
    a, b = a[i:], b[i:]
    j = 0
    n = min(len(a), len(b))
    while j < n and a[len(a) - 1 - j] == b[len(b) - 1 - j]:
        j += 1
    return (a[: len(a) - j], b[: len(b) - j]) if j else (a, b)


def _myers(a: list, b: list) -> int:
    """
    خوارزمية مايرز الشعاعية-البِتّية (1999) — مسافةٌ مضبوطة في O(n·⌈m/w⌉).

    الفكرة: تُمثَّل حالةُ عمودٍ كاملٍ من المصفوفة بأعدادٍ صحيحة، ويُحسب
    العمود التالي بعملياتٍ بِتّية عليها — لا بحلقةٍ على خلاياه.

    وهنا تنقلب قلّةُ حيلة بايثون فضيلةً: أعدادُه **غير محدودة الدقّة**،
    فعرضُ «الكلمة» عندنا هو طولُ النمط كلّه (w = m) لا ٦٤ بِتّاً. فعمودٌ
    من ٣٢٠٠ خلية يُحسب بعشر عملياتٍ على عددٍ من ٣٢٠٠ بِتّ — تُنفَّذ في C
    داخل مفسّر بايثون. فينقلب O(n·m) إلى O(n) عمليةً كبيرة.

    وهذا ما تفعله RapidFuzz في C++ تحت الغطاء. الفرقُ أننا لا نحتاجها.

    البِتّياتُ هنا كثيفةٌ عمداً وتتبعُ صياغة Hyyrö حرفاً بحرف؛ فالضامنُ
    ليس وضوحَ السطر بل `levenshtein_reference` والاختبارُ العشوائيّ عليه.
    """
    m = len(a)
    if m == 0:
        return len(b)
    mask = (1 << m) - 1

    peq: dict = {}
    for i, ch in enumerate(a):
        peq[ch] = peq.get(ch, 0) | (1 << i)

    vp, vn, score = mask, 0, m
    last = 1 << (m - 1)
    get = peq.get
    for ch in b:
        eq = get(ch, 0)
        xv = eq | vn
        xh = ((((eq & vp) + vp) & mask) ^ vp) | eq
        hp = vn | (mask & ~(xh | vp))
        hn = vp & xh
        if hp & last:
            score += 1
        elif hn & last:
            score -= 1
        hp = ((hp << 1) | 1) & mask
        hn = (hn << 1) & mask
        vp = hn | (mask & ~(xv | hp))
        vn = hp & xv
    return score


def levenshtein(a: list, b: list) -> int:
    """
    مسافة ليفنشتاين — **مضبوطة لا تقريبية**، بخوارزمية أوكّونن.

    كانت هذه الدالة تحسب المصفوفة كاملةً: O(n·m). وبنشمارك خارجيّ فضحها،
    وقياسُنا على صفحةٍ واقعية (٣١٩٥ محرفاً) أكّد: **٢٥٣٦ ms للصفحة**، أي
    **١٢ دقيقةً ونصفاً لأطروحةٍ من ٣٠٠ صفحة**. أي أن `arafix eval` —
    وهي الأداة التي أضفناها لنُثبت النزاهة — كانت غير صالحةٍ للاستعمال
    على الأطاريح التي بُنيت لأجلها.

    والعلاج **خوارزميّ لا تبعيّة**، وقوامه ملاحظتان:

      ١. البادئة واللاحقة المشتركتان لا تُسهمان في المسافة — تُقتطعان
         بـ O(n) مقارنات.
      ٢. حسابُ عمودٍ كامل بعملياتٍ بِتّية على عددٍ واحد بدل حلقةٍ على
         خلاياه (مايرز 1999). وهنا تنقلب قلّةُ حيلة بايثون فضيلةً: أعدادُه
         غير محدودة الدقّة، فالعمودُ كلُّه عددٌ واحد. انظر `_myers`.

    والنتيجة **مضبوطةٌ** لا تقريبية، والضامنُ اختبارٌ عشوائيّ على آلاف
    الأزواج ضدّ `levenshtein_reference`.

    وقد قيسَت RapidFuzz (C++) فكانت أسرع ١١× من مايرز — ولم تُؤخَذ.
    مايرز تُنهي أطروحةً من ٣٠٠ صفحة في ١٫٧ ثانية، والمكسبُ نزولٌ بها إلى
    ٠٫١٦ — لأحدٍ لا وجود له. وهذه غلطةُ `arafix[ocr]` عينها التي حُذفت
    في 0.5.0: **تبعيّةٌ لحاجةٍ افتراضية**. فإن ظهر مَن يقيس مُدوَّنةً من
    آلاف الصفحات، عاد النقاش ومعه رقمُه.

    >>> levenshtein(list("المجلات"), list("المجالت"))
    2
    >>> levenshtein(list("كتاب"), list("كتاب"))
    0
    >>> levenshtein([], list("نص"))
    2
    """
    if a == b:
        return 0
    a, b = _trim_common(a, b)
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a

    return _myers(b, a)  # النمطُ هو الأقصر: عددٌ أصغر فعملياتٌ أرخص


def levenshtein_reference(a: list, b: list) -> int:
    """
    التنفيذ المرجعيّ: مصفوفةٌ كاملة، بطيءٌ وبديهيّ.

    نُبقيه **عمداً** لا للاستعمال بل ليكون محكّاً: خوارزمية أوكّونن
    أسرع بمراتب وأدقّ ما يقال فيها إنها ذكيّة — والذكاءُ في الكود يُختبَر
    بالبلاهة. فاختبارٌ عشوائيّ يقارن الاثنين على آلاف الأزواج.
    """
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _prepare(text: str, cfg: EvalConfig) -> str:
    out = text
    if cfg.ignore_diacritics or cfg.ignore_orthographic_variants:
        out = normalize_text(
            out,
            NormalizeConfig(
                fold_presentation_forms=False,
                strip_diacritics=cfg.ignore_diacritics,
                unify_alef=cfg.ignore_orthographic_variants,
                unify_taa_marbuta=cfg.ignore_orthographic_variants,
                unify_alef_maqsura=cfg.ignore_orthographic_variants,
            ),
        )
    if cfg.ignore_punctuation:
        out = re.sub(r"[^\w\s\u0600-\u06FF]", "", out)
    if cfg.collapse_whitespace:
        out = _WS.sub(" ", out).strip()
    return out


def cer(reference: str, hypothesis: str, config: EvalConfig | None = None) -> EditDistance:
    """معدّل خطأ المحارف."""
    cfg = config or EvalConfig()
    ref, hyp = _prepare(reference, cfg), _prepare(hypothesis, cfg)
    return EditDistance(levenshtein(list(ref), list(hyp)), len(ref))


def wer(reference: str, hypothesis: str, config: EvalConfig | None = None) -> EditDistance:
    """
    معدّل خطأ الكلمات.

    أقسى من CER وأصدق لهذه المكتبة: كلمةٌ انقلب فيها حرفان («المجالت»)
    تكلّف ٢/٧ في CER وتكلّف كلمةً كاملة في WER. ونحن نُخطئ في الكلمات
    لا في الحروف، فليكن القياس حيث الخطأ.
    """
    cfg = config or EvalConfig()
    ref = _prepare(reference, cfg).split()
    hyp = _prepare(hypothesis, cfg).split()
    return EditDistance(levenshtein(ref, hyp), len(ref))


@dataclass
class EvalReport:
    """حصيلة قياسٍ واحد."""

    label: str
    cer: EditDistance
    wer: EditDistance
    ref_chars: int = 0
    hyp_chars: int = 0
    worst_lines: list[tuple[int, str, str]] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - عرض
        return (
            f"{self.label:22s} CER {self.cer.rate:6.2%}  WER {self.wer.rate:6.2%}  "
            f"(دقّةُ محارف {self.cer.accuracy:.2%})"
        )


def evaluate_text(
    reference: str,
    hypothesis: str,
    label: str = "نصّ",
    config: EvalConfig | None = None,
    worst: int = 3,
) -> EvalReport:
    """
    يقيس نصّاً مقابل مرجعه، ويسرد أسوأ سطوره.

    سردُ الأسوأ مقصود: المعدّل يقول «٣٪ خطأ» ولا يقول أين. والثلاثةُ
    الأسوأ تدلّك على النمط في ثوانٍ.
    """
    cfg = config or EvalConfig()
    rep = EvalReport(
        label=label,
        cer=cer(reference, hypothesis, cfg),
        wer=wer(reference, hypothesis, cfg),
        ref_chars=len(reference),
        hyp_chars=len(hypothesis),
    )

    ref_lines = [ln for ln in reference.split("\n") if ln.strip()]
    hyp_lines = [ln for ln in hypothesis.split("\n") if ln.strip()]
    scored = []
    for i, (r, h) in enumerate(zip(ref_lines, hyp_lines), 1):
        d = cer(r, h, cfg)
        if d.distance:
            scored.append((d.rate, i, r, h))
    scored.sort(reverse=True)
    rep.worst_lines = [(i, r, h) for _, i, r, h in scored[:worst]]
    return rep


def evaluate_pdf(
    pdf_path: str,
    truth_path: str,
    extractor: str = "auto",
    config: EvalConfig | None = None,
) -> EvalReport:
    """يستخرج ملفاً ويقيسه مقابل حقيقةٍ مرجعية نصّية."""
    from .pipeline import PipelineConfig, extract_pdf

    with open(truth_path, encoding="utf-8") as fh:
        truth = fh.read()
    doc = extract_pdf(pdf_path, PipelineConfig(extractor=extractor))
    return evaluate_text(truth, doc.text, label=extractor, config=config)


def compare_extractors(
    pdf_path: str,
    truth_path: str,
    config: EvalConfig | None = None,
) -> list[EvalReport]:
    """
    يقيس كل المسارات المتاحة على **ملفك أنت**، ويرتّبها.

    هذه هي الدالة التي تهمّك حقاً. نحن قسنا على ملفاتٍ ولّدناها، وملفاتُك
    أقذر دائماً. فلا تصدّق أرقامنا — أَجرِ القياس.
    """
    from .extractors import REGISTRY, PyMuPDFExtractor, register

    if "mupdf-bidi" not in REGISTRY:

        @register
        class _MuPDFBidi(PyMuPDFExtractor):
            """مسار المقارنة: نثق ببِدي MuPDF بدل قراءتنا الهندسية."""

            name = "mupdf-bidi"

            def __init__(self) -> None:
                super().__init__(bidi="mupdf")

    reports = []
    for name, cls in REGISTRY.items():
        if not cls.available():
            continue
        try:
            reports.append(evaluate_pdf(pdf_path, truth_path, name, config))
        except Exception as exc:  # pragma: no cover - دفاعيّ
            print(f"تعذّر قياس {name}: {exc}")
    reports.sort(key=lambda r: r.cer.rate)
    return reports
