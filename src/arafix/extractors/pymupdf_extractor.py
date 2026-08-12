"""
محرّك PyMuPDF — الافتراضي.

اخترناه افتراضياً لثلاثة أسباب: أسرع محرّكات بايثون، ويكشف الخطوط
المضمَّنة (وهو شرط الدرجة ٣)، ويُخرج بنيةً غنية فيها إحداثيات كل جليف.
"""

from __future__ import annotations

import contextlib
import unicodedata
from collections.abc import Iterator

from ..noise import GeometricNoiseConfig, GeometricNoiseFilter
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
        geometric_noise: GeometricNoiseConfig | None = None,
        preserve_spatial_bboxes: bool = False,
    ) -> None:
        """
        :param sort: يرتّب الكتل بإحداثياتها قبل الإخراج (مُهلِك للعربية غالباً).
        :param bidi: ``geometry`` (افتراضي) أو ``mupdf``.
        :param layout_mode: يُمرَّر لتحليل البنية — انظر ``arafix.layout``.
        """
        self.sort = sort
        self.bidi = bidi
        self.layout_mode = layout_mode
        self.preserve_spatial_bboxes = preserve_spatial_bboxes
        self.noise_filter = (
            GeometricNoiseFilter(geometric_noise)
            if geometric_noise is not None
            else None
        )

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

    @staticmethod
    def _is_markable_base(text: str) -> bool:
        """Letter base that may carry tashkeel — not space, punct, or digits."""
        if not text:
            return False
        return unicodedata.category(text[0]).startswith("L")

    @staticmethod
    def _as_combining_marks(ch: str) -> str | None:
        """
        Expand pure-diacritic presentation forms to Mn marks.

        Word→PDF often emits shadda+vowel *ligatures* (U+FC5E–FC63, U+FCF2–FCF4)
        and spacing harakat (U+FE70–FE7F) as category **Lo**. Treating them as
        letter bases creates phantom letters and shifts real attachment
        (``رُوِّج`` → ``رُِّوج``). Only expansions that are *entirely* Mn are
        treated as marks; lam-alef and letter ligatures stay bases.
        """
        if unicodedata.category(ch) == "Mn":
            return ch
        from arafix.unicode_tables import DEFERRED_PF_TO_BASE, SPACING_MARK_PF_TO_BASE

        if ch in SPACING_MARK_PF_TO_BASE:
            return SPACING_MARK_PF_TO_BASE[ch]
        exp = DEFERRED_PF_TO_BASE.get(ch)
        if exp and all(unicodedata.category(c) == "Mn" for c in exp):
            return exp
        return None

    @staticmethod
    def _attach_mark(base_text: str, mark: str) -> str:
        """Append *mark* to a base cluster with shadda-before-vowel order."""
        from arafix.order import order_combining_marks

        if not base_text:
            return mark
        base, existing = base_text[0], base_text[1:]
        return base + order_combining_marks(existing + mark)

    def _extract_glyphs(self, page, spans=None) -> list[tuple[float, float, str, float, int]]:
        """
        Read the paint stream: ``(y, x, text, size, seq)``.

        **P0 — nearest-base Mn attachment** (geometry, not stream-previous).

        **P2a — cluster-aware mark attachment:**

        1. Collect letter bases and diacritics separately. Diacritics include
           true Mn **and** pure-mark presentation forms (shadda+vowel
           ligatures, spacing harakat PF).
        2. Bind each mark to the nearest letter base on the same line.
        3. **Consecutive stack stickiness:** if a mark is within
           ``Δx < 0.45·size`` of the previous mark's position, prefer the
           same base (vertical / ligature stacks share one carrier).
        4. Canonicalize mark order on the base (shadda before vowels).
        5. Preserve stream ``seq`` for LTR island repair in layout.

        Never glue marks onto whitespace or punctuation.
        """
        bases: list[list] = []  # mutable [y, x, text, size, seq, glyph_id, font, bbox]
        # (y, x, ch, size) — size carried for stack thresholds
        marks: list[tuple[float, float, str, float]] = []
        size_hint = 10.0
        seq = 0
        traces = spans if spans is not None else page.get_texttrace()
        for span in sorted(traces, key=lambda s: s.get("seqno", 0)):
            if span.get("type", 0) != 0:
                continue
            font = str(span.get("font") or "")
            size = float(span.get("size") or size_hint or 10.0)
            if size:
                size_hint = size
            for uni, glyph_id, origin, _bbox in span["chars"]:
                ch = chr(uni)
                y, x = float(origin[1]), float(origin[0])
                seq += 1
                mark_exp = self._as_combining_marks(ch)
                if mark_exp is not None:
                    # Ligature PF may expand to several Mn at the same origin.
                    for m in mark_exp:
                        marks.append((y, x, m, size))
                else:
                    base = [y, x, ch, size, seq, int(glyph_id), font]
                    if self.preserve_spatial_bboxes:
                        base.append(tuple(float(value) for value in _bbox[:4]))
                    bases.append(base)

        last_i: int | None = None
        last_mx: float | None = None
        last_my: float | None = None

        for my, mx, mch, _msz in marks:
            best_i: int | None = None
            best_d = float("inf")
            cands: list[tuple[float, int]] = []
            for i, b in enumerate(bases):
                if not self._is_markable_base(b[2]):
                    continue
                by, bx, _text, bsz = b[0], b[1], b[2], b[3]
                dy = abs(by - my)
                dx = abs(bx - mx)
                line_tol = max(bsz * 0.65, 3.0)
                dist = dx + (1000.0 * dy if dy > line_tol else 0.15 * dy)
                cands.append((dist, i))
                if dist < best_d:
                    best_d = dist
                    best_i = i

            # Sticky only for co-located marks (same origin: expanded ligature PF
            # or true vertical stack at identical paint position). Wider Δx
            # wrongly merges neighbouring letters' harakat.
            if (
                last_i is not None
                and last_mx is not None
                and last_my is not None
                and best_i is not None
                and abs(mx - last_mx) <= 0.75
                and abs(my - last_my) <= 0.75
            ):
                best_i = last_i

            if best_i is not None:
                bases[best_i][2] = self._attach_mark(bases[best_i][2], mch)
                last_i, last_mx, last_my = best_i, mx, my

        return [tuple(base) for base in bases]

    @staticmethod
    def _glyphs_to_layout_glyphs(glyphs: list[tuple]) -> list:
        from arafix.layout import Glyph

        out = []
        for g in glyphs:
            y, x, t, s = g[0], g[1], g[2], g[3]
            sq = int(g[4]) if len(g) > 4 else 0
            bbox = tuple(float(value) for value in g[7][:4]) if len(g) > 7 else None
            out.append(Glyph(y=y, x=x, text=t, size=s, seq=sq, bbox=bbox))
        return out

    def _geometric_text_from_glyphs(
        self, glyphs: list[tuple],
    ) -> str:
        from arafix.layout import analyze_layout_simple_linear

        return analyze_layout_simple_linear(self._glyphs_to_layout_glyphs(glyphs))

    def _build_layout(
        self,
        glyphs: list[tuple],
        width: float,
        height: float,
    ):
        from arafix.layout import LayoutConfig, analyze_layout

        gs = self._glyphs_to_layout_glyphs(glyphs)
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
            repeated_keys: set[tuple] = set()
            if (
                self.noise_filter is not None
                and self.bidi == "geometry"
                and self.noise_filter.config.remove_repeated_short_spans
            ):
                # Keep only compact fingerprints in the first pass; full spans
                # are loaded again page-by-page in the extraction pass.
                repeated_keys = self.noise_filter.repeated_keys(
                    page.get_texttrace() for page in doc
                )

            for i in range(len(doc)):
                page = doc.load_page(i)
                number = i + 1
                rect = page.rect
                width, height = float(rect.width), float(rect.height)
                fonts: list[str] = []
                with contextlib.suppress(Exception):
                    fonts = sorted({f[3] for f in page.get_fonts(full=True)})
                has_images = bool(page.get_images(full=True))

                if self.bidi == "geometry":
                    traces = page.get_texttrace()
                    noise_removed = 0
                    noise_reasons: dict[str, int] = {}
                    if self.noise_filter is not None:
                        traces, noise_removed, noise_reasons = self.noise_filter.filter_spans(
                            traces, repeated_keys
                        )
                    glyphs = self._extract_glyphs(page, traces)
                    layout = self._build_layout(glyphs, width, height)
                    text = layout.plain_text if layout else self._geometric_text_from_glyphs(glyphs)
                    yield RawPage(
                        number=number,
                        text=text,
                        fonts=fonts,
                        has_images=has_images,
                        width=width,
                        height=height,
                        glyphs=glyphs,
                        layout=layout,
                        noise_spans_removed=noise_removed,
                        noise_reasons=noise_reasons,
                    )
                else:
                    text = page.get_text("text", sort=self.sort)
                    yield RawPage(
                        number=number,
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
