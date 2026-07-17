"""
محرّك PyMuPDF — الافتراضي.

اخترناه افتراضياً لثلاثة أسباب: أسرع محرّكات بايثون، ويكشف الخطوط
المضمَّنة (وهو شرط الدرجة ٣)، ويُخرج بنيةً غنية (`rawdict`) فيها
إحداثيات كل جليف — نحتاجها حين نعيد ترتيب السطور.
"""

from __future__ import annotations

import contextlib
import unicodedata
from collections.abc import Iterator

from .base import Extractor, RawPage

__all__ = ["PyMuPDFExtractor"]


class PyMuPDFExtractor(Extractor):
    name = "pymupdf"

    def __init__(self, sort: bool = False, bidi: str = "geometry") -> None:
        """
        :param sort: يرتّب الكتل بإحداثياتها قبل الإخراج.

        **افتراضياً `False`، ومخالفة الشائع هنا مقصودة.**

        كثيرٌ من الأدلة يوصي بـ `sort=True` لتنظيم الصفحة. وهو نصحٌ
        صحيح للإنجليزية، **مُهلِكٌ للعربية**: الترتيب يمشي على المحور
        السينيّ تصاعدياً (يساراً فيميناً)، فيخرج السطر العربي مقلوب
        الكلمات: «العامة السياسة في مقارنة دراسة».

        والأخبث أن الحروف تبقى سليمةً داخل كل كلمة، فيبدو النص صحيحاً
        للوهلة الأولى ولا يفضحه إلا القارئ العربي. ولا تكشفه الدرجة ٢
        لأن شواهدها حرفية داخل الكلمة، والعطب هنا في ترتيب الكلمات.

        فلا تفعّله إلا لصفحاتٍ متعدّدة الأعمدة، وعلى بصيرة.

        :param bidi: من يتولّى ترتيب الاتجاه.

        ``"geometry"`` (الافتراضي) — نقرأ الجليفات بإحداثيّ x الحقيقيّ،
        أي **ترتيب التخزين الخام**، ونترك الدرجة ٢ تعكسه بمنطقنا. وهذا
        ليس تفضيلاً بل نتيجةَ قياس: ثنائيّ الاتجاه في MuPDF يمزّق
        المحايدات (الأقواس والنقطة وعلامة التعجّب) تمزيقاً بيّناً::

            (مقدمة الدراسة)  →  ()مقدمة الدراسة
            الفقرة [أ-ج] هنا →  ج[ هنا-الفقرة ]أ

        العربية تخرج سليمةً والمحايدات مبعثرة. وعلى عيّنةٍ من ١٢ سطراً
        أخفق مسارُ MuPDF في ٩، وأخفق المسار الهندسيّ في صفر.

        ``"mupdf"`` — نثق ببِدي MuPDF. أبقيناه للمقارنة وللملفات التي
        يخدمها أفضل (كمتعدّدة الأعمدة).
        """
        self.sort = sort
        self.bidi = bidi

    @classmethod
    def available(cls) -> bool:
        try:
            import fitz  # noqa: F401
            return True
        except ImportError:
            return False

    def _open(self, path: str):
        try:
            import fitz  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "محرّك PyMuPDF غير مثبَّت: pip install arafix[pdf]"
            ) from exc
        return fitz.open(path)

    #: تسامحٌ رأسيّ في ضمّ الجليفات إلى سطر، كنسبةٍ من قياس الخط.
    LINE_TOLERANCE = 0.5

    def _geometric_text(self, page) -> str:
        """
        يعيد بناء نصّ الصفحة من **تيار الرسم الخام** ومواضع الجليفات.

        ولكلٍّ من ربط العنقود وترتيبه شاهدٌ مختلف، والخلطُ بينهما فخّ:

          * **الربط (أيّ علامةٍ لأيّ حرف؟) → من تيار الرسم.**
            الهندسة تكذب هنا: العلامة عرضُها صفر فتُرسَم عند القلم بعد
            أن تجاوز حرفَها، فـ x عندها يساوي x للحرف **التالي** لا
            لحرفها. وإلصاقُها بـ«الأقرب» يُلصقها بالجار::

                نُشرت  →  نشُرت        أولاً  →  أوًلا

            أما تيار الرسم فلا يكذب: محرّكات التشكيل تُخرج الأساس ثم
            علاماته، بلا استثناء.

          * **الترتيب (أيّ عنقودٍ قبل أيّ؟) → من الهندسة.**
            وهذا ما جئنا لأجله: تيار الرسم قد يكون بصرياً، و x وحده
            يقول أين وقع كلُّ شيء فعلاً.

        ونقرأ التيار بـ ``get_texttrace`` لا ``rawdict``، وهذا **شرطٌ**:
        ``rawdict`` يعيد ترتيب محارفه ببِدي MuPDF قبل أن يسلّمها، فيهدم
        الربط الذي جئنا نستشهد به. قِسناه: في ``rawdict`` يأتي أوّلُ
        محرفٍ من أقصى اليمين، فلا تيارَ فيه أصلاً.
        """
        clusters: list[list] = []  # [y, x, text]
        for span in sorted(page.get_texttrace(), key=lambda s: s.get("seqno", 0)):
            if span.get("type", 0) != 0:  # 0 = نصٌّ مملوء؛ ما عداه حدودٌ أو قصّ
                continue
            for uni, _gid, origin, _bbox in span["chars"]:
                ch = chr(uni)
                if clusters and unicodedata.category(ch) == "Mn":
                    clusters[-1][2] += ch  # العلامة تلحق أساسها في التيار
                else:
                    clusters.append([origin[1], origin[0], ch])
            size = span.get("size") or 0
            if size:
                self._size_hint = size

        if not clusters:
            return ""

        tol = max((getattr(self, "_size_hint", 10) or 10) * self.LINE_TOLERANCE, 1.0)
        clusters.sort(key=lambda c: c[0])  # بالخطّ الأساس، مستقرّاً
        rows: list[list[list]] = [[clusters[0]]]
        for c in clusters[1:]:
            if abs(c[0] - rows[-1][0][0]) <= tol:
                rows[-1].append(c)
            else:
                rows.append([c])

        lines = []
        for row in rows:
            row.sort(key=lambda c: c[1])  # مستقرّ: التعادل يحفظ التيار
            lines.append("".join(c[2] for c in row))
        return "\n".join(lines)

    def pages(self, path: str) -> Iterator[RawPage]:
        doc = self._open(path)
        try:
            for i, page in enumerate(doc, start=1):
                if self.bidi == "geometry":
                    text = self._geometric_text(page)
                else:
                    text = page.get_text("text", sort=self.sort)
                fonts: list[str] = []
                with contextlib.suppress(Exception):
                    fonts = sorted({f[3] for f in page.get_fonts(full=True)})
                yield RawPage(
                    number=i,
                    text=text,
                    fonts=fonts,
                    has_images=bool(page.get_images(full=True)),
                )
        finally:
            doc.close()

    def font_bytes(self, path: str) -> dict[str, bytes]:
        """يستخرج الخطوط المضمَّنة فعلاً (المرجعية منها لا تُضمَّن فتُتخطّى)."""
        doc = self._open(path)
        out: dict[str, bytes] = {}
        try:
            for page in doc:
                for xref, _ext, _type, basefont, *_rest in page.get_fonts(full=True):
                    if basefont in out:
                        continue
                    try:
                        name, ext_, _t, data = doc.extract_font(xref)
                        if data:
                            out[basefont or name] = data
                    except Exception:
                        continue
        finally:
            doc.close()
        return out
