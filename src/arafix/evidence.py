"""Candidate generation and conservative evidence fusion.

The module separates *what could be a repair* from *whether it is safe*.  All
components are dependency-free and deterministic.  A detector may contribute a
candidate or a score, but only :class:`EvidenceFusion` can authorize a change.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Optional, cast

from .audit import RepairDecision

if TYPE_CHECKING:
    from .context import DocumentContext

__all__ = [
    "Candidate",
    "CandidateGenerator",
    "CharacterConfusionModel",
    "Confusion",
    "EvidenceDecision",
    "EvidenceFusion",
    "GlyphEvidence",
    "NegativeEvidence",
    "NegativeEvidenceModel",
]


@dataclass(frozen=True)
class Confusion:
    """One observed-to-candidate confusion with provenance and cost."""

    observed: str
    candidate: str
    source: str = "character"
    cost: float = 0.5
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.observed:
            raise ValueError("confusion observed must not be empty")
        if not self.candidate:
            raise ValueError("confusion candidate must not be empty")
        if not 0.0 <= self.cost <= 1.0:
            raise ValueError("confusion cost must be between 0 and 1")

    @property
    def score(self) -> float:
        return 1.0 - self.cost

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_DEFAULT_CHARACTER_CONFUSIONS: tuple[Confusion, ...] = (
    Confusion("ة", "ه", source="character", cost=0.65, detail="Arabic letter-shape confusion"),
    Confusion("ى", "ي", source="character", cost=0.65, detail="Arabic letter-shape confusion"),
    Confusion("ي", "ى", source="character", cost=0.75, detail="Arabic letter-shape confusion"),
    Confusion("ا", "أ", source="character", cost=0.80, detail="hamza omission confusion"),
    Confusion("ب", "ت", source="character", cost=0.90, detail="nearby glyph confusion"),
    Confusion("ت", "ث", source="character", cost=0.90, detail="nearby glyph confusion"),
    Confusion("د", "ذ", source="character", cost=0.90, detail="nearby glyph confusion"),
    Confusion("س", "ش", source="character", cost=0.90, detail="nearby glyph confusion"),
    Confusion("ص", "ض", source="character", cost=0.90, detail="nearby glyph confusion"),
)


class CharacterConfusionModel:
    """Generate character-level hypotheses without deciding their validity.

    The model is deliberately not enabled by :class:`PipelineConfig` by
    default.  Its output is useful only when an independent evidence source,
    such as document context or a glyph map, agrees with it.
    """

    def __init__(self, confusions: Iterable[Confusion] = ()) -> None:
        self.confusions = tuple(confusions)
        by_observed: dict[str, list[Confusion]] = {}
        for confusion in self.confusions:
            by_observed.setdefault(confusion.observed, []).append(confusion)
        self._by_observed = {
            observed: tuple(items) for observed, items in by_observed.items()
        }

    @classmethod
    def default(cls) -> CharacterConfusionModel:
        """Return the explicit Arabic confusions used as opt-in seeds."""
        return cls(_DEFAULT_CHARACTER_CONFUSIONS)

    def candidates(self, observed: str) -> tuple[Confusion, ...]:
        """Return word candidates formed by the configured substitutions."""
        output: dict[tuple[str, str], Confusion] = {}
        for old, confusions in self._by_observed.items():
            for index, char in enumerate(observed):
                if char != old:
                    continue
                for confusion in confusions:
                    candidate = observed[:index] + confusion.candidate + observed[index + 1 :]
                    output[(candidate, confusion.source)] = Confusion(
                        observed=observed,
                        candidate=candidate,
                        source=confusion.source,
                        cost=confusion.cost,
                        detail=confusion.detail,
                    )
        return tuple(output.values())

    def to_dict(self) -> dict[str, object]:
        return {"confusions": [confusion.to_dict() for confusion in self.confusions]}


@dataclass(frozen=True)
class GlyphEvidence:
    """Font/glyph observation that can support, but never force, a candidate."""

    observed: str
    candidate: str
    score: float
    font: str | None = None
    glyph_id: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    source: str = "glyph"

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("glyph evidence score must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Candidate:
    """A possible replacement.  It contains evidence inputs, never a decision."""

    observed: str
    text: str
    sources: tuple[str, ...] = ()
    edit_distance: int | None = None
    cost: float | None = None
    signals: tuple[tuple[str, float], ...] = ()
    details: tuple[str, ...] = ()

    def signal_map(self) -> dict[str, float]:
        return dict(self.signals)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["signals"] = {name: value for name, value in self.signals}
        return payload


@dataclass(frozen=True)
class NegativeEvidence:
    """A reason to preserve text or lower confidence in a repair."""

    reason: str
    score: float
    detail: str = ""
    source: str = "negative"

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("negative evidence score must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class NegativeEvidenceModel:
    """Conservative preserve-because checks for code and protected islands."""

    _URL_OR_EMAIL = re.compile(r"(?:https?://|www\.|[\w.+-]+@[\w.-]+\.)", re.I)
    _ASCII_IDENTIFIER = re.compile(r"[A-Za-z0-9_]")
    _QUOTES = "\"'`«»“”‘’"

    def inspect(self, text: str, start: int, end: int) -> tuple[NegativeEvidence, ...]:
        token = text[start:end]
        nearby = text[max(0, start - 32) : min(len(text), end + 32)]
        evidence: list[NegativeEvidence] = []
        if self._URL_OR_EMAIL.search(nearby):
            evidence.append(
                NegativeEvidence("url_or_email", 1.0, "URL or email island surrounds the span")
            )
        if any(char in token for char in "._:/\\") or "--" in token:
            evidence.append(
                NegativeEvidence("identifier_or_path", 0.95, "identifier/path punctuation")
            )
        if (start > 0 and text[start - 1] in self._QUOTES) or (
            end < len(text) and text[end] in self._QUOTES
        ):
            evidence.append(
                NegativeEvidence("quoted_text", 0.45, "quoted span is preserved by default")
            )
        if (start > 0 and self._ASCII_IDENTIFIER.fullmatch(text[start - 1])) or (
            end < len(text) and self._ASCII_IDENTIFIER.fullmatch(text[end])
        ):
            evidence.append(
                NegativeEvidence(
                    "code_or_identifier_island",
                    0.9,
                    "adjacent Latin/identifier character",
                )
            )
        return tuple(evidence)


class CandidateGenerator:
    """Collect candidates from independent sources without choosing one."""

    def __init__(
        self,
        *,
        confusion_model: CharacterConfusionModel | None = None,
        pdf_confusions: Iterable[Confusion] = (),
    ) -> None:
        self.confusion_model = confusion_model
        self.pdf_confusions = tuple(pdf_confusions)

    @classmethod
    def with_pdf_confusions(
        cls,
        *,
        confusion_model: CharacterConfusionModel | None = None,
    ) -> CandidateGenerator:
        """Build a generator seeded from the existing closed PDF list."""
        from .pdf_confusions import (
            THUMB_RED_CONFUSIONS,
            WHOLE_FORM_CONFUSIONS,
            YE_REH_CONFUSIONS,
        )

        pairs = WHOLE_FORM_CONFUSIONS + YE_REH_CONFUSIONS + THUMB_RED_CONFUSIONS
        return cls(
            confusion_model=confusion_model,
            pdf_confusions=(
                Confusion(old, new, source="pdf_confusion", cost=0.20)
                for old, new in pairs
            ),
        )

    @staticmethod
    def _merge(
        bucket: dict[str, dict[str, object]],
        *,
        observed: str,
        text: str,
        source: str,
        edit_distance: int | None = None,
        cost: float | None = None,
        signals: Mapping[str, float] | None = None,
        detail: str = "",
    ) -> None:
        if not text or text == observed:
            return
        item = bucket.setdefault(
            text,
            {
                "sources": set(),
                "edit_distance": edit_distance,
                "cost": cost,
                "signals": {},
                "details": [],
            },
        )
        sources = item["sources"]
        assert isinstance(sources, set)
        sources.add(source)
        current_distance = cast(Optional[int], item["edit_distance"])
        if edit_distance is not None and (
            current_distance is None or edit_distance < current_distance
        ):
            item["edit_distance"] = edit_distance
        current_cost = cast(Optional[float], item["cost"])
        if cost is not None and (current_cost is None or cost < current_cost):
            item["cost"] = cost
        item_signals = item["signals"]
        assert isinstance(item_signals, dict)
        for name, value in (signals or {}).items():
            item_signals[name] = max(float(value), float(item_signals.get(name, 0.0)))
        if detail:
            details = item["details"]
            assert isinstance(details, list)
            if detail not in details:
                details.append(detail)

    def generate(
        self,
        observed: str,
        *,
        document_context: DocumentContext | None = None,
        left: str | None = None,
        right: str | None = None,
        paragraph_index: int | None = None,
        glyph_candidates: Mapping[str, float] | None = None,
        glyph_evidence: Iterable[GlyphEvidence] = (),
    ) -> tuple[Candidate, ...]:
        bucket: dict[str, dict[str, object]] = {}
        if document_context is not None:
            for context_candidate in document_context.rank(
                observed, left, right, paragraph_index=paragraph_index
            ):
                frequency_score = float(getattr(context_candidate, "frequency_score", 0.0))
                phrase_score = float(getattr(context_candidate, "phrase_score", 0.0))
                trigram_support = float(getattr(context_candidate, "word_trigram_support", 0))
                trigram_score = min(1.0, trigram_support / 2.0)
                paragraph_frequency = float(getattr(context_candidate, "paragraph_frequency", 0))
                paragraph_score = min(
                    1.0,
                    paragraph_frequency / max(1, context_candidate.document_frequency),
                )
                self._merge(
                    bucket,
                    observed=observed,
                    text=context_candidate.word,
                    source="document_vocabulary",
                    edit_distance=context_candidate.edit_distance,
                    signals={
                        "context_score": max(0.0, min(1.0, context_candidate.word_score)),
                        "context_margin": context_candidate.margin,
                        "document_frequency": frequency_score,
                        "document_frequency_count": float(
                            context_candidate.document_frequency
                        ),
                        "phrase_support_count": float(context_candidate.phrase_support),
                        "phrase_sides_count": float(context_candidate.phrase_sides),
                        "both_context_sides": float(bool(left and right)),
                        "phrase_score": phrase_score,
                        "character_score": min(
                            1.0, max(0.0, 0.5 + context_candidate.character_gain)
                        ),
                        "word_trigram_score": trigram_score,
                        "paragraph_score": paragraph_score,
                    },
                )

        if self.confusion_model is not None:
            for confusion in self.confusion_model.candidates(observed):
                self._merge(
                    bucket,
                    observed=observed,
                    text=confusion.candidate,
                    source=confusion.source,
                    cost=confusion.cost,
                    signals={"confusion_score": confusion.score},
                    detail=confusion.detail,
                )

        for confusion in self.pdf_confusions:
            if confusion.observed == observed:
                self._merge(
                    bucket,
                    observed=observed,
                    text=confusion.candidate,
                    source=confusion.source,
                    cost=confusion.cost,
                    signals={"pdf_confusion_score": confusion.score},
                    detail=confusion.detail,
                )

        for glyph_item in glyph_evidence:
            if glyph_item.observed == observed:
                self._merge(
                    bucket,
                    observed=observed,
                    text=glyph_item.candidate,
                    source=glyph_item.source,
                    signals={"glyph_score": glyph_item.score},
                    detail=(
                        f"font={glyph_item.font!r}, glyph_id={glyph_item.glyph_id!r}, "
                        f"bbox={glyph_item.bbox!r}"
                    ),
                )

        for text, score in (glyph_candidates or {}).items():
            self._merge(
                bucket,
                observed=observed,
                text=text,
                source="glyph_evidence",
                signals={"glyph_score": max(0.0, min(1.0, float(score)))},
            )

        candidates: list[Candidate] = []
        for text, item in bucket.items():
            sources = item["sources"]
            signals = item["signals"]
            details = item["details"]
            assert isinstance(sources, set)
            assert isinstance(signals, dict)
            assert isinstance(details, list)
            candidates.append(
                Candidate(
                    observed=observed,
                    text=text,
                    sources=tuple(sorted(sources)),
                    edit_distance=cast(Optional[int], item["edit_distance"]),
                    cost=cast(Optional[float], item["cost"]),
                    signals=tuple(sorted((name, float(value)) for name, value in signals.items())),
                    details=tuple(details),
                )
            )
        return tuple(sorted(candidates, key=lambda item: (item.text, item.sources)))


@dataclass(frozen=True)
class EvidenceDecision:
    """Result of fusing evidence; this is the only object allowed to authorize."""

    observed: str
    replacement: str | None
    decision: RepairDecision
    score: float
    margin: float
    signals: tuple[tuple[str, float], ...] = ()
    negative_evidence: tuple[NegativeEvidence, ...] = ()
    candidates: tuple[Candidate, ...] = ()
    reason: str = ""

    @property
    def status(self) -> str:
        return self.decision.value

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["decision"] = self.decision.value
        payload["signals"] = {name: value for name, value in self.signals}
        payload["negative_evidence"] = [item.to_dict() for item in self.negative_evidence]
        payload["candidates"] = [item.to_dict() for item in self.candidates]
        return payload


class EvidenceFusion:
    """Fuse independent signals and abstain when evidence is insufficient."""

    _WEIGHTS: Mapping[str, float] = {
        "context_score": 0.26,
        "document_frequency": 0.16,
        "phrase_score": 0.20,
        "character_score": 0.10,
        "word_trigram_score": 0.10,
        "paragraph_score": 0.06,
        "confusion_score": 0.08,
        "pdf_confusion_score": 0.08,
        "glyph_score": 0.18,
    }

    def __init__(
        self,
        *,
        min_score: float = 0.50,
        min_margin: float = 0.05,
        min_independent_signals: int = 2,
        negative_unsafe_threshold: float = 0.80,
    ) -> None:
        self.min_score = min_score
        self.min_margin = min_margin
        self.min_independent_signals = min_independent_signals
        self.negative_unsafe_threshold = negative_unsafe_threshold

    def _score(self, candidate: Candidate) -> tuple[float, tuple[tuple[str, float], ...]]:
        signals = candidate.signal_map()
        weighted = [
            (self._WEIGHTS[name], value)
            for name, value in signals.items()
            if name in self._WEIGHTS
        ]
        if not weighted:
            return 0.0, ()
        total_weight = sum(weight for weight, _ in weighted)
        score = sum(weight * value for weight, value in weighted) / total_weight
        return max(0.0, min(1.0, score)), tuple(sorted(signals.items()))

    def decide(
        self,
        observed: str,
        candidates: Iterable[Candidate],
        *,
        negative_evidence: Iterable[NegativeEvidence] = (),
        min_score: float | None = None,
        min_margin: float | None = None,
    ) -> EvidenceDecision:
        candidate_list = tuple(candidates)
        negatives = tuple(negative_evidence)
        ranked = sorted(
            ((self._score(candidate)[0], candidate) for candidate in candidate_list),
            key=lambda item: (item[0], item[1].text),
            reverse=True,
        )
        if not ranked:
            return EvidenceDecision(
                observed=observed,
                replacement=None,
                decision=RepairDecision.UNCERTAIN,
                score=0.0,
                margin=0.0,
                negative_evidence=negatives,
                reason="no-candidates",
            )

        best_score, best = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        margin = best_score - second_score
        signals = best.signal_map()
        negative_score = max((item.score for item in negatives), default=0.0)
        required_score = self.min_score if min_score is None else min_score
        required_margin = self.min_margin if min_margin is None else min_margin
        independent = sum(
            name in self._WEIGHTS and value >= 0.45
            for name, value in signals.items()
        )
        context_score = signals.get("context_score", 0.0)
        context_margin = signals.get("context_margin", 0.0)
        document_frequency_count = signals.get("document_frequency_count", 0.0)
        phrase_support_count = signals.get("phrase_support_count", 0.0)
        context_gate = (
            "document_vocabulary" in best.sources
            and context_score >= 0.25
            and context_margin >= 0.12
            and document_frequency_count >= 3.0
            and phrase_support_count >= 2.0
            and (
                signals.get("both_context_sides", 0.0) == 0.0
                or signals.get("phrase_sides_count", 0.0) >= 2.0
            )
        )
        if negative_score >= self.negative_unsafe_threshold:
            decision = RepairDecision.UNSAFE
            reason = "negative-evidence-protects-island"
        elif (
            (best_score >= required_score or context_gate)
            and margin >= required_margin
            and independent >= self.min_independent_signals
        ):
            decision = RepairDecision.SAFE
            reason = "independent-evidence-agreement"
        else:
            decision = RepairDecision.UNCERTAIN
            reason = "insufficient-score-margin-or-independent-evidence"
        return EvidenceDecision(
            observed=observed,
            replacement=best.text if decision is RepairDecision.SAFE else None,
            decision=decision,
            score=best_score,
            margin=margin,
            signals=tuple(sorted(signals.items())),
            negative_evidence=negatives,
            candidates=tuple(candidate for _, candidate in ranked[:5]),
            reason=reason,
        )
