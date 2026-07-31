"""
جسور اختيارية نحو أنظمة أخرى — **لا** تبعيّات في النواة.

  * ``markitdown_plugin`` — يُسجَّل عبر entry point؛ يُحمَّل فقط إن وُجد MarkItDown.
  * ``wrap_callable`` — أيّ دالة ``path → str`` تُغلَّف بـ ``repair_text``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from arafix.pipeline import PipelineConfig, repair_text
from arafix.types import RepairResult

__all__ = ["wrap_callable", "repair_extracted"]


def repair_extracted(
    text: str,
    config: PipelineConfig | None = None,
) -> RepairResult:
    """مدخل موحَّد لما بعد أيّ مستخرج (markitdown، pdfminer، نسخ من المتصفح…)."""
    return repair_text(text, config)


def wrap_callable(
    extract_fn: Callable[..., str],
    config: PipelineConfig | None = None,
) -> Callable[..., RepairResult]:
    """
    يغلّف دالة استخراج لتعيد ``RepairResult`` بدل نصٍّ عارٍ.

    >>> def fake(path):  # doctest: +SKIP
    ...     return "\\ufee3\\ufeae\\ufea3\\ufe92\\ufe8e"
    >>> wrapped = wrap_callable(fake)  # doctest: +SKIP
    >>> wrapped("x.pdf").text  # doctest: +SKIP
    'مرحبا'
    """

    def _wrapped(*args: Any, **kwargs: Any) -> RepairResult:
        return repair_text(extract_fn(*args, **kwargs), config)

    _wrapped.__name__ = getattr(extract_fn, "__name__", "wrapped") + "_arafix"
    _wrapped.__doc__ = (
        f"arafix-wrapped {getattr(extract_fn, '__name__', extract_fn)!r}: "
        "extract then repair_text."
    )
    return _wrapped
