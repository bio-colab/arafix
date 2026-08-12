"""Document-local context scoring for conservative Arabic recovery.

This module is deliberately dependency-free.  It is not a spell checker and it
never invents a word outside the document vocabulary.  A replacement is
accepted only when edit distance, document frequency, phrase support, character
n-grams, and a score margin agree; otherwise the model abstains.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass

__all__ = [
    "ContextCandidate",
    "ContextDecision",
    "ContextRepair",
    "DocumentContext",
]

_WORD_RE = re.compile(r"[\u0621-\u064A\u0671-\u06D3]{3,}")


@dataclass(frozen=True)
class ContextCandidate:
    """One document-supported candidate for an observed token."""

    word: str
    edit_distance: int
    document_frequency: int
    phrase_support: int
    phrase_sides: int
    word_score: float
    character_score: float
    margin: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ContextDecision:
    """An accepted or rejected candidate decision with independent evidence."""

    observed: str
    replacement: str | None
    left_context: str | None
    right_context: str | None
    accepted: bool
    reason: str
    candidates: tuple[ContextCandidate, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return payload


@dataclass(frozen=True)
class ContextRepair:
    """Result of one context-scoring pass."""

    text: str
    decisions: tuple[ContextDecision, ...] = ()
    confidence: float = 1.0

    @property
    def changed(self) -> bool:
        return bool(self.decisions and any(d.accepted for d in self.decisions))

    @property
    def accepted_count(self) -> int:
        return sum(1 for decision in self.decisions if decision.accepted)

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "accepted_count": self.accepted_count,
            "confidence": self.confidence,
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


class DocumentContext:
    """A compact word/phrase/character model learned from one document.

    The model is intentionally document-local.  It stores only words that occur
    at least ``min_frequency`` times as repair candidates, while retaining all
    token counts for phrase denominators.  No external model or package is
    required.
    """

    def __init__(
        self,
        text: str,
        *,
        min_frequency: int = 3,
        min_phrase_support: int = 2,
        max_edit_distance: int = 1,
    ) -> None:
        if min_frequency < 1:
            raise ValueError("min_frequency must be positive")
        if min_phrase_support < 1:
            raise ValueError("min_phrase_support must be positive")
        if max_edit_distance != 1:
            raise ValueError("only edit distance 1 is supported in v1")

        self.min_frequency = min_frequency
        self.min_phrase_support = min_phrase_support
        self.max_edit_distance = max_edit_distance
        tokens = tuple(_WORD_RE.findall(text))
        self.word_counts = Counter(tokens)
        self.vocabulary = {
            word for word, count in self.word_counts.items() if count >= min_frequency
        }
        self.phrase_counts = Counter(zip(tokens, tokens[1:]))
        self.character_counts = Counter(
            gram for word in tokens for gram in self._character_ngrams(word)
        )
        self.character_total = sum(self.character_counts.values())
        self.max_frequency = max(self.word_counts.values(), default=1)
        self._words_by_length: dict[int, tuple[str, ...]] = {
            length: tuple(sorted(word for word in self.vocabulary if len(word) == length))
            for length in {len(word) for word in self.vocabulary}
        }

    @classmethod
    def from_texts(
        cls,
        texts: Iterable[str],
        *,
        min_frequency: int = 3,
        min_phrase_support: int = 2,
    ) -> DocumentContext:
        """Build one model from page/block texts in their supplied order."""
        return cls(
            "\n".join(texts),
            min_frequency=min_frequency,
            min_phrase_support=min_phrase_support,
        )

    @staticmethod
    def _character_ngrams(word: str, n: int = 3) -> tuple[str, ...]:
        padded = f"^{word}$"
        if len(padded) <= n:
            return (padded,)
        return tuple(padded[i : i + n] for i in range(len(padded) - n + 1))

    @staticmethod
    def _edit_distance(left: str, right: str) -> int:
        previous = list(range(len(right) + 1))
        for i, left_char in enumerate(left, 1):
            current = [i]
            for j, right_char in enumerate(right, 1):
                current.append(
                    min(
                        current[-1] + 1,
                        previous[j] + 1,
                        previous[j - 1] + (left_char != right_char),
                    )
                )
            previous = current
        return previous[-1]

    def _character_score(self, word: str) -> float:
        grams = self._character_ngrams(word)
        if not grams or not self.character_total:
            return 0.0
        denominator = self.character_total + len(grams)
        return sum(
            math.log((self.character_counts[gram] + 1.0) / denominator)
            for gram in grams
        ) / len(grams)

    def _phrase_support(
        self,
        left: str | None,
        candidate: str,
        right: str | None,
    ) -> tuple[int, int]:
        counts: list[int] = []
        if left:
            counts.append(self.phrase_counts[(left, candidate)])
        if right:
            counts.append(self.phrase_counts[(candidate, right)])
        return sum(counts), sum(count > 0 for count in counts)

    def _phrase_score(
        self,
        left: str | None,
        candidate: str,
        right: str | None,
    ) -> float:
        support, sides = self._phrase_support(left, candidate, right)
        if not sides:
            return 0.0
        return math.log1p(support) / math.log1p(self.max_frequency)

    def _candidates(self, observed: str) -> list[str]:
        candidates: list[str] = []
        for length in range(max(3, len(observed) - 1), len(observed) + 2):
            for candidate in self._words_by_length.get(length, ()):
                if candidate != observed and self._edit_distance(observed, candidate) <= 1:
                    candidates.append(candidate)
        return candidates

    def rank(
        self,
        observed: str,
        left: str | None = None,
        right: str | None = None,
    ) -> tuple[ContextCandidate, ...]:
        """Rank document-vocabulary candidates without changing the text."""
        candidates = self._candidates(observed)
        if not candidates:
            return ()
        observed_phrase = self._phrase_score(left, observed, right)
        observed_character = self._character_score(observed)
        observed_score = 0.25 * observed_phrase + 0.10 * observed_character
        ranked: list[ContextCandidate] = []
        for candidate in candidates:
            distance = self._edit_distance(observed, candidate)
            frequency = self.word_counts[candidate]
            support, sides = self._phrase_support(left, candidate, right)
            frequency_score = math.log1p(frequency) / math.log1p(self.max_frequency)
            phrase_score = self._phrase_score(left, candidate, right)
            character_score = self._character_score(candidate)
            score = (
                0.40 * (1.0 - distance / max(len(observed), len(candidate)))
                + 0.25 * frequency_score
                + 0.25 * phrase_score
                + 0.10 * (character_score - observed_character)
            )
            ranked.append(
                ContextCandidate(
                    word=candidate,
                    edit_distance=distance,
                    document_frequency=frequency,
                    phrase_support=support,
                    phrase_sides=sides,
                    word_score=score,
                    character_score=character_score,
                    margin=score - observed_score,
                )
            )
        ranked.sort(
            key=lambda candidate: (
                candidate.word_score,
                candidate.document_frequency,
                candidate.word,
            ),
            reverse=True,
        )
        return tuple(ranked)

    def repair(self, text: str, *, min_margin: float = 0.12) -> ContextRepair:
        """Apply only high-agreement candidates; abstain otherwise."""
        matches = list(_WORD_RE.finditer(text))
        if not matches:
            return ContextRepair(text=text)
        tokens = [match.group(0) for match in matches]
        decisions: list[ContextDecision] = []
        output = text
        offset = 0
        margins: list[float] = []
        for index, match in enumerate(matches):
            observed = match.group(0)
            if observed in self.vocabulary:
                continue
            left = tokens[index - 1] if index else None
            right = tokens[index + 1] if index + 1 < len(tokens) else None
            ranked = self.rank(observed, left, right)
            if not ranked:
                continue
            best = ranked[0]
            second = ranked[1] if len(ranked) > 1 else None
            best_support, best_sides = self._phrase_support(left, best.word, right)
            accepted = (
                best.document_frequency >= self.min_frequency
                and best_support >= self.min_phrase_support
                and (not left or not right or best_sides == 2)
                and best.margin >= min_margin
                and best.word_score
                - (second.word_score if second is not None else 0.0)
                >= min_margin / 2
            )
            if not accepted:
                continue
            start = match.start() + offset
            end = match.end() + offset
            output = output[:start] + best.word + output[end:]
            offset += len(best.word) - len(observed)
            margins.append(best.margin)
            decisions.append(
                ContextDecision(
                    observed=observed,
                    replacement=best.word,
                    left_context=left,
                    right_context=right,
                    accepted=True,
                    reason="frequency+phrase+character+margin",
                    candidates=ranked[:5],
                )
            )

        confidence = (
            min(1.0, 0.85 + 0.15 * min(1.0, sum(margins) / len(margins)))
            if margins
            else 1.0
        )
        return ContextRepair(text=output, decisions=tuple(decisions), confidence=confidence)
