"""
معاجم اختيارية مضمَّنة — لا تُحمَّل إلا عند الطلب.

المستوى الافتراضي: :mod:`arafix.lexicon.core` (كلمات شائعة لحسم
انقلاب لام-ألف المُبهَم). يُفعَّل من الأنبوب عبر
``PipelineConfig.use_core_lexicon``.
"""

from __future__ import annotations

from .core import (
    clear_core_lexicon_cache,
    core_lexicon_size,
    get_core_lexicon,
)

__all__ = [
    "get_core_lexicon",
    "core_lexicon_size",
    "clear_core_lexicon_cache",
]
