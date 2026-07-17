"""
arafix — استرجاع النص العربي من ملفات PDF المعطوبة.

سلّم من خمس درجات، لا مطرقة واحدة:

    ٠ التشخيص     diagnose()       لا تعالج قبل أن تعرف
    ١ التطبيع      normalize_text() الأشكال الرسومية ← الحروف الأصلية
    ٢ الاتجاه      fix_order()      بصريّ ← منطقيّ، بحماية الأرقام
    ٣ الخريطة      build_glyph_map() إعادة بنائها من الخط المضمَّن
    ٤ الـ OCR      (خارجيّ)          آخر الدواء، لا أوّله

الاستعمال الأسرع:

    >>> from arafix import repair_text
    >>> repair_text("\ufee3\ufeae\ufea3\ufe92\ufe8e").text
    'مرحبا'

    >>> from arafix import extract_pdf           # doctest: +SKIP
    >>> doc = extract_pdf("thesis.pdf")          # doctest: +SKIP
    >>> print(doc.text, doc.confidence)          # doctest: +SKIP

الترخيص: MIT.
"""

from __future__ import annotations

__version__ = "0.1.0"
__license__ = "MIT"

from .cmap import GlyphMap, build_glyph_map, decode_glyph_name
from .diagnose import (
    DEFAULT_THRESHOLDS,
    detect_mojibake,
    detect_presentation_forms,
    detect_pua,
    detect_visual_order,
    diagnose,
)
from .extractors import Extractor, RawPage, get_extractor, register
from .normalize import NormalizeConfig, fold_presentation_forms, normalize_text
from .order import ReorderConfig, fix_order, reverse_visual_line
from .pipeline import PipelineConfig, extract_pdf, repair_text
from .types import (
    Defect,
    Diagnosis,
    DocumentResult,
    Evidence,
    PageResult,
    RepairResult,
    Stage,
)
from .unicode_tables import PF_TO_BASE, JoiningForm, unicode_version

__all__ = [
    "__version__",
    # الأنبوب
    "repair_text",
    "extract_pdf",
    "PipelineConfig",
    # الدرجة ٠
    "diagnose",
    "detect_mojibake",
    "detect_presentation_forms",
    "detect_pua",
    "detect_visual_order",
    "DEFAULT_THRESHOLDS",
    # الدرجة ١
    "normalize_text",
    "fold_presentation_forms",
    "NormalizeConfig",
    # الدرجة ٢
    "fix_order",
    "reverse_visual_line",
    "ReorderConfig",
    # الدرجة ٣
    "build_glyph_map",
    "decode_glyph_name",
    "GlyphMap",
    # النماذج
    "Defect",
    "Stage",
    "Evidence",
    "Diagnosis",
    "RepairResult",
    "PageResult",
    "DocumentResult",
    # المحرّكات
    "Extractor",
    "RawPage",
    "get_extractor",
    "register",
    # الجداول
    "PF_TO_BASE",
    "JoiningForm",
    "unicode_version",
]
