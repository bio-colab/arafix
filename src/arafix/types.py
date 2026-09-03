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
    from .rag import RAGChunk

__all__ = [
    "Defect",
    "Stage",
    "Evidence",
    "Diagnosis",
    "RepairResult",
    "PageResult",
    "DocumentResult",
    "TextBlock",
    "BlockResult",
    "BlocksResult",
]


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

    def __str__(self) -> str:
        return self.text


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
        from .rag import spatial_rag_chunks

        return spatial_rag_chunks(self, max_chars=max_chars)

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
    def all_tables(self) -> list[list[list[str]]]:
        """كل جداول المستند بالترتيب."""
        out: list[list[list[str]]] = []
        for p in self.pages:
            out.extend(p.tables)
        return out


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
