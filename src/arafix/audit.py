"""Auditable, deterministic recovery decisions and reversible text patches.

The audit layer is deliberately optional.  It records evidence about changes
without changing the text produced by the existing repair pipeline.  Runtime
code uses only the Python standard library.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Any

__all__ = [
    "AuditMode",
    "RepairDecision",
    "EvidenceItem",
    "AuditEvent",
    "PatchOperation",
    "Patch",
    "RepairAudit",
    "AuditTrail",
    "sha256_text",
]


class AuditMode(str, Enum):
    """Amount of provenance retained by the repair pipeline."""

    OFF = "off"
    SUMMARY = "summary"
    FULL = "full"

    @classmethod
    def coerce(cls, value: AuditMode | str | None) -> AuditMode:
        if value is None:
            return cls.OFF
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except ValueError as exc:
            choices = ", ".join(item.value for item in cls)
            raise ValueError(f"audit_mode must be one of: {choices}") from exc


class RepairDecision(str, Enum):
    """Decision safety class for a repair or abstention."""

    SAFE = "safe"
    UNCERTAIN = "uncertain"
    UNSAFE = "unsafe"


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest of UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class EvidenceItem:
    """One inspectable observation supporting a decision."""

    name: str
    value: float | int | str | bool | None = None
    detail: str = ""
    source: str = "pipeline"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": _json_value(self.value),
            "detail": self.detail,
            "source": self.source,
        }


@dataclass(frozen=True)
class AuditEvent:
    """A single changed span or stage-level decision."""

    event_id: int
    stage: str
    rule: str
    decision: RepairDecision
    before: str | None = None
    after: str | None = None
    span_before: tuple[int, int] | None = None
    span_after: tuple[int, int] | None = None
    evidence: tuple[EvidenceItem, ...] = ()
    confidence: float | None = None
    reversible: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "stage": self.stage,
            "rule": self.rule,
            "decision": self.decision.value,
            "before": self.before,
            "after": self.after,
            "span_before": list(self.span_before) if self.span_before else None,
            "span_after": list(self.span_after) if self.span_after else None,
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence,
            "reversible": self.reversible,
            "metadata": _json_value(dict(self.metadata)),
        }


@dataclass(frozen=True)
class PatchOperation:
    """One non-overlapping replacement in before and after coordinates."""

    start_before: int
    end_before: int
    start_after: int
    end_after: int
    before: str
    after: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_before": self.start_before,
            "end_before": self.end_before,
            "start_after": self.start_after,
            "end_after": self.end_after,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True)
class Patch:
    """Hash-guarded reversible patch between two complete text versions."""

    original_sha256: str
    repaired_sha256: str
    operations: tuple[PatchOperation, ...] = ()
    format_version: str = "arafix.patch.v1"

    @classmethod
    def from_texts(cls, original: str, repaired: str) -> Patch:
        operations: list[PatchOperation] = []
        matcher = SequenceMatcher(None, original, repaired, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            operations.append(
                PatchOperation(
                    start_before=i1,
                    end_before=i2,
                    start_after=j1,
                    end_after=j2,
                    before=original[i1:i2],
                    after=repaired[j1:j2],
                )
            )
        return cls(
            original_sha256=sha256_text(original),
            repaired_sha256=sha256_text(repaired),
            operations=tuple(operations),
        )

    @property
    def changed(self) -> bool:
        return bool(self.operations)

    def apply(self, text: str) -> str:
        """Apply the patch only if the source hash matches exactly."""
        if sha256_text(text) != self.original_sha256:
            raise ValueError("patch source SHA-256 does not match original_sha256")
        out = text
        for op in reversed(self.operations):
            if out[op.start_before : op.end_before] != op.before:
                raise ValueError("patch source span does not match its recorded text")
            out = out[: op.start_before] + op.after + out[op.end_before :]
        if sha256_text(out) != self.repaired_sha256:
            raise ValueError("patched text SHA-256 does not match repaired_sha256")
        return out

    def revert(self, text: str) -> str:
        """Revert the patch only if the current hash matches the repaired text."""
        if sha256_text(text) != self.repaired_sha256:
            raise ValueError("patch target SHA-256 does not match repaired_sha256")
        out = text
        for op in reversed(self.operations):
            if out[op.start_after : op.end_after] != op.after:
                raise ValueError("patch target span does not match its recorded text")
            out = out[: op.start_after] + op.before + out[op.end_after :]
        if sha256_text(out) != self.original_sha256:
            raise ValueError("reverted text SHA-256 does not match original_sha256")
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format_version,
            "original_sha256": self.original_sha256,
            "repaired_sha256": self.repaired_sha256,
            "operations": [op.to_dict() for op in self.operations],
        }


@dataclass(frozen=True)
class RepairAudit:
    """Complete audit result for one repair invocation."""

    original_sha256: str
    repaired_sha256: str
    mode: AuditMode
    events: tuple[AuditEvent, ...] = ()
    abstentions: tuple[AuditEvent, ...] = ()
    patch: Patch | None = None
    schema: str = "arafix.recovery-audit.v1"

    @property
    def changed(self) -> bool:
        return self.original_sha256 != self.repaired_sha256

    @property
    def changed_events(self) -> int:
        return len(self.events)

    @property
    def abstention_count(self) -> int:
        return len(self.abstentions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "mode": self.mode.value,
            "original_sha256": self.original_sha256,
            "repaired_sha256": self.repaired_sha256,
            "changed": self.changed,
            "changed_events": self.changed_events,
            "abstention_count": self.abstention_count,
            "events": [event.to_dict() for event in self.events],
            "abstentions": [event.to_dict() for event in self.abstentions],
            "patch": self.patch.to_dict() if self.patch else None,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)


class AuditTrail:
    """Mutable builder used internally by the pipeline."""

    def __init__(self, original: str, mode: AuditMode | str | None = None) -> None:
        self.original = original
        self.mode = AuditMode.coerce(mode)
        self._events: list[AuditEvent] = []
        self._abstentions: list[AuditEvent] = []
        self._next_id = 1

    @property
    def enabled(self) -> bool:
        return self.mode is not AuditMode.OFF

    def _event_text(self, text: str) -> str | None:
        return text if self.mode is AuditMode.FULL else None

    def record(
        self,
        before: str,
        after: str,
        *,
        stage: str,
        rule: str,
        decision: RepairDecision = RepairDecision.SAFE,
        evidence: Iterable[EvidenceItem] = (),
        confidence: float | None = None,
        reversible: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """Record changed spans and return ``after`` unchanged."""
        if not self.enabled or before == after:
            return after
        if decision is not RepairDecision.SAFE:
            raise ValueError("a changed text must be recorded as SAFE")
        evidence_tuple = tuple(evidence)
        if self.mode is AuditMode.SUMMARY:
            self._events.append(
                AuditEvent(
                    event_id=self._next_id,
                    stage=stage,
                    rule=rule,
                    decision=decision,
                    evidence=evidence_tuple,
                    confidence=confidence,
                    reversible=False,
                    metadata={**dict(metadata or {}), "changed": True},
                )
            )
            self._next_id += 1
            return after

        matcher = SequenceMatcher(None, before, after, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            self._events.append(
                AuditEvent(
                    event_id=self._next_id,
                    stage=stage,
                    rule=rule,
                    decision=decision,
                    before=self._event_text(before[i1:i2]),
                    after=self._event_text(after[j1:j2]),
                    span_before=(i1, i2),
                    span_after=(j1, j2),
                    evidence=evidence_tuple,
                    confidence=confidence,
                    reversible=reversible,
                    metadata=dict(metadata or {}),
                )
            )
            self._next_id += 1
        return after

    def abstain(
        self,
        *,
        stage: str,
        rule: str,
        decision: RepairDecision,
        evidence: Iterable[EvidenceItem] = (),
        confidence: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a no-op uncertain/unsafe decision."""
        if not self.enabled:
            return
        if decision is RepairDecision.SAFE:
            raise ValueError("SAFE is not an abstention decision")
        self._abstentions.append(
            AuditEvent(
                event_id=self._next_id,
                stage=stage,
                rule=rule,
                decision=decision,
                evidence=tuple(evidence),
                confidence=confidence,
                reversible=False,
                metadata=dict(metadata or {}),
            )
        )
        self._next_id += 1

    def finalize(self, repaired: str) -> RepairAudit | None:
        if not self.enabled:
            return None
        patch = Patch.from_texts(self.original, repaired) if self.mode is AuditMode.FULL else None
        return RepairAudit(
            original_sha256=sha256_text(self.original),
            repaired_sha256=sha256_text(repaired),
            mode=self.mode,
            events=tuple(self._events),
            abstentions=tuple(self._abstentions),
            patch=patch,
        )
