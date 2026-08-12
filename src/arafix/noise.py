"""Pre-pipeline geometric noise filtering for PDF text spans.

The filter is deliberately conservative.  It never classifies text by Arabic
content.  It only removes a span when physical evidence is strong: a light
gray rotated span, or a repeated small span at the same geometric position
with a matching physical signature.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

__all__ = ["GeometricNoiseConfig", "GeometricNoiseFilter"]

_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class GeometricNoiseConfig:
    """Thresholds for the opt-in geometric PDF noise filter."""

    min_rotation_degrees: float = 8.0
    light_gray_min: float = 0.60
    gray_tolerance: float = 0.10
    min_watermark_size: float = 16.0
    repeated_min_pages: int = 2
    position_quantum: float = 4.0
    angle_quantum_degrees: float = 2.0
    #: Two-pass repetition detection is opt-in because it requires a second
    #: text-trace pass over large PDFs.  Strong gray+rotation evidence remains
    #: single-pass and enabled by default.
    remove_repeated_short_spans: bool = False


class GeometricNoiseFilter:
    """Classify PDF text-trace spans using physical, not linguistic, evidence."""

    def __init__(self, config: GeometricNoiseConfig | None = None) -> None:
        self.config = config or GeometricNoiseConfig()

    @staticmethod
    def span_text(span: Mapping) -> str:
        chars = span.get("chars") or ()
        return "".join(chr(c[0]) for c in chars).strip()

    @staticmethod
    def _color(span: Mapping) -> tuple[float, float, float] | None:
        color = span.get("color")
        if not color or len(color) < 3:
            return None
        try:
            return float(color[0]), float(color[1]), float(color[2])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _angle_degrees(span: Mapping) -> float:
        direction = span.get("dir") or (1.0, 0.0)
        try:
            return abs(math.degrees(math.atan2(float(direction[1]), float(direction[0]))))
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0

    def is_light_gray(self, span: Mapping) -> bool:
        color = self._color(span)
        if color is None:
            return False
        lo, hi = min(color), max(color)
        mean = sum(color) / 3.0
        return mean >= self.config.light_gray_min and hi - lo <= self.config.gray_tolerance

    def is_rotated(self, span: Mapping) -> bool:
        return self._angle_degrees(span) >= self.config.min_rotation_degrees

    def _quantize(self, value: float) -> int:
        q = self.config.position_quantum
        return int(round(value / q)) if q > 0 else int(round(value))

    def _repeat_key(self, span: Mapping) -> tuple | None:
        text = self.span_text(span)
        bbox = span.get("bbox")
        if not text or not bbox or len(bbox) < 4:
            return None
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox[:4])
            angle = self._angle_degrees(span)
            angle_q = self.config.angle_quantum_degrees
            aq = int(round(angle / angle_q)) if angle_q > 0 else int(round(angle))
            return (
                _SPACE_RE.sub(" ", text),
                self._quantize(x0),
                self._quantize(y0),
                self._quantize(x1),
                self._quantize(y1),
                aq,
            )
        except (TypeError, ValueError):
            return None

    def repeated_keys(self, pages: Iterable[Sequence[Mapping]]) -> set[tuple]:
        """Return span fingerprints occurring on at least N distinct pages."""
        seen: dict[tuple, set[int]] = defaultdict(set)
        for page_number, spans in enumerate(pages):
            page_keys = {key for span in spans if (key := self._repeat_key(span))}
            for key in page_keys:
                seen[key].add(page_number)
        minimum = max(2, int(self.config.repeated_min_pages))
        return {key for key, page_numbers in seen.items() if len(page_numbers) >= minimum}

    def should_drop(self, span: Mapping, repeated_keys: set[tuple] | None = None) -> tuple[bool, str]:
        """Return ``(drop, reason)`` for one text-trace span."""
        text = self.span_text(span)
        if not text:
            return False, ""
        repeated = bool(repeated_keys and self._repeat_key(span) in repeated_keys)
        gray = self.is_light_gray(span)
        rotated = self.is_rotated(span)
        size = float(span.get("size") or 0.0)

        if gray and rotated and (size >= self.config.min_watermark_size or repeated):
            return True, "light-gray-rotated"
        if (
            self.config.remove_repeated_short_spans
            and repeated
            and len(text) <= 2
            and (gray or rotated)
        ):
            return True, "repeated-short-span"
        return False, ""

    def filter_spans(
        self, spans: Sequence[Mapping], repeated_keys: set[tuple] | None = None
    ) -> tuple[list[Mapping], int, dict[str, int]]:
        kept: list[Mapping] = []
        counts: dict[str, int] = defaultdict(int)
        for span in spans:
            drop, reason = self.should_drop(span, repeated_keys)
            if drop:
                counts[reason] += 1
            else:
                kept.append(span)
        return kept, sum(counts.values()), dict(counts)
