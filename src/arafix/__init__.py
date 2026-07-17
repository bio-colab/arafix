"""
arafix — استرجاع النص العربي من ملفات PDF المعطوبة.

سلّم من خمس درجات، لا مطرقة واحدة:

    ٠ التشخيص     diagnose()         لا تعالج قبل أن تعرف
    ١أ التطبيع     fold_simple_forms() الأشكال المفردة؛ الرباطُ ذرّةٌ بعد
    ٢ الاتجاه      fix_order()         بصريّ ← منطقيّ، بحماية الأرقام
    ١ب الرباطات    expand_ligatures()  ﻻ ← لا، بعد استقرار الترتيب
    ٣ الخريطة      build_glyph_map() إعادة بنائها من الخط المضمَّن
    ٤ الـ OCR      (خارجيّ)            آخر الدواء، لا أوّله

وفوقها القياس — فرقمٌ على ملفاتك أصدقُ من كل شهاداتنا:

    >>> from arafix import compare_extractors        # doctest: +SKIP
    >>> for r in compare_extractors("t.pdf", "t.txt"):  # doctest: +SKIP
    ...     print(r)                                  # doctest: +SKIP

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

__version__ = "0.4.0"
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
from .evaluate import (
    EvalConfig,
    EvalReport,
    cer,
    compare_extractors,
    evaluate_pdf,
    evaluate_text,
    levenshtein,
    wer,
)
from .extractors import Extractor, RawPage, get_extractor, register
from .lamalef import (
    LamAlefReport,
    detect_lam_alef_transposition,
    repair_lam_alef_transposition,
)
from .normalize import (
    NormalizeConfig,
    expand_deferred_forms,
    expand_ligatures,
    fold_presentation_forms,
    fold_simple_forms,
    normalize_text,
)
from .order import (
    MIRROR_PAIRS,
    ReorderConfig,
    fix_order,
    grapheme_clusters,
    reverse_visual_line,
)
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
from .unicode_tables import (
    DEFERRED_PF_TO_BASE,
    LIGATURE_PF_TO_BASE,
    PF_TO_BASE,
    SIMPLE_PF_TO_BASE,
    SPACING_MARK_PF_TO_BASE,
    JoiningForm,
    unicode_version,
)

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
    # الدرجة ١ (تمريرتان: مفردات ← اتجاه ← رباطات)
    "normalize_text",
    "fold_presentation_forms",
    "fold_simple_forms",
    "expand_deferred_forms",
    "expand_ligatures",
    "NormalizeConfig",
    # لام-ألف
    "detect_lam_alef_transposition",
    "repair_lam_alef_transposition",
    "LamAlefReport",
    # الدرجة ٢
    "fix_order",
    "reverse_visual_line",
    "grapheme_clusters",
    "MIRROR_PAIRS",
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
    # القياس
    "evaluate_text",
    "evaluate_pdf",
    "compare_extractors",
    "cer",
    "wer",
    "levenshtein",
    "EvalConfig",
    "EvalReport",
    # المحرّكات
    "Extractor",
    "RawPage",
    "get_extractor",
    "register",
    # الجداول
    "PF_TO_BASE",
    "SIMPLE_PF_TO_BASE",
    "DEFERRED_PF_TO_BASE",
    "LIGATURE_PF_TO_BASE",
    "SPACING_MARK_PF_TO_BASE",
    "JoiningForm",
    "unicode_version",
]
