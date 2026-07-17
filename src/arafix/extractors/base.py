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


@dataclass
class RawPage:
    """صفحة كما خرجت من المحرّك، قبل أيّ علاج."""

    number: int
    text: str
    fonts: list[str] = field(default_factory=list)
    has_images: bool = False

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

    @classmethod
    def available(cls) -> bool:
        """أمُثبَّتة تبعيّات هذا المحرّك؟"""
        return True
