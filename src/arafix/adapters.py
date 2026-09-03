"""
مهايئات خفيفة — مسارٌ واحد من «نصٍّ مستخرج بأيّ أداة» إلى عربيّ سليم.

    from arafix.adapters import fix_any, fix_table, wrap_callable
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .pipeline import PipelineConfig, repair_blocks, repair_text
from .types import BlocksResult, RepairResult, TextBlock

__all__ = ["fix_any", "fix_table", "as_blocks", "wrap_callable", "repair_extracted"]


def repair_extracted(
    text: str,
    config: PipelineConfig | None = None,
) -> RepairResult:
    """مدخل موحَّد لما بعد أيّ مستخرج (pdfminer، نسخ من المتصفح…)."""
    return repair_text(text, config)


def wrap_callable(
    extract_fn: Callable[..., str],
    config: PipelineConfig | None = None,
) -> Callable[..., RepairResult]:
    """يغلّف دالة استخراج لتعيد RepairResult بدل نصٍّ عارٍ."""

    def _wrapped(*args: Any, **kwargs: Any) -> RepairResult:
        return repair_text(extract_fn(*args, **kwargs), config)

    _wrapped.__name__ = getattr(extract_fn, "__name__", "wrapped") + "_arafix"
    _wrapped.__doc__ = (
        f"arafix-wrapped {getattr(extract_fn, '__name__', extract_fn)!r}: "
        "extract then repair_text."
    )
    return _wrapped


def fix_any(text: str, config: PipelineConfig | None = None) -> RepairResult:
    """أيّ نصٍّ — من pdfminer أو المتصفح أو الحافظة."""
    return repair_text(text, config)


def as_blocks(
    rows: list[list[str]],
    *,
    id_prefix: str = "r",
) -> list[TextBlock]:
    """ يحوّل جدولاً (قائمة صفوف) إلى كتل ``TextBlock`` بخلايا مستقلة."""
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
    config: PipelineConfig | None = None,
) -> list[list[str]]:
    """
    يصلح خلايا جدولٍ كلٌّ على حدة ويُرجع نفس الشكل.

    >>> fix_table([["\ufee3\ufeae\ufea3\ufe92\ufe8e", "OK"]])
    [['مرحبا', 'OK']]
    """
    if not rows:
        return []
    blocks = as_blocks(rows)
    repaired: BlocksResult = repair_blocks(blocks, config)
    by_id = repaired.by_id()
    out: list[list[str]] = []
    for i, row in enumerate(rows):
        new_row = []
        for j, _ in enumerate(row):
            key = f"r{i}c{j}"
            new_row.append(by_id[key].text if key in by_id else "")
        out.append(new_row)
    return out
