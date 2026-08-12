"""
الدرجة البنيوية — أعمدة وجداول وترويسات من هندسة الجليفات.

المحرّك يستخرج الجليفات؛ هذا الملف **يرتّبها قراءةً** لا علاجاً عربياً.
العلاج يبقى لـ ``repair_text`` / ``repair_blocks`` على كل كتلة.

قرارات عربية مقصودة:

  * ترتيب الأعمدة **يميناً←يساراً** (افتراضيّ) — عمود الجريدة الأيمن أولاً.
  * التقسيم **بالفجوة الأفقية (gutter)** على الجليفات لا على مراكز الأسطر:
    فالأسطر المتوازية في عمودين كانت تُدمَج سطراً واحداً فيُظنّ جدولًا.
  * الترويسة/التذييل يُفصلان عن الجسد.
  * الجداول: خلايا مستقلة بعد عزل الأعمدة (لا تخلط عموداً بجدول).
  * صفحة عمودٍ واحد = مسار خطّيّ مطابقٌ لما قبل 0.8.0.

لا تبعيّات — يُختبر بجليفات اصطناعية.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Literal

from .types import TextBlock

__all__ = [
    "Glyph",
    "LayoutLine",
    "LayoutColumn",
    "LayoutTable",
    "PageLayout",
    "LayoutConfig",
    "cluster_to_lines",
    "analyze_layout",
    "glyphs_from_triples",
    "analyze_layout_simple_linear",
    "join_glyphs_preserving_ltr",
]


ReadingOrder = Literal["rtl", "ltr"]
LayoutMode = Literal["auto", "linear", "columns", "full"]


@dataclass
class Glyph:
    """جليف واحد — y خط الأساس، x أصل الرسم."""

    y: float
    x: float
    text: str
    size: float = 10.0
    #: ترتيب التيار (seqno) — يُستعمل لإعادة ترتيب جزر LTR بعد الفرز بـ x.
    seq: int = 0
    #: رسم الجليف الأصلي، إن وفره المستخرج (x0, y0, x1, y1).
    bbox: tuple[float, float, float, float] | None = None


def _glyph_is_ltr_unit(text: str) -> bool:
    """LTR letter/digit or LTR-internal punctuation (hyphen, slash, …)."""
    if not text:
        return False
    ch = text[0]
    o = ord(ch)
    if ch.isdigit() or ("A" <= ch <= "Z") or ("a" <= ch <= "z"):
        return True
    if 0x0660 <= o <= 0x0669 or 0x06F0 <= o <= 0x06F9:  # Arabic-Indic digits
        return True
    if 0x00C0 <= o <= 0x024F:  # Latin extended
        return True
    return ch in "/\\-.,:+%°'\u2019_\u2013\u2014"


def _glyph_is_ltr_space(text: str) -> bool:
    return bool(text) and text.isspace()


def _space_threshold(
    ordered: list[Glyph],
    *,
    space_mode: str,
    space_k: float,
    space_percentile: float,
    space_min_factor: float,
    space_max_factor: float,
) -> float:
    """
    Per-line gap threshold for inserting word spaces.

    Modes (calibrated on *بصمة الإبهام الحمراء* gold pages, Safahat):

    * ``percentile`` (default): threshold = q-th gap of the line, clamped
      to [min_factor, max_factor] × median glyph size. Best CER/WER tradeoff
      on the book (q≈0.78 ≈ gold space count).
    * ``mad``: median + k·MAD (older, more conservative).
    """
    if len(ordered) < 2:
        return float("inf")
    gaps = [ordered[i].x - ordered[i - 1].x for i in range(1, len(ordered))]
    sizes = [g.size for g in ordered if g.size > 0]
    med_sz = statistics.median(sizes) if sizes else 10.0
    if space_mode == "mad":
        med_gap = statistics.median(gaps)
        mad = statistics.median([abs(g - med_gap) for g in gaps]) or (med_sz * 0.1)
        th = med_gap + space_k * mad
        th = max(th, med_sz * space_min_factor)
        th = min(th, med_sz * space_max_factor)
    else:
        # percentile of this line's gaps — do not cap with max_factor, or
        # synthetic lines with letter pitch ≈ size insert spaces mid-word
        # (``ذيل`` → ``ذ ي ل``). Floor only.
        sg = sorted(gaps)
        q = min(1.0, max(0.0, space_percentile))
        idx = min(len(sg) - 1, max(0, int(round(q * (len(sg) - 1)))))
        th = sg[idx]
        th = max(th, med_sz * space_min_factor)
    return th


def join_glyphs_preserving_ltr(
    glyphs: list[Glyph],
    *,
    insert_spaces: bool = True,
    space_mode: str = "percentile",
    space_percentile: float = 0.72,
    space_k: float = 1.5,
    space_min_factor: float = 0.42,
    space_max_factor: float = 1.05,
) -> str:
    """
    Build line text: sort by x (visual), re-order each LTR island by stream
    ``seq`` (dates like ``13-7``), and optionally insert spaces from geometry.

    **Spaces:** many Arabic book PDFs encode no U+0020 between words; only
    glyph advances differ. Threshold is adaptive per line (see
    ``_space_threshold``). Evidence: Safahat *thumb_red* gold loop.
    """
    if not glyphs:
        return ""
    ordered = sorted(glyphs, key=lambda g: g.x)

    # Segment into LTR islands (seq-reordered) or single non-LTR glyphs.
    token_texts: list[str] = []
    token_firsts: list[Glyph] = []
    token_lasts: list[Glyph] = []
    i = 0
    n = len(ordered)
    while i < n:
        g = ordered[i]
        if _glyph_is_ltr_unit(g.text):
            j = i + 1
            while j < n:
                t = ordered[j].text
                if _glyph_is_ltr_unit(t):
                    j += 1
                    continue
                # spaces between LTR tokens belong to the island
                if _glyph_is_ltr_space(t) and j + 1 < n and _glyph_is_ltr_unit(
                    ordered[j + 1].text
                ):
                    j += 1
                    continue
                break
            run = ordered[i:j]
            if any(g.seq for g in run):
                run = sorted(run, key=lambda g: g.seq)
            token_firsts.append(run[0])
            token_lasts.append(run[-1])
            token_texts.append("".join(g.text for g in run))
            i = j
        else:
            token_firsts.append(g)
            token_lasts.append(g)
            token_texts.append(g.text)
            i += 1

    # Whitespace glyphs are stronger evidence than coordinate gaps. In
    # shaped Arabic fonts the origin-to-origin advance varies substantially
    # by glyph, so inferring *additional* spaces on a line that already
    # carries explicit PDF spaces fragments valid words (دراسة → درا سة).
    # Keep geometry inference for the genuinely space-less extraction case.
    has_explicit_space = any(_glyph_is_ltr_space(g.text) for g in ordered)
    if not insert_spaces or has_explicit_space or len(token_texts) <= 1:
        return "".join(token_texts)

    th = _space_threshold(
        ordered,
        space_mode=space_mode,
        space_k=space_k,
        space_percentile=space_percentile,
        space_min_factor=space_min_factor,
        space_max_factor=space_max_factor,
    )
    parts: list[str] = []
    for ti in range(len(token_texts)):
        if ti > 0:
            prev_last = token_lasts[ti - 1]
            cur_first = token_firsts[ti]
            gap = cur_first.x - prev_last.x
            prev_t = prev_last.text
            cur_t = cur_first.text
            if (
                gap > th
                and prev_t
                and cur_t
                and not prev_t[-1].isspace()
                and not cur_t[0].isspace()
            ):
                parts.append(" ")
        parts.append(token_texts[ti])
    return "".join(parts)


@dataclass
class LayoutLine:
    y: float
    glyphs: list[Glyph]
    role: str = "body"  # body | header | footer
    column_index: int | None = None
    #: Copied from LayoutConfig when clustering (word-space geometry).
    insert_spaces: bool = True
    space_mode: str = "percentile"
    space_percentile: float = 0.72
    space_k: float = 1.5
    space_min_factor: float = 0.42
    space_max_factor: float = 1.05

    @property
    def text(self) -> str:
        return join_glyphs_preserving_ltr(
            self.glyphs,
            insert_spaces=self.insert_spaces,
            space_mode=self.space_mode,
            space_percentile=self.space_percentile,
            space_k=self.space_k,
            space_min_factor=self.space_min_factor,
            space_max_factor=self.space_max_factor,
        )

    @property
    def x0(self) -> float:
        return min(g.x for g in self.glyphs) if self.glyphs else 0.0

    @property
    def x1(self) -> float:
        if not self.glyphs:
            return 0.0
        size = self.glyphs[0].size
        return max(g.x for g in self.glyphs) + size * 0.5

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        size = self.glyphs[0].size if self.glyphs else 10.0
        return (self.x0, self.y - size, self.x1, self.y + size * 0.3)

    @property
    def spatial_bbox(self) -> tuple[float, float, float, float]:
        """Use exact paint bboxes when available, without changing layout logic."""
        exact = [g.bbox for g in self.glyphs if g.bbox is not None]
        if not exact:
            return self.bbox
        return (
            min(box[0] for box in exact),
            min(box[1] for box in exact),
            max(box[2] for box in exact),
            max(box[3] for box in exact),
        )


@dataclass
class LayoutColumn:
    index: int  # ترتيب القراءة (0 = يُقرأ أولاً)
    x0: float
    x1: float
    lines: list[LayoutLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)


@dataclass
class LayoutTable:
    rows: list[list[str]]
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    n_cols: int = 0
    cell_bboxes: list[list[tuple[float, float, float, float]]] = field(default_factory=list)

    def to_blocks(self, page: int = 0, table_id: int = 0) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        for i, row in enumerate(self.rows):
            for j, cell in enumerate(row):
                blocks.append(
                    TextBlock(
                        text=cell,
                        id=f"p{page}t{table_id}r{i}c{j}",
                        role="cell",
                        bbox=(
                            self.cell_bboxes[i][j]
                            if i < len(self.cell_bboxes) and j < len(self.cell_bboxes[i])
                            else self.bbox
                        ),
                        meta={"row": i, "col": j, "table": table_id, "page": page},
                    )
                )
        return blocks


@dataclass
class LayoutConfig:
    line_tolerance_factor: float = 0.5
    #: فجوة أفقية تُعدّ «ميزاباً» بين عمودين (× عرض الصفحة).
    gutter_ratio: float = 0.06
    #: الحد الأدنى لعرض الميزاب بالنقاط.
    min_gutter_pt: float = 18.0
    #: نسبة الجليفات الأدنى على كل جانب من الميزاب.
    min_side_fraction: float = 0.15
    header_band: float = 0.08
    footer_band: float = 0.08
    reading_order: ReadingOrder = "rtl"
    detect_tables: bool = True
    word_gap_factor: float = 2.2
    min_table_cols: int = 2
    min_table_rows: int = 3
    #: لا تُحسب جدولاً إن غطّت الخلايا أكثر من هذه النسبة من عرض العمود
    #: (نصٌّ متدفّق لا شبكة).
    max_table_cell_width_ratio: float = 0.45

    #: Insert U+0020 between glyphs from geometry when the PDF omits spaces.
    #: Calibrated on *بصمة الإبهام الحمراء* (Safahat) gold loop — not AI text.
    insert_glyph_spaces: bool = True
    #: ``percentile`` (default, best on thumb_red) or ``mad`` (conservative).
    glyph_space_mode: str = "percentile"
    #: Line-gap quantile when mode=percentile (0.72 ≈ gold WER/CER tradeoff).
    glyph_space_percentile: float = 0.72
    #: Used when mode=mad: median + k·MAD.
    glyph_space_k: float = 1.5
    glyph_space_min_factor: float = 0.42
    glyph_space_max_factor: float = 1.05


@dataclass
class PageLayout:
    width: float
    height: float
    lines: list[LayoutLine] = field(default_factory=list)
    columns: list[LayoutColumn] = field(default_factory=list)
    tables: list[LayoutTable] = field(default_factory=list)
    headers: list[LayoutLine] = field(default_factory=list)
    footers: list[LayoutLine] = field(default_factory=list)
    n_columns: int = 1
    mode_used: str = "linear"
    notes: list[str] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        parts: list[str] = []
        if self.headers:
            parts.append("\n".join(ln.text for ln in self.headers))
        if self.columns:
            col_texts = [c.text for c in self.columns if c.text.strip()]
            parts.append("\n\n".join(col_texts))
        if self.tables:
            for table in self.tables:
                md = table_to_markdown(table.rows)
                if md:
                    parts.append(md)
        if self.footers:
            parts.append("\n".join(ln.text for ln in self.footers))
        return "\n\n".join(p for p in parts if p.strip())

    def to_blocks(self, page_number: int = 1) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        for i, ln in enumerate(self.headers):
            blocks.append(
                TextBlock(
                    text=ln.text,
                    id=f"p{page_number}h{i}",
                    role="header",
                    bbox=ln.bbox,
                )
            )
        for col in self.columns:
            for i, ln in enumerate(col.lines):
                blocks.append(
                    TextBlock(
                        text=ln.text,
                        id=f"p{page_number}c{col.index}l{i}",
                        role="line",
                        bbox=ln.bbox,
                        meta={"column": col.index},
                    )
                )
        for ti, table in enumerate(self.tables):
            blocks.extend(table.to_blocks(page=page_number, table_id=ti))
        for i, ln in enumerate(self.footers):
            blocks.append(
                TextBlock(
                    text=ln.text,
                    id=f"p{page_number}f{i}",
                    role="footer",
                    bbox=ln.bbox,
                )
            )
        return blocks

    def reassemble_from_blocks(
        self, texts_by_id: dict[str, str], page_number: int = 1
    ) -> str:
        def get(bid: str, fallback: str) -> str:
            return texts_by_id.get(bid, fallback)

        parts: list[str] = []
        h = [get(f"p{page_number}h{i}", ln.text) for i, ln in enumerate(self.headers)]
        if any(x.strip() for x in h):
            parts.append("\n".join(h))

        col_parts: list[str] = []
        for col in self.columns:
            lines = [
                get(f"p{page_number}c{col.index}l{i}", ln.text)
                for i, ln in enumerate(col.lines)
            ]
            col_parts.append("\n".join(lines))
        if col_parts:
            parts.append("\n\n".join(col_parts))

        for ti, table in enumerate(self.tables):
            grid = [
                [
                    get(f"p{page_number}t{ti}r{i}c{j}", cell)
                    for j, cell in enumerate(row)
                ]
                for i, row in enumerate(table.rows)
            ]
            md = table_to_markdown(grid)
            if md:
                parts.append(md)

        f = [get(f"p{page_number}f{i}", ln.text) for i, ln in enumerate(self.footers)]
        if any(x.strip() for x in f):
            parts.append("\n".join(f))

        return "\n\n".join(p for p in parts if p.strip())


def table_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    n = max(len(r) for r in rows)
    norm = [list(r) + [""] * (n - len(r)) for r in rows]

    def esc(c: str) -> str:
        return c.replace("|", "\\|")

    lines = ["| " + " | ".join(esc(c) for c in norm[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(n)) + " |")
    for row in norm[1:]:
        lines.append("| " + " | ".join(esc(c) for c in row) + " |")
    return "\n".join(lines)


def glyphs_from_triples(
    triples: list[tuple[float, float, str] | list],
    size: float = 10.0,
) -> list[Glyph]:
    out: list[Glyph] = []
    for t in triples:
        out.append(Glyph(y=float(t[0]), x=float(t[1]), text=str(t[2]), size=size))
    return out


def cluster_to_lines(
    glyphs: list[Glyph],
    *,
    tolerance: float | None = None,
    config: LayoutConfig | None = None,
) -> list[LayoutLine]:
    if not glyphs:
        return []

    cfg = config or LayoutConfig()
    size_hint = statistics.median([g.size for g in glyphs]) if glyphs else 10.0
    tol = tolerance if tolerance is not None else max(size_hint * 0.5, 1.0)

    ordered = sorted(glyphs, key=lambda g: g.y)
    rows: list[list[Glyph]] = [[ordered[0]]]
    for g in ordered[1:]:
        if abs(g.y - rows[-1][0].y) <= tol:
            rows[-1].append(g)
        else:
            rows.append([g])

    lines: list[LayoutLine] = []
    for row in rows:
        row_sorted = sorted(row, key=lambda g: g.x)
        y = statistics.median([g.y for g in row_sorted])
        lines.append(
            LayoutLine(
                y=y,
                glyphs=row_sorted,
                insert_spaces=cfg.insert_glyph_spaces,
                space_mode=cfg.glyph_space_mode,
                space_percentile=cfg.glyph_space_percentile,
                space_k=cfg.glyph_space_k,
                space_min_factor=cfg.glyph_space_min_factor,
                space_max_factor=cfg.glyph_space_max_factor,
            )
        )
    return lines


def _find_gutters(
    glyphs: list[Glyph],
    page_width: float,
    cfg: LayoutConfig,
) -> list[float]:
    """
    يجد فجوات أفقية (ميازب) تفصل أعمدة.

    الفكرة: رتّب مواضع x الفريدة، وابحث عن قفزات كبيرة لا يمرّ فيها
    جليف، ويوجد محتوىٌ معتبر يميناً ويساراً.
    """
    if len(glyphs) < 8 or page_width <= 0:
        return []

    xs = sorted({round(g.x, 1) for g in glyphs})
    if len(xs) < 4:
        return []

    min_gap = max(page_width * cfg.gutter_ratio, cfg.min_gutter_pt)
    candidates: list[tuple[float, float]] = []  # (gap, mid_x)

    for i in range(len(xs) - 1):
        gap = xs[i + 1] - xs[i]
        if gap >= min_gap:
            mid = (xs[i] + xs[i + 1]) / 2
            left_n = sum(1 for g in glyphs if g.x < mid)
            right_n = sum(1 for g in glyphs if g.x >= mid)
            n = len(glyphs)
            if left_n / n >= cfg.min_side_fraction and right_n / n >= cfg.min_side_fraction:
                # هل يمتد المحتوى عمودياً على الجانبين؟
                left_ys = [g.y for g in glyphs if g.x < mid]
                right_ys = [g.y for g in glyphs if g.x >= mid]
                if not left_ys or not right_ys:
                    continue
                left_span = max(left_ys) - min(left_ys)
                right_span = max(right_ys) - min(right_ys)
                page_span = max(g.y for g in glyphs) - min(g.y for g in glyphs) or 1.0
                if left_span > page_span * 0.25 and right_span > page_span * 0.25:
                    candidates.append((gap, mid))

    if not candidates:
        return []

    # كل ميزاب مؤهَّل يحدّ عموداً حقيقياً. اختيار أكبر فجوة واحدة فقط
    # يدمج العمودين الباقيين في صفحة ثلاثية الأعمدة، رغم أن لكل فجوة
    # الشواهد العمودية ونِسَب المحتوى نفسها. نعيدها مرتبة مكانياً، وهو
    # الترتيب الذي تتوقعه _split_glyphs_by_gutters.
    return sorted(mid for _, mid in candidates)


def _split_glyphs_by_gutters(
    glyphs: list[Glyph], gutters: list[float]
) -> list[list[Glyph]]:
    if not gutters:
        return [glyphs]
    bounds = sorted(gutters)
    buckets: list[list[Glyph]] = [[] for _ in range(len(bounds) + 1)]
    for g in glyphs:
        placed = False
        for i, cut in enumerate(bounds):
            if g.x < cut:
                buckets[i].append(g)
                placed = True
                break
        if not placed:
            buckets[-1].append(g)
    return [b for b in buckets if b]


def _band_filter_glyphs(
    glyphs: list[Glyph],
    page_height: float,
    cfg: LayoutConfig,
) -> tuple[list[Glyph], list[Glyph], list[Glyph]]:
    if page_height <= 0:
        return [], glyphs, []
    top = page_height * cfg.header_band
    bot = page_height * (1.0 - cfg.footer_band)
    headers, body, footers = [], [], []
    for g in glyphs:
        if g.y <= top:
            headers.append(g)
        elif g.y >= bot:
            footers.append(g)
        else:
            body.append(g)
    return headers, body, footers


def _split_line_glyphs_into_cells(
    line: LayoutLine, cfg: LayoutConfig
) -> list[list[Glyph]]:
    if not line.glyphs:
        return []
    gs = sorted(line.glyphs, key=lambda g: g.x)
    size = statistics.median([g.size for g in gs]) or 10.0
    gap_th = size * cfg.word_gap_factor

    cells: list[list[Glyph]] = [[gs[0]]]
    for g in gs[1:]:
        prev = cells[-1][-1]
        if g.x - prev.x > gap_th:
            cells.append([g])
        else:
            cells[-1].append(g)
    return cells


def _split_line_into_cells(line: LayoutLine, cfg: LayoutConfig) -> list[str]:
    return ["".join(g.text for g in cell) for cell in _split_line_glyphs_into_cells(line, cfg)]


def _detect_tables_in_lines(
    lines: list[LayoutLine],
    col_width: float,
    cfg: LayoutConfig,
) -> tuple[list[LayoutLine], list[LayoutTable]]:
    if not cfg.detect_tables or len(lines) < cfg.min_table_rows:
        return lines, []

    cell_rows = [_split_line_into_cells(ln, cfg) for ln in lines]
    has_spatial_bboxes = any(
        g.bbox is not None for line in lines for g in line.glyphs
    )
    cell_glyph_rows = (
        [_split_line_glyphs_into_cells(ln, cfg) for ln in lines]
        if has_spatial_bboxes
        else []
    )
    tables: list[LayoutTable] = []
    consumed: set[int] = set()
    i = 0
    while i < len(lines):
        if len(cell_rows[i]) < cfg.min_table_cols:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and len(cell_rows[j]) >= cfg.min_table_cols:
            j += 1
        if j - i >= cfg.min_table_rows:
            counts = [len(cell_rows[k]) for k in range(i, j)]
            try:
                n_cols = statistics.mode(counts)
            except statistics.StatisticsError:
                n_cols = int(statistics.median(counts))

            rows_data: list[list[str]] = []
            cell_bboxes: list[list[tuple[float, float, float, float]]] = []
            for k in range(i, j):
                row = cell_rows[k][:n_cols]
                row = row + [""] * (n_cols - len(row))
                if cell_glyph_rows:
                    boxes: list[tuple[float, float, float, float]] = []
                    for cell in cell_glyph_rows[k][:n_cols]:
                        if not cell:
                            boxes.append(lines[k].bbox)
                            continue
                        exact = [g.bbox for g in cell if g.bbox is not None]
                        if exact:
                            boxes.append(
                                (
                                    min(box[0] for box in exact),
                                    min(box[1] for box in exact),
                                    max(box[2] for box in exact),
                                    max(box[3] for box in exact),
                                )
                            )
                        else:
                            boxes.append(
                                (
                                    min(g.x for g in cell),
                                    min(g.y - g.size for g in cell),
                                    max(g.x + g.size * 0.5 for g in cell),
                                    max(g.y + g.size * 0.3 for g in cell),
                                )
                            )
                    if len(boxes) < n_cols:
                        boxes.extend([lines[k].bbox] * (n_cols - len(boxes)))
                    cell_bboxes.append(boxes[:n_cols])
                rows_data.append(row)
                consumed.add(k)

            y0 = lines[i].bbox[1]
            y1 = lines[j - 1].bbox[3]
            x0 = min(lines[k].x0 for k in range(i, j))
            x1 = max(lines[k].x1 for k in range(i, j))
            tables.append(
                LayoutTable(
                    rows=rows_data,
                    bbox=(x0, y0, x1, y1),
                    n_cols=n_cols,
                    cell_bboxes=cell_bboxes,
                )
            )
            i = j
        else:
            i += 1

    remaining = [ln for idx, ln in enumerate(lines) if idx not in consumed]
    return remaining, tables


def analyze_layout(
    glyphs: list[Glyph],
    *,
    page_width: float,
    page_height: float,
    config: LayoutConfig | None = None,
    mode: LayoutMode = "auto",
) -> PageLayout:
    """
    يحلّل جليفات صفحة → ترويسة / أعمدة (RTL) / جداول / تذييل.
    """
    cfg = config or LayoutConfig()
    layout = PageLayout(width=page_width, height=page_height)

    if not glyphs:
        layout.notes.append("لا جليفات")
        return layout

    if mode == "linear":
        lines = cluster_to_lines(glyphs, config=cfg)
        layout.lines = lines
        layout.mode_used = "linear"
        layout.n_columns = 1
        if lines:
            layout.columns = [
                LayoutColumn(
                    index=0,
                    x0=min(ln.x0 for ln in lines),
                    x1=max(ln.x1 for ln in lines),
                    lines=lines,
                )
            ]
        return layout

    # 1) عزل الترويسة/التذييل على مستوى الجليف
    h_glyphs, body_glyphs, f_glyphs = _band_filter_glyphs(glyphs, page_height, cfg)
    layout.headers = cluster_to_lines(h_glyphs, config=cfg)
    for ln in layout.headers:
        ln.role = "header"
    layout.footers = cluster_to_lines(f_glyphs, config=cfg)
    for ln in layout.footers:
        ln.role = "footer"

    if not body_glyphs:
        body_glyphs = list(glyphs)
        layout.headers = []
        layout.footers = []

    # الوضع full يطلب الجداول صراحةً. افحص الشبكة قبل الميازيب، إذ إن
    # أعمدة الجدول المنتظمة تبدو هندسياً كفواصل أعمدة الصفحة. أمّا وضع
    # columns فيبقى صريحاً: يستعمله المستدعي حين يعرف أن الصفحة أعمدة.
    if cfg.detect_tables and mode == "full":
        table_lines = cluster_to_lines(body_glyphs, config=cfg)
        remaining, tables = _detect_tables_in_lines(table_lines, page_width, cfg)
        if tables:
            layout.tables = tables
            layout.lines = layout.headers + remaining + layout.footers
            for ln in remaining:
                ln.role = "body"
                ln.column_index = 0
            if remaining:
                layout.columns = [
                    LayoutColumn(
                        index=0,
                        x0=min(ln.x0 for ln in remaining),
                        x1=max(ln.x1 for ln in remaining),
                        lines=remaining,
                    )
                ]
            layout.n_columns = 1
            layout.mode_used = "full"
            layout.notes.append(f"{len(tables)} جدول(اً) قبل فصل الأعمدة")
            return layout

    # 2) ميازب الأعمدة
    want_cols = mode in ("auto", "columns", "full")
    gutters = _find_gutters(body_glyphs, page_width, cfg) if want_cols else []
    glyph_groups = _split_glyphs_by_gutters(body_glyphs, gutters)

    if len(glyph_groups) <= 1:
        layout.mode_used = "linear" if mode == "auto" else mode
        layout.n_columns = 1
        lines = cluster_to_lines(body_glyphs, config=cfg)
        layout.lines = layout.headers + lines + layout.footers

        # جداول داخل العمود الواحد
        if cfg.detect_tables and mode in ("auto", "full"):
            rest, tables = _detect_tables_in_lines(lines, page_width, cfg)
            layout.tables = tables
            lines = rest
            if tables:
                layout.notes.append(f"{len(tables)} جدول(اً)")

        for ln in lines:
            ln.role = "body"
            ln.column_index = 0
        if lines:
            layout.columns = [
                LayoutColumn(
                    index=0,
                    x0=min(ln.x0 for ln in lines),
                    x1=max(ln.x1 for ln in lines),
                    lines=lines,
                )
            ]
        if layout.headers or layout.footers:
            layout.notes.append("عُزلت ترويسة/تذييل")
        return layout

    # 3) أعمدة متعددة — هندسياً يسار→يمين ثم نرتّب القراءة
    layout.mode_used = "columns"
    geo_groups = glyph_groups  # left-to-right by gutter split
    read_groups = (
        list(reversed(geo_groups)) if cfg.reading_order == "rtl" else list(geo_groups)
    )

    cols: list[LayoutColumn] = []
    all_body_lines: list[LayoutLine] = []
    for idx, group in enumerate(read_groups):
        lines = cluster_to_lines(group, config=cfg)
        # جداول داخل العمود
        if cfg.detect_tables and mode in ("auto", "full"):
            col_w = (max(g.x for g in group) - min(g.x for g in group)) or page_width
            lines, tables = _detect_tables_in_lines(lines, col_w, cfg)
            layout.tables.extend(tables)

        for ln in lines:
            ln.role = "body"
            ln.column_index = idx
        all_body_lines.extend(lines)
        cols.append(
            LayoutColumn(
                index=idx,
                x0=min(g.x for g in group),
                x1=max(g.x for g in group),
                lines=lines,
            )
        )

    layout.columns = cols
    layout.n_columns = len(cols)
    layout.lines = layout.headers + all_body_lines + layout.footers
    layout.notes.append(
        f"{layout.n_columns} عموداً · قراءة {cfg.reading_order}"
    )
    if layout.headers or layout.footers:
        layout.notes.append("عُزلت ترويسة/تذييل")
    if layout.tables:
        layout.notes.append(f"{len(layout.tables)} جدول(اً)")

    return layout


def analyze_layout_simple_linear(glyphs: list[Glyph]) -> str:
    return "\n".join(ln.text for ln in cluster_to_lines(glyphs))
