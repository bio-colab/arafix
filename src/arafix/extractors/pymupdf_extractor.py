"""
محرّك PyMuPDF — الافتراضي.

اخترناه افتراضياً لثلاثة أسباب: أسرع محرّكات بايثون، ويكشف الخطوط
المضمَّنة (وهو شرط الدرجة ٣)، ويُخرج بنيةً غنية فيها إحداثيات كل جليف.
"""

from __future__ import annotations

import contextlib
import unicodedata
from collections.abc import Iterator

from .base import Extractor, RawPage

__all__ = ["PyMuPDFExtractor"]


class PyMuPDFExtractor(Extractor):
    name = "pymupdf"

    def __init__(
        self,
        sort: bool = False,
        bidi: str = "geometry",
        *,
        layout_mode: str = "auto",
    ) -> None:
        """
        :param sort: يرتّب الكتل بإحداثياتها قبل الإخراج (مُهلِك للعربية غالباً).
        :param bidi: ``geometry`` (افتراضي) أو ``mupdf``.
        :param layout_mode: يُمرَّر لتحليل البنية — انظر ``arafix.layout``.
        """
        self.sort = sort
        self.bidi = bidi
        self.layout_mode = layout_mode

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

    LINE_TOLERANCE = 0.5

    def _extract_glyphs(self, page) -> list[tuple[float, float, str, float]]:
        """
        يقرأ تيار الرسم: ``(y, x, text, size)``.

        الربط من التيار (التشكيل)، لا من أقرب x — انظر التعليق التاريخي
        في النسخ السابقة.
        """
        clusters: list[tuple[float, float, str, float]] = []
        size_hint = 10.0
        for span in sorted(page.get_texttrace(), key=lambda s: s.get("seqno", 0)):
            if span.get("type", 0) != 0:
                continue
            size = float(span.get("size") or size_hint or 10.0)
            if size:
                size_hint = size
            for uni, _gid, origin, _bbox in span["chars"]:
                ch = chr(uni)
                if clusters and unicodedata.category(ch) == "Mn":
                    y, x, text, sz = clusters[-1]
                    clusters[-1] = (y, x, text + ch, sz)
                else:
                    clusters.append((origin[1], origin[0], ch, size))
        return clusters

    def _geometric_text_from_glyphs(
        self, glyphs: list[tuple[float, float, str, float]]
    ) -> str:
        from arafix.layout import Glyph, analyze_layout_simple_linear

        gs = [Glyph(y=y, x=x, text=t, size=s) for y, x, t, s in glyphs]
        return analyze_layout_simple_linear(gs)

    def _build_layout(
        self,
        glyphs: list[tuple[float, float, str, float]],
        width: float,
        height: float,
    ):
        from arafix.layout import Glyph, LayoutConfig, analyze_layout

        gs = [Glyph(y=y, x=x, text=t, size=s) for y, x, t, s in glyphs]
        mode = self.layout_mode if self.layout_mode in (
            "auto", "linear", "columns", "full"
        ) else "auto"
        return analyze_layout(
            gs,
            page_width=width,
            page_height=height,
            config=LayoutConfig(),
            mode=mode,  # type: ignore[arg-type]
        )

    def pages(self, path: str) -> Iterator[RawPage]:
        doc = self._open(path)
        try:
            for i, page in enumerate(doc, start=1):
                rect = page.rect
                width, height = float(rect.width), float(rect.height)
                fonts: list[str] = []
                with contextlib.suppress(Exception):
                    fonts = sorted({f[3] for f in page.get_fonts(full=True)})
                has_images = bool(page.get_images(full=True))

                if self.bidi == "geometry":
                    glyphs = self._extract_glyphs(page)
                    layout = self._build_layout(glyphs, width, height)
                    text = layout.plain_text if layout else self._geometric_text_from_glyphs(glyphs)
                    yield RawPage(
                        number=i,
                        text=text,
                        fonts=fonts,
                        has_images=has_images,
                        width=width,
                        height=height,
                        glyphs=glyphs,
                        layout=layout,
                    )
                else:
                    text = page.get_text("text", sort=self.sort)
                    yield RawPage(
                        number=i,
                        text=text,
                        fonts=fonts,
                        has_images=has_images,
                        width=width,
                        height=height,
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
