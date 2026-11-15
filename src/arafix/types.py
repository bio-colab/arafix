"""
نماذج البيانات — العقد الثابت بين كل مراحل الأنبوب.

قاعدة معمارية واحدة تحكم هذا الملف: **لا مرحلة تُرجع نصاً عارياً.**
كل مرحلة تُرجع كائناً يحمل النص ومعه سبب ما فعلته ودرجة ثقتها فيه.
بهذا يبقى القرار للمستعمل لا للمكتبة، وتبقى المكتبة قابلة للتدقيق.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .audit import Patch, RepairAudit

__all__ = [
    "Defect",
    "Stage",
    "Evidence",
    "Diagnosis",
    "RepairResult",
    "PageResult",
    "DocumentResult",
    "TableResult",
    "TextBlock",
    "BlockResult",
    "BlocksResult",
    "as_blocks",
    "fix_table",
    "table_to_markdown",
    "RAGChunk",
    "set_repair_handlers",
]

_repair_text_handler: Any = None
_repair_blocks_handler: Any = None


def set_repair_handlers(text_fn: Any, blocks_fn: Any) -> None:
    global _repair_text_handler, _repair_blocks_handler
    _repair_text_handler = text_fn
    _repair_blocks_handler = blocks_fn


def _dispatch_repair_text(text: str, config: Any = None) -> Any:
    global _repair_text_handler
    if _repair_text_handler is None:
        import importlib
        import sys

        mod = sys.modules.get("arafix.pipeline") or importlib.import_module("arafix.pipeline")
        _repair_text_handler = mod.repair_text
    return _repair_text_handler(text, config)


def _dispatch_repair_blocks(blocks: list[TextBlock], config: Any = None) -> BlocksResult:
    global _repair_blocks_handler
    if _repair_blocks_handler is None:
        import importlib
        import sys

        mod = sys.modules.get("arafix.pipeline") or importlib.import_module("arafix.pipeline")
        _repair_blocks_handler = mod.repair_blocks
    return _repair_blocks_handler(blocks, config)


class Defect(str, Enum):
    """العلل التي تعرف هذه المكتبة تشخيصها. مغلقة عمداً وقابلة للتوسيع."""

    PRESENTATION_FORMS = "presentation_forms"   # حروف مطبوخة U+FB50–FEFF
    VISUAL_ORDER = "visual_order"               # النص مخزَّن معكوساً
    MOJIBAKE = "mojibake"                       # UTF-8 فُكّ بـ Latin-1
    LAM_ALEF_TRANSPOSED = "lam_alef_transposed" # «لا» صارت «ال» — رباطٌ فُكّ قبل العكس
    BROKEN_CMAP = "broken_cmap"                 # PUA / خرائط مفقودة
    TATWEEL_NOISE = "tatweel_noise"             # كشيدة زخرفية
    NO_TEXT_LAYER = "no_text_layer"             # صفحة ممسوحة ضوئياً
    NONE = "none"                               # سليم


class Stage(str, Enum):
    """درجات سلّم العلاج. كل درجة مستقلة وقابلة للتخطي منفردة."""

    HYGIENE = "hygiene"            # بوابة — NBSP/soft-hyphen قبل التشخيص
    DIAGNOSE = "diagnose"          # ٠ — لا تعالج قبل أن تعرف
    NORMALIZE = "normalize"        # ١ — تطبيع الأشكال الرسومية
    REORDER = "reorder"            # ٢ — إصلاح الاتجاه
    EXPAND_LIGATURES = "expand_ligatures"  # ١ب — فكّ الرباطات، بعد استقرار الترتيب
    REPAIR_LAM_ALEF = "repair_lam_alef"    # ترقيع عطبٍ أوقعته أداةٌ أخرى
    REPAIR_SPACING = "repair_spacing"      # طيّ/إدراج حدود كلمات ذات شاهد
    REPAIR_PDF_CONFUSIONS = "repair_pdf_confusions"  # امل/ري من كتب PDF منشورة
    CONTEXT = "context"          # معجم/عبارات الوثيقة — اختياري ومحافظ
    REBUILD_CMAP = "rebuild_cmap"  # ٣ — إعادة بناء الخريطة من الخط
    OCR = "ocr"                    # ٤ — آخر الدواء


@dataclass(frozen=True)
class Evidence:
    """
    شاهد واحد على وجود علّة.

    وجودها مقصود: الفرق بين أداةٍ تقول «النص معكوس» وأداةٍ تقول
    «النص معكوس لأن ٩٤٪ من التاءات المربوطة وقعت أول الكلمة»
    هو الفرق بين أداةٍ تُصدَّق وأداةٍ تُستعمل على عمى.
    """

    name: str
    value: float
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - عرض فقط
        return f"{self.name}={self.value:.3f} :: {self.detail}"


#: العلل التي يقوم شاهدُها على فحصٍ **حتميّ** — نطاقٍ أو اختبارٍ جبريّ.
#: لا دخل لحجم العيّنة بها: فحصُ نطاقٍ على خمسة محارف قاطعٌ كفحصه على
#: خمسة آلاف. ومن خفّض ثقتها لصغر العيّنة خلط الإحصاء بالحساب.
DETERMINISTIC_DEFECTS = frozenset({
    Defect.PRESENTATION_FORMS,
    Defect.BROKEN_CMAP,
    Defect.MOJIBAKE,
    Defect.TATWEEL_NOISE,
    Defect.NO_TEXT_LAYER,
    Defect.LAM_ALEF_TRANSPOSED,
})


@dataclass
class Diagnosis:
    """حصيلة الدرجة صفر: ماذا في هذا النص، وبأيّ ثقة."""

    defects: list[Defect] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    #: ثقةُ كل علّةٍ على حدة. الرقمُ الواحد يُخفي أن بعض شواهدنا قاطعة
    #: وبعضها ظنّيّ، فيظلم الأولى ويجمّل الثانية.
    defect_confidence: dict[Defect, float] = field(default_factory=dict)

    confidence: float = 0.0
    char_count: int = 0
    arabic_ratio: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)

    def has(self, defect: Defect) -> bool:
        return defect in self.defects

    def confidence_in(self, defect: Defect) -> float:
        """ثقةُ علّةٍ بعينها. أدقّ من `confidence` الجامع."""
        return self.defect_confidence.get(defect, 0.0)

    @property
    def healthy(self) -> bool:
        return not self.defects or self.defects == [Defect.NONE]

    def summary(self) -> str:
        if self.healthy:
            return "سليم"
        return "، ".join(d.value for d in self.defects)


@dataclass
class RepairResult:
    """حصيلة أنبوب الإصلاح على نصٍّ واحد."""

    text: str
    original: str
    diagnosis: Diagnosis
    stages_applied: list[Stage] = field(default_factory=list)
    confidence: float = 1.0
    notes: list[str] = field(default_factory=list)
    #: Optional provenance record. ``None`` keeps the historical fast path.
    audit: RepairAudit | None = None

    @property
    def changed(self) -> bool:
        return self.text != self.original

    @property
    def reversible_patch(self) -> Patch | None:
        """Return the hash-guarded patch when full auditing was requested."""
        return self.audit.patch if self.audit is not None else None

    def __str__(self) -> str:
        return self.text


@dataclass
class PageResult:
    """نتيجة صفحة واحدة من ملف PDF."""

    page_number: int
    repair: RepairResult
    fonts: list[str] = field(default_factory=list)
    #: تحليل بنيويّ (أعمدة/جداول/ترويسة) — إن فُعّل المسار البنيويّ.
    layout: Any = None
    #: كتل مُصلَحة مستقلة (سطور/خلايا) مع معرّفاتها.
    blocks: BlocksResult | None = None
    n_columns: int = 1
    #: أبعاد الصفحة بالنقاط، لاستخدامها في مخرجات الاستشهاد المكاني.
    width: float = 0.0
    height: float = 0.0
    #: جداول مُصلَحة: قائمة شبكات [صف][عمود].
    tables: list[list[list[str]]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.repair.text

    @property
    def headings(self) -> list[tuple[str, int]]:
        """
        العناوين المستخرجة من الصفحة مع درجاتها الهرمية: [(نص_العنوان, درجة_العنوان)].
        الدرجات: 1 = H1، 2 = H2، 3 = H3.
        """
        out: list[tuple[str, int]] = []
        if self.blocks is not None:
            for b in self.blocks.blocks:
                if b.block.role == "heading":
                    lvl = int(b.block.meta.get("heading_level", 1))
                    out.append((b.text.strip(), lvl))
        elif self.layout is not None:
            all_lines = [ln for col in getattr(self.layout, "columns", []) for ln in col.lines]
            rep_lines = [ln for ln in self.text.splitlines() if ln.strip()]
            use_rep = len(all_lines) == len(rep_lines)
            for idx, ln in enumerate(all_lines):
                if getattr(ln, "is_heading", False):
                    if use_rep:
                        repaired = rep_lines[idx].strip()
                    else:
                        repaired = _dispatch_repair_text(ln.text).text.strip()
                    out.append((repaired, getattr(ln, "heading_level", 1) or 1))
        return out

    @property
    def header_text(self) -> str:
        """نص ترويسات الصفحة المجمّعة."""
        if self.blocks is not None:
            parts = [b.text for b in self.blocks.blocks if b.block.role == "header"]
            return "\n".join(p.strip() for p in parts if p.strip())
        if self.layout is not None and getattr(self.layout, "headers", None):
            return "\n".join(
                _dispatch_repair_text(ln.text).text.strip()
                for ln in self.layout.headers
                if ln.text.strip()
            )
        return ""

    @property
    def footer_text(self) -> str:
        """نص تذييلات الصفحة المجمّعة (تشمل أرقام الصفحات)."""
        if self.blocks is not None:
            parts = [b.text for b in self.blocks.blocks if b.block.role == "footer"]
            return "\n".join(p.strip() for p in parts if p.strip())
        if self.layout is not None and getattr(self.layout, "footers", None):
            return "\n".join(
                _dispatch_repair_text(ln.text).text.strip()
                for ln in self.layout.footers
                if ln.text.strip()
            )
        return ""

    @property
    def body_text(self) -> str:
        """
        متن الصفحة الصافي باستبعاد الترويسات والتذييلات وأرقام الصفحات.
        """
        if self.blocks is not None:
            parts = [
                b.text
                for b in self.blocks.blocks
                if b.block.role not in ("header", "footer")
            ]
            return "\n".join(p.strip() for p in parts if p.strip())
        if self.layout is not None:
            has_headers = bool(getattr(self.layout, "headers", None))
            has_footers = bool(getattr(self.layout, "footers", None))
            if not has_headers and not has_footers:
                return self.text.strip()
            all_lines = [ln for col in getattr(self.layout, "columns", []) for ln in col.lines]
            rep_lines = [ln for ln in self.text.splitlines() if ln.strip()]
            if len(all_lines) == len(rep_lines):
                parts = [
                    rep_lines[i].strip()
                    for i, ln in enumerate(all_lines)
                    if ln.role not in ("header", "footer")
                ]
                return "\n".join(p for p in parts if p)
        return self.text.strip()

    @property
    def tables_rich(self) -> list[TableResult]:
        """قائمة كائنات الجداول ذات دوال التصدير الغنية."""
        out: list[TableResult] = []
        for idx, grid in enumerate(self.tables):
            bbox = None
            if self.layout and idx < len(getattr(self.layout, "tables", [])):
                bbox = self.layout.tables[idx].bbox
            out.append(TableResult(rows=grid, page=self.page_number, index=idx, bbox=bbox))
        return out

    def to_markdown(self, *, include_headers_footers: bool = False) -> str:
        """
        تصدير صفحة الـ PDF بصيغة Markdown قياسية وهيكلية.
        تترجم العناوين إلى (#, ##, ###) وتدمج الجداول بصيغة Markdown.
        """
        parts: list[str] = []
        if include_headers_footers and self.header_text:
            parts.append(f"> *{self.header_text}*")

        lines: list[tuple[str, str, int]] = []
        if self.blocks is not None:
            for b in self.blocks.blocks:
                if b.block.role in ("header", "footer") and not include_headers_footers:
                    continue
                lvl = int(b.block.meta.get("heading_level", 0) or 0)
                lines.append((b.text.strip(), b.block.role or "body", lvl))
        elif self.layout is not None:
            all_lines = [ln for col in getattr(self.layout, "columns", []) for ln in col.lines]
            rep_lines = [ln for ln in self.text.splitlines() if ln.strip()]
            use_rep = len(all_lines) == len(rep_lines)
            for idx, ln in enumerate(all_lines):
                if ln.role in ("header", "footer") and not include_headers_footers:
                    continue
                rep = (
                    rep_lines[idx].strip()
                    if use_rep
                    else _dispatch_repair_text(ln.text).text.strip()
                )
                if rep:
                    lines.append((rep, ln.role, ln.heading_level))

        p_buffer: list[str] = []

        def flush_p() -> None:
            if p_buffer:
                parts.append(" ".join(p_buffer))
                p_buffer.clear()

        for text, role, level in lines:
            if not text:
                flush_p()
                continue
            if role == "heading" or level > 0:
                flush_p()
                lvl = min(max(level or 1, 1), 6)
                parts.append(f"{'#' * lvl} {text}")
            elif role == "list_item":
                flush_p()
                item_text = text
                if not any(item_text.startswith(pfx) for pfx in ("- ", "* ", "• ")):
                    item_text = f"- {item_text}"
                parts.append(item_text)
            else:
                p_buffer.append(text)
                if text[-1:] in (".", "!", "؟"):
                    flush_p()

        flush_p()

        for table in self.tables_rich:
            md_tbl = table.to_markdown()
            if md_tbl:
                parts.append(md_tbl)

        if include_headers_footers and self.footer_text:
            parts.append(f"> *{self.footer_text}*")

        return "\n\n".join(p for p in parts if p.strip())

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True)
class RAGChunk:
    """A citation-ready chunk with page coordinates and structural ancestry."""

    id: str
    text: str
    page: int
    bbox: tuple[float, float, float, float]
    role: str = "paragraph"
    parent_context: tuple[str, ...] = ()
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "page": self.page,
            "bbox": [round(float(value), 3) for value in self.bbox],
            "role": self.role,
            "parent_context": list(self.parent_context),
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class DocumentResult:
    """نتيجة ملف كامل."""

    path: str
    pages: list[PageResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)

    @property
    def headings(self) -> list[tuple[str, int, int]]:
        """
        جميع عناوين المستند بالترتيب: [(نص_العنوان, درجة_العنوان, رقم_الصفحة)].
        """
        out: list[tuple[str, int, int]] = []
        for p in self.pages:
            for heading_text, lvl in p.headings:
                out.append((heading_text, lvl, p.page_number))
        return out

    def identify_running_headers_footers(self) -> tuple[set[str], set[str]]:
        """
        كشف الترويسات والتذييلات المتكررة عبر صفحات المستند.
        تُحدد النصوص التي تتكرر عبر صفحتين أو أكثر أو تطابق أنماط أرقام الصفحات.
        """
        import re
        from collections import Counter

        header_counts: Counter[str] = Counter()
        footer_counts: Counter[str] = Counter()

        page_num_pat = re.compile(
            r"^\s*(?:[pP]age\s*)?(?:[صص]\.?\s*)?[-–—]?\s*[0-9\u0660-\u0669]+\s*[-–—]?(?:\s*/\s*[0-9\u0660-\u0669]+)?\s*$"
        )

        for p in self.pages:
            h = p.header_text.strip()
            if h:
                for line in h.splitlines():
                    cl = line.strip()
                    if cl:
                        header_counts[cl] += 1
            f = p.footer_text.strip()
            if f:
                for line in f.splitlines():
                    cl = line.strip()
                    if cl:
                        footer_counts[cl] += 1

        running_headers = {text for text, count in header_counts.items() if count >= 2}
        running_footers = {
            text
            for text, count in footer_counts.items()
            if count >= 2 or page_num_pat.match(text)
        }
        return running_headers, running_footers

    @property
    def running_headers(self) -> list[str]:
        headers, _ = self.identify_running_headers_footers()
        return sorted(headers)

    @property
    def running_footers(self) -> list[str]:
        _, footers = self.identify_running_headers_footers()
        return sorted(footers)

    @property
    def body_text(self) -> str:
        """
        متن المستند كاملاً باستبعاد الترويسات والتذييلات المتكررة، مع ربط
        الفقرات المكسورة عبر حواف الصفحات برباط انسيابي سلس.
        """
        if not self.pages:
            return ""

        r_headers, r_footers = self.identify_running_headers_footers()
        terminal_punct = set(".,:;!?،؛؟.!؟")

        cleaned_pages: list[str] = []
        for p in self.pages:
            p_text = p.body_text
            lines = [
                ln.strip()
                for ln in p_text.splitlines()
                if ln.strip() and ln.strip() not in r_headers and ln.strip() not in r_footers
            ]
            cleaned_pages.append("\n".join(lines))

        stitched_parts: list[str] = []
        for page_str in cleaned_pages:
            if not page_str.strip():
                continue
            if not stitched_parts:
                stitched_parts.append(page_str)
                continue

            prev = stitched_parts[-1].rstrip()
            curr = page_str.lstrip()

            last_char = prev[-1:] if prev else ""
            first_line = curr.splitlines()[0] if curr else ""

            starts_as_new_block = (
                first_line.startswith(("#", "-", "*", "•"))
                or any(
                    first_line.startswith(pfx)
                    for pfx in ("الفصل", "الباب", "المادة", "المبحث")
                )
            )

            if last_char not in terminal_punct and not starts_as_new_block:
                stitched_parts[-1] = f"{prev} {curr}"
            else:
                stitched_parts.append(curr)

        return "\n\n".join(p for p in stitched_parts if p.strip())

    @property
    def confidence(self) -> float:
        """
        أدنى ثقة في الصفحات **ذات النص** — أضعف حلقة في السلسلة.

        الصفحات شبه الفارغة (غلاف، بياض) كانت تسحب الثقة إلى ٠٫٠ رغم
        أن متن الكتاب سليم. تُستثنى الصفحات بأقل من ٤٠ محرفاً غير فراغ.
        """
        substantive = [
            p.repair.confidence
            for p in self.pages
            if len((p.text or "").strip()) >= 40
        ]
        if substantive:
            return min(substantive)
        return min((p.repair.confidence for p in self.pages), default=0.0)

    def to_rag_chunks(self, *, max_chars: int = 1200) -> list[RAGChunk]:
        """Return deterministic citation-ready spatial chunks for this document."""
        import importlib
        import sys

        rag_mod = sys.modules.get("arafix.rag") or importlib.import_module("arafix.rag")
        fn = rag_mod.spatial_rag_chunks
        return fn(self, max_chars=max_chars)

    def to_rag_json(self, *, max_chars: int = 1200, indent: int | None = 2) -> str:
        """Serialize citation-ready spatial chunks as the native RAG JSON format."""
        import json

        payload = {
            "schema": "arafix.spatial-rag.v1",
            "source": self.path,
            "chunking": {"method": "structure-aware", "max_chars": max_chars},
            "chunks": [
                chunk.to_dict() for chunk in self.to_rag_chunks(max_chars=max_chars)
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=indent)

    def __str__(self) -> str:
        return self.text

    @property
    def tables(self) -> list[TableResult]:
        """كافة جداول المستند ككائنات TableResult غنية."""
        out: list[TableResult] = []
        for p in self.pages:
            out.extend(p.tables_rich)
        return out

    def tables_to_markdown(self) -> list[str]:
        """تصدير كافة جداول المستند كسلاسل Markdown."""
        return [t.to_markdown() for t in self.tables]

    def tables_to_csv(self) -> list[str]:
        """تصدير كافة جداول المستند بصيغة CSV."""
        return [t.to_csv() for t in self.tables]

    def to_markdown(
        self,
        *,
        include_page_breaks: bool = True,
        include_headers_footers: bool = False,
    ) -> str:
        """
        تصدير المستند كاملاً كملف Markdown احترافي، يترجم العناوين إلى (#, ##, ###)
        ويفرز القوائم والجداول، ويدمج الفقرات عبر الصفحات.
        """
        if not self.pages:
            return ""

        page_markdowns = [
            p.to_markdown(include_headers_footers=include_headers_footers)
            for p in self.pages
        ]

        if include_page_breaks:
            return "\n\n---\n\n".join(md for md in page_markdowns if md.strip())

        return "\n\n".join(md for md in page_markdowns if md.strip())

    def to_llm_text(
        self,
        *,
        optimize_tokens: bool = True,
        strip_tashkeel: bool = False,
        include_tables: bool = True,
        include_page_markers: bool = False,
    ) -> str:
        """
        تصدير النص بأعلى كفاءة لـ LLMs وتقليل استهلاك التوكنز بنسبة تصل إلى 45%.

        المزايا:
        - استبعاد الترويسات والتذييلات وأرقام الصفحات المتكررة.
        - وصل الجمل المنكسرة عبر حواف الصفحات.
        - صياغة هيكلية خفيفة (عناوين Markdown وجداول واضحة).
        - إزالة التطويل/الكشيدة وتكثيف الفراغات البيضاء المكررة.
        - خيار تجريد التشكيل الفائض (strip_tashkeel=True) لتوفير أقصى قدر من التوكنز.
        """
        import re

        from .unicode_tables import is_arabic_diacritic

        chunks: list[str] = []
        r_headers, r_footers = self.identify_running_headers_footers()

        for p in self.pages:
            if include_page_markers:
                chunks.append(f"\n[الصفحة {p.page_number}]\n")

            md = p.to_markdown(include_headers_footers=False)
            lines = []
            for ln in md.splitlines():
                cl = ln.strip()
                if cl in r_headers or cl in r_footers:
                    continue
                lines.append(ln)
            chunks.append("\n".join(lines))

        text = "\n\n".join(c for c in chunks if c.strip())

        if optimize_tokens:
            text = text.replace("\u0640", "")
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = "\n".join(ln.strip() for ln in text.splitlines())

        if strip_tashkeel:
            text = "".join(ch for ch in text if not is_arabic_diacritic(ch))

        return text.strip()

    @property
    def all_tables(self) -> list[list[list[str]]]:
        """كل جداول المستند بالترتيب."""
        out: list[list[list[str]]] = []
        for p in self.pages:
            out.extend(p.tables)
        return out


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


@dataclass
class TableResult:
    """
    جدولٌ مستخرجٌ ومُصلحٌ ذو دوال تصدير إلى Markdown و CSV و Pandas و Dict.
    """

    rows: list[list[str]]
    page: int = 1
    index: int = 0
    bbox: tuple[float, float, float, float] | None = None

    @property
    def headers(self) -> list[str]:
        return list(self.rows[0]) if self.rows else []

    @property
    def data(self) -> list[list[str]]:
        return [list(r) for r in self.rows[1:]] if len(self.rows) > 1 else []

    def to_markdown(self) -> str:
        return table_to_markdown(self.rows)

    def to_csv(self) -> str:
        import csv
        import io

        if not self.rows:
            return ""
        buf = io.StringIO()
        writer = csv.writer(buf)
        for r in self.rows:
            writer.writerow(r)
        return buf.getvalue()

    def to_dict(self) -> list[dict[str, str]]:
        """يحول الجدول إلى قائمة قواميس باعتبار الصف الأول ترويسة الأعمدة."""
        if not self.rows:
            return []
        headers = [h.strip() or f"col_{i}" for i, h in enumerate(self.rows[0])]
        out = []
        for r in self.rows[1:]:
            row_dict = {}
            for i, h in enumerate(headers):
                val = r[i] if i < len(r) else ""
                row_dict[h] = val
            out.append(row_dict)
        return out

    def to_dataframe(self) -> Any:
        """يحول الجدول إلى DataFrame في حال توفر مكتبة pandas."""
        try:
            import pandas as pd
        except ImportError as err:
            raise ImportError(
                "مكتبة pandas غير مثبتة. ثبّتها عبر: pip install pandas"
            ) from err
        if not self.rows:
            return pd.DataFrame()
        return pd.DataFrame(self.data, columns=self.headers or None)

    def repair(self, config: Any = None) -> TableResult:
        """يصلح نصوص خلايا الجدول باستخدام خط الأنابيب القياسي."""
        new_rows = [
            [_dispatch_repair_text(cell, config).text for cell in row]
            for row in self.rows
        ]
        return TableResult(
            rows=new_rows,
            page=self.page,
            index=self.index,
            bbox=self.bbox,
        )

    def __str__(self) -> str:
        return self.to_markdown()


@dataclass
class TextBlock:
    """كتلة نصية ذات موقع وهوية — خلية جدول، سطر، ترويسة."""

    text: str
    id: str | None = None
    role: str | None = None  # "cell" | "line" | "heading" | "caption" | …
    bbox: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class BlockResult:
    """حصيلة إصلاح كتلةٍ واحدة مع هويّتها الأصلية."""

    block: TextBlock
    repair: RepairResult

    @property
    def text(self) -> str:
        return self.repair.text

    @property
    def id(self) -> str | None:
        return self.block.id

    def __str__(self) -> str:
        return self.text


@dataclass
class BlocksResult:
    """حصيلة ``repair_blocks`` — قائمة مرتَّبة كما وصلت."""

    blocks: list[BlockResult] = field(default_factory=list)

    @property
    def texts(self) -> list[str]:
        return [b.text for b in self.blocks]

    @property
    def confidence(self) -> float:
        return min((b.repair.confidence for b in self.blocks), default=0.0)

    def by_id(self) -> dict[str, BlockResult]:
        return {b.id: b for b in self.blocks if b.id is not None}

    def join(self, sep: str = "\n") -> str:
        return sep.join(b.text for b in self.blocks)

    def __str__(self) -> str:
        return self.join()


def as_blocks(
    rows: list[list[str]],
    *,
    id_prefix: str = "r",
) -> list[TextBlock]:
    """تحول جدولاً (قائمة صفوف) إلى كتل TextBlock خلايا مستقلة."""
    blocks: list[TextBlock] = []
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            blocks.append(
                TextBlock(
                    text=cell or "",
                    id=f"{id_prefix}{i}c{j}",
                    role="cell",
                    meta={"row": i, "col": j},
                )
            )
    return blocks


def fix_table(
    rows: list[list[str]],
    config: Any = None,
) -> list[list[str]]:
    """
    يصلح خلايا جدولٍ خليةً على حدة وبنفس الهيكل الأصلي.
    """
    if not rows:
        return []
    blocks = as_blocks(rows)
    repaired: BlocksResult = _dispatch_repair_blocks(blocks, config)
    by_id = repaired.by_id()
    out: list[list[str]] = []
    for i, row in enumerate(rows):
        new_row = []
        for j, _ in enumerate(row):
            key = f"r{i}c{j}"
            new_row.append(by_id[key].text if key in by_id else "")
        out.append(new_row)
    return out

