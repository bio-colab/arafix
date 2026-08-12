"""Document-local context and conservative recovery evidence.

``DocumentContext`` owns document statistics, while candidate generation and
acceptance live in :mod:`arafix.evidence`.  This keeps the context model from
being an independent spell checker: it contributes evidence to the same
candidate/decision path used by other sources.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from .audit import RepairDecision

if TYPE_CHECKING:
    from .evidence import (
        CandidateGenerator,
        EvidenceDecision,
        EvidenceFusion,
        NegativeEvidenceModel,
    )

__all__ = [
    "ContextCandidate",
    "ContextDecision",
    "ContextRepair",
    "DocumentContext",
]

_TOKEN_RE = re.compile(r"[\u0621-\u064A\u0671-\u06D3]+")
_ARABIC_LETTER_RE = re.compile(r"[\u0621-\u064A\u0671-\u06D3]")
_WORD_RE = re.compile(r"[\u0621-\u064A\u0671-\u06D3]{3,}")


def _touches_combining_mark(text: str, start: int, end: int) -> bool:
    """Reject only matches split by an internal Arabic combining mark."""
    if end < len(text) and unicodedata.combining(text[end]) != 0:
        cursor = end
        while cursor < len(text) and unicodedata.combining(text[cursor]) != 0:
            cursor += 1
        if cursor < len(text) and _ARABIC_LETTER_RE.match(text, cursor):
            return True
    if start > 0 and unicodedata.combining(text[start - 1]) != 0:
        cursor = start - 1
        while cursor > 0 and unicodedata.combining(text[cursor - 1]) != 0:
            cursor -= 1
        if cursor > 0 and _ARABIC_LETTER_RE.match(text, cursor - 1):
            return True
    return False


@dataclass(frozen=True)
class ContextCandidate:
    """One document-supported candidate and its context features."""

    word: str
    edit_distance: int
    document_frequency: int
    phrase_support: int
    phrase_sides: int
    word_score: float
    character_score: float
    margin: float
    frequency_score: float = 0.0
    phrase_score: float = 0.0
    character_gain: float = 0.0
    word_trigram_support: int = 0
    paragraph_frequency: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ContextDecision:
    """A compatibility view of one context attempt."""

    observed: str
    replacement: str | None
    left_context: str | None
    right_context: str | None
    accepted: bool
    reason: str
    candidates: tuple[ContextCandidate, ...] = ()
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return payload


@dataclass(frozen=True)
class ContextRepair:
    """Result of one context/evidence pass."""

    text: str
    decisions: tuple[ContextDecision, ...] = ()
    confidence: float = 1.0
    fusion_decisions: tuple[EvidenceDecision, ...] = ()

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
            "fusion_decisions": [decision.to_dict() for decision in self.fusion_decisions],
        }


class DocumentContext:
    """A compact model learned from one document and used as evidence.

    The model stores word frequencies, bigrams, trigrams, character trigrams,
    character 4-grams, and paragraph-local counts.  It never creates a repair
    outside the document vocabulary unless another source supplies a candidate;
    authorization is delegated to :class:`arafix.evidence.EvidenceFusion`.
    """

    def __init__(
        self,
        text: str,
        *,
        min_frequency: int = 3,
        min_phrase_support: int = 2,
        max_edit_distance: int = 1,
        candidate_generator: CandidateGenerator | None = None,
        evidence_fusion: EvidenceFusion | None = None,
        negative_evidence: NegativeEvidenceModel | None = None,
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
        self.text = text
        tokens = tuple(_TOKEN_RE.findall(text))
        word_tokens = tuple(_WORD_RE.findall(text))
        self.tokens = tokens
        self.word_counts = Counter(word_tokens)
        self.vocabulary = {
            word
            for word, count in self.word_counts.items()
            if len(word) >= 3 and count >= min_frequency
        }
        phrase_tokens = word_tokens
        self.phrase_counts = Counter(zip(phrase_tokens, phrase_tokens[1:]))
        self.word_trigram_counts = Counter(
            zip(phrase_tokens, phrase_tokens[1:], phrase_tokens[2:])
        )
        self.character_counts = Counter(
            gram for word in word_tokens for gram in self._character_ngrams(word, 3)
        )
        self.character_4_counts = Counter(
            gram for word in word_tokens for gram in self._character_ngrams(word, 4)
        )
        self.character_total = sum(self.character_counts.values())
        self.character_4_total = sum(self.character_4_counts.values())
        self.max_frequency = max(self.word_counts.values(), default=1)
        self._paragraph_counts = tuple(
            Counter(_TOKEN_RE.findall(paragraph))
            for paragraph in text.split("\n\n")
        ) or (Counter(),)
        self._words_by_length: dict[int, tuple[str, ...]] = {
            length: tuple(sorted(word for word in self.vocabulary if len(word) == length))
            for length in {len(word) for word in self.vocabulary}
        }

        if candidate_generator is None:
            from .evidence import CandidateGenerator

            # Context remains the historical safe default. Character confusion
            # candidates are available through an explicitly injected generator
            # so they cannot compete with document evidence unexpectedly.
            candidate_generator = CandidateGenerator()
        if evidence_fusion is None:
            from .evidence import EvidenceFusion

            evidence_fusion = EvidenceFusion()
        if negative_evidence is None:
            from .evidence import NegativeEvidenceModel

            negative_evidence = NegativeEvidenceModel()
        self.candidate_generator = candidate_generator
        self.evidence_fusion = evidence_fusion
        self.negative_evidence = negative_evidence

    @classmethod
    def from_texts(
        cls,
        texts: Iterable[str],
        *,
        min_frequency: int = 3,
        min_phrase_support: int = 2,
        candidate_generator: CandidateGenerator | None = None,
        evidence_fusion: EvidenceFusion | None = None,
        negative_evidence: NegativeEvidenceModel | None = None,
    ) -> DocumentContext:
        """Build one model from page/block texts in their supplied order."""
        return cls(
            "\n".join(texts),
            min_frequency=min_frequency,
            min_phrase_support=min_phrase_support,
            candidate_generator=candidate_generator,
            evidence_fusion=evidence_fusion,
            negative_evidence=negative_evidence,
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

    def _character_score(self, word: str, n: int = 3) -> float:
        counts = self.character_counts if n == 3 else self.character_4_counts
        total = self.character_total if n == 3 else self.character_4_total
        grams = self._character_ngrams(word, n)
        if not grams or not total:
            return 0.0
        denominator = total + len(grams)
        return sum(math.log((counts[gram] + 1.0) / denominator) for gram in grams) / len(grams)

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
        return min(1.0, math.log1p(support) / math.log1p(self.max_frequency))

    def _word_trigram_support(
        self,
        left: str | None,
        candidate: str,
        right: str | None,
    ) -> int:
        if left is None or right is None:
            return 0
        return self.word_trigram_counts[(left, candidate, right)]

    def _paragraph_frequency(self, word: str, paragraph_index: int | None) -> int:
        if paragraph_index is None:
            return 0
        if paragraph_index < 0 or paragraph_index >= len(self._paragraph_counts):
            return 0
        return self._paragraph_counts[paragraph_index][word]

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
        *,
        paragraph_index: int | None = None,
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
            character_gain = character_score - observed_character
            word_trigram_support = self._word_trigram_support(left, candidate, right)
            paragraph_frequency = self._paragraph_frequency(candidate, paragraph_index)
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
                    word_score=max(0.0, min(1.0, score)),
                    character_score=character_score,
                    margin=score - observed_score,
                    frequency_score=frequency_score,
                    phrase_score=phrase_score,
                    character_gain=character_gain,
                    word_trigram_support=word_trigram_support,
                    paragraph_frequency=paragraph_frequency,
                )
            )
        ranked.sort(
            key=lambda candidate: (
                candidate.word_score,
                candidate.document_frequency,
                candidate.phrase_support,
                candidate.word,
            ),
            reverse=True,
        )
        return tuple(ranked)

    def repair(self, text: str, *, min_margin: float = 0.12) -> ContextRepair:
        """Generate and fuse evidence; apply only SAFE decisions."""
        matches = list(_WORD_RE.finditer(text))
        if not matches:
            return ContextRepair(text=text)
        tokens = [match.group(0) for match in matches]
        decisions: list[ContextDecision] = []
        fusion_decisions: list[EvidenceDecision] = []
        replacements: list[tuple[int, int, str]] = []
        margins: list[float] = []
        for index, match in enumerate(matches):
            observed = match.group(0)
            if _touches_combining_mark(text, match.start(), match.end()):
                continue
            if observed in self.vocabulary:
                continue
            left = tokens[index - 1] if index else None
            right = tokens[index + 1] if index + 1 < len(tokens) else None
            paragraph_index = text.count("\n\n", 0, match.start())
            ranked = self.rank(
                observed, left, right, paragraph_index=paragraph_index
            )
            glyph_candidates: dict[str, float] = {}
            if not ranked and not glyph_candidates:
                continue
            candidates = self.candidate_generator.generate(
                observed,
                document_context=self,
                left=left,
                right=right,
                paragraph_index=paragraph_index,
                glyph_candidates=glyph_candidates,
            )
            negatives = self.negative_evidence.inspect(text, match.start(), match.end())
            fused = self.evidence_fusion.decide(
                observed,
                candidates,
                negative_evidence=negatives,
                min_margin=min_margin / 2.0,
            )
            fusion_decisions.append(fused)
            if not candidates:
                continue
            candidate_by_word = {candidate.word: candidate for candidate in ranked}
            compatibility_candidates = tuple(
                candidate_by_word[item.text]
                for item in fused.candidates
                if item.text in candidate_by_word
            )
            decision = ContextDecision(
                observed=observed,
                replacement=fused.replacement,
                left_context=left,
                right_context=right,
                accepted=fused.decision is RepairDecision.SAFE,
                reason=fused.reason,
                candidates=compatibility_candidates or ranked[:5],
                evidence=fused.to_dict(),
            )
            decisions.append(decision)
            if fused.decision is RepairDecision.SAFE and fused.replacement:
                replacements.append((match.start(), match.end(), fused.replacement))
                margins.append(fused.margin)

        if not replacements:
            return ContextRepair(
                text=text,
                decisions=tuple(decisions),
                fusion_decisions=tuple(fusion_decisions),
            )
        chunks: list[str] = []
        cursor = 0
        for start, end, replacement in replacements:
            chunks.append(text[cursor:start])
            chunks.append(replacement)
            cursor = end
        chunks.append(text[cursor:])
        confidence = min(1.0, 0.85 + 0.15 * min(1.0, sum(margins) / len(margins)))
        return ContextRepair(
            text="".join(chunks),
            decisions=tuple(decisions),
            confidence=confidence,
            fusion_decisions=tuple(fusion_decisions),
        )
