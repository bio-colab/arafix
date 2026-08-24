"""
عقد الاستخراج — المفصل الذي تُركَّب فيه المحرّكات.

المكتبة **لا تكتب قارئ PDF**، وهذا قرار معماري مقصود: كتابة قارئ PDF
من الصفر عملُ سنين، وموجودٌ منه ما يكفي. مهمّتنا ما بعد القراءة.

فكل محرّك (PyMuPDF, pdfminer, pdftotext…) يُغلَّف خلف هذا العقد
الواحد. وأثر ذلك عمليّ لا نظريّ: تبديل المحرّك سطرٌ واحد، وإضافة
محرّك جديد ملفٌّ واحد لا يمسّ شيئاً من الباقي.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawPage:
    """صفحة كما خرجت من المحرّك، قبل أيّ علاج."""

    number: int
    text: str
    fonts: list[str] = field(default_factory=list)
    has_images: bool = False
    #: عرض/ارتفاع الصفحة بنقاط PDF — للتحليل البنيويّ.
    width: float = 0.0
    height: float = 0.0
    #: جليفات هندسية ``(y, x, text, size[, seq, glyph_id, font])`` إن وفّرها
    #: المحرّك. الحقول الإضافية اختيارية لحفظ توافق المستخرجات الخارجية.
    glyphs: list[tuple] = field(default_factory=list)
    #: ``PageLayout`` جاهز إن حُسب أثناء الاستخراج.
    layout: Any = None
    #: عدد spans التي حذفها فلتر الضوضاء الهندسية قبل بناء الجليفات.
    noise_spans_removed: int = 0
    #: أسباب الحذف بحسب نوع الدليل الفيزيائي.
    noise_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """صفحة بلا طبقة نصية — مرشّحة للدرجة ٤ (OCR)."""
        return not self.text.strip()


class Extractor(ABC):
    """العقد. أيّ صنف يحقّقه يصلح محرّكاً لهذه المكتبة."""

    name: str = "abstract"

    @abstractmethod
    def pages(self, path: str) -> Iterator[RawPage]:
        """يُنتج صفحات الملف واحدةً واحدة (مولِّد، لا قائمة — لأجل الملفات الضخمة)."""

    @abstractmethod
    def font_bytes(self, path: str) -> dict[str, bytes]:
        """يُرجع الخطوط المضمَّنة: اسم الخط ← بايتاته. تحتاجها الدرجة ٣."""

    def metadata(self, path: str) -> dict[str, Any]:
        """يُرجع metadata على مستوى الملف، إن كان المحرّك يعرفها.

        هذا hook اختياري وغير مجرّد حتى تبقى المحركات الخارجية القديمة
        المتوافقة مع العقد؛ المحرك الذي لا يملك metadata يعيد قاموساً فارغاً.
        البيانات وصفية فقط ولا تمنح أي مرحلة إصلاح صلاحية جديدة.
        """
        return {}

    @classmethod
    def available(cls) -> bool:
        """أمُثبَّتة تبعيّات هذا المحرّك؟"""
        return True
