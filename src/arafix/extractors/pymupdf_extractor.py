"""
محرّك PyMuPDF — الافتراضي.

اخترناه افتراضياً لثلاثة أسباب: أسرع محرّكات بايثون، ويكشف الخطوط
المضمَّنة (وهو شرط الدرجة ٣)، ويُخرج بنيةً غنية (`rawdict`) فيها
إحداثيات كل جليف — نحتاجها حين نعيد ترتيب السطور.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from .base import Extractor, RawPage

__all__ = ["PyMuPDFExtractor"]


class PyMuPDFExtractor(Extractor):
    name = "pymupdf"

    def __init__(self, sort: bool = False) -> None:
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
        """
        self.sort = sort

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

    def pages(self, path: str) -> Iterator[RawPage]:
        doc = self._open(path)
        try:
            for i, page in enumerate(doc, start=1):
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
