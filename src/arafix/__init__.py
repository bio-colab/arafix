"""
arafix — recover broken Arabic text from PDFs.

Graded ladder (not one hammer)::

    0  diagnose()          know before you fix
    1a fold_simple_forms() presentation forms; keep ligatures atomic
    2  fix_order()         visual → logical, protect LTR runs
    1b expand_ligatures()  ﻻ → لا after order is stable
    3  build_glyph_map()   rebuild from embedded font
    4  OCR                 last resort (not shipped)

Quick start::

    >>> from arafix import repair_text
    >>> repair_text("\ufee3\ufeae\ufea3\ufe92\ufe8e").text
    'مرحبا'

    >>> from arafix import repair_blocks
    >>> repair_blocks(["\ufee3\ufeae\ufea3\ufe92\ufe8e"]).texts[0]
    'مرحبا'

    >>> from arafix import extract_pdf           # doctest: +SKIP
    >>> doc = extract_pdf("thesis.pdf")          # doctest: +SKIP

MIT license. Primary long-form docs are in Arabic (README).
"""

from __future__ import annotations

__version__ = "1.0.1"
__license__ = "MIT"

from .adapters import as_blocks, fix_any, fix_markitdown, fix_table
from .audit import (
    AuditEvent,
    AuditMode,
    AuditTrail,
    EvidenceItem,
    Patch,
    PatchOperation,
    RepairAudit,
    RepairDecision,
    sha256_text,
)
from .cmap import GlyphMap, build_glyph_map, decode_glyph_name
from .context import ContextCandidate, ContextDecision, ContextRepair, DocumentContext
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
    levenshtein_reference,
    wer,
)
from .evidence import (
    Candidate,
    CandidateGenerator,
    CharacterConfusionModel,
    Confusion,
    EvidenceDecision,
    EvidenceFusion,
    GlyphEvidence,
    NegativeEvidence,
    NegativeEvidenceModel,
)
from .extractors import Extractor, RawPage, get_extractor, register
from .hygiene import (
    count_artifacts,
    fold_arabic_punct_confusables,
    sanitize_extraction,
)
from .lamalef import (
    LamAlefReport,
    detect_lam_alef_transposition,
    repair_lam_alef_transposition,
)
from .layout import (
    Glyph,
    LayoutColumn,
    LayoutConfig,
    LayoutLine,
    LayoutTable,
    PageLayout,
    analyze_layout,
    cluster_to_lines,
    table_to_markdown,
)
from .lexicon import clear_core_lexicon_cache, core_lexicon_size, get_core_lexicon
from .noise import GeometricNoiseConfig, GeometricNoiseFilter
from .normalize import (
    NormalizeConfig,
    expand_deferred_forms,
    expand_ligatures,
    fold_pdf_homoglyphs,
    fold_presentation_forms,
    fold_simple_forms,
    normalize_text,
)
from .order import (
    MIRROR_PAIRS,
    ReorderConfig,
    fix_order,
    grapheme_clusters,
    normalize_page_ranges,
    order_combining_marks,
    relocate_sentence_punctuation,
    repair_inverted_ltr_parens,
    reverse_visual_line,
)
from .pdf_confusions import (
    PdfConfusionReport,
    repair_pdf_confusions,
)
from .pipeline import (
    PipelineConfig,
    extract_pdf,
    harvest_document_lexicon,
    repair_blocks,
    repair_text,
)
from .rag import RAGChunk, extract_pdf_rag, spatial_rag_chunks
from .scientific import (
    BFEReport,
    DBRReport,
    MCSReport,
    ScientificReport,
    SHDRReport,
    bidi_flow_entropy,
    diacritic_base_matrix,
    homoglyph_drift,
    morphological_continuity,
    scientific_audit,
)
from .types import (
    BlockResult,
    BlocksResult,
    Defect,
    Diagnosis,
    DocumentResult,
    Evidence,
    PageResult,
    RepairResult,
    Stage,
    TextBlock,
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
    "repair_blocks",
    # التدقيق والرقع القابلة للعكس
    "AuditMode",
    "RepairDecision",
    "EvidenceItem",
    "AuditEvent",
    "PatchOperation",
    "Patch",
    "RepairAudit",
    "AuditTrail",
    "sha256_text",
    "extract_pdf",
    "extract_pdf_rag",
    "spatial_rag_chunks",
    "RAGChunk",
    "PipelineConfig",
    "harvest_document_lexicon",
    "DocumentContext",
    "ContextCandidate",
    "ContextDecision",
    "ContextRepair",
    "Candidate",
    "CandidateGenerator",
    "CharacterConfusionModel",
    "Confusion",
    "EvidenceDecision",
    "EvidenceFusion",
    "GlyphEvidence",
    "NegativeEvidence",
    "NegativeEvidenceModel",
    # مهايئات
    "fix_any",
    "fix_markitdown",
    "fix_table",
    "as_blocks",
    # نظافة الاستخراج
    "sanitize_extraction",
    "count_artifacts",
    "fold_arabic_punct_confusables",
    # البنية
    "Glyph",
    "LayoutLine",
    "LayoutColumn",
    "LayoutTable",
    "PageLayout",
    "LayoutConfig",
    "analyze_layout",
    "cluster_to_lines",
    "table_to_markdown",
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
    "fold_pdf_homoglyphs",
    "expand_deferred_forms",
    "expand_ligatures",
    "NormalizeConfig",
    "GeometricNoiseConfig",
    "GeometricNoiseFilter",
    # معجم النواة
    "get_core_lexicon",
    "core_lexicon_size",
    "clear_core_lexicon_cache",
    # لام-ألف
    "detect_lam_alef_transposition",
    "repair_lam_alef_transposition",
    "LamAlefReport",
    # التباسات كتب PDF منشورة (Safahat — ليست مولّدة بالذكاء الاصطناعي)
    "repair_pdf_confusions",
    "PdfConfusionReport",
    # الدرجة ٢
    "fix_order",
    "reverse_visual_line",
    "grapheme_clusters",
    "order_combining_marks",
    "normalize_page_ranges",
    "relocate_sentence_punctuation",
    "repair_inverted_ltr_parens",
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
    "TextBlock",
    "BlockResult",
    "BlocksResult",
    # القياس
    "evaluate_text",
    "evaluate_pdf",
    "compare_extractors",
    "cer",
    "wer",
    "levenshtein",
    "levenshtein_reference",
    "EvalConfig",
    "EvalReport",
    # scientific metrics (MCS / DBR / BFE / SHDR)
    "scientific_audit",
    "morphological_continuity",
    "diacritic_base_matrix",
    "bidi_flow_entropy",
    "homoglyph_drift",
    "ScientificReport",
    "MCSReport",
    "DBRReport",
    "BFEReport",
    "SHDRReport",
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
