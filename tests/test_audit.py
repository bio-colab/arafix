import json
from pathlib import Path

import pytest
from arafix import (
    AuditMode,
    Patch,
    PipelineConfig,
    RepairDecision,
    RepairResult,
    extract_pdf,
    repair_text,
)


def test_patch_apply_and_revert_are_hash_guarded() -> None:
    original = "GDP2024، نص"
    repaired = "GDP 2024، نص"
    patch = Patch.from_texts(original, repaired)

    assert patch.changed
    assert patch.apply(original) == repaired
    assert patch.revert(repaired) == original
    with pytest.raises(ValueError, match="original_sha256"):
        patch.apply("نص مختلف")
    with pytest.raises(ValueError, match="repaired_sha256"):
        patch.revert(original)


def test_full_audit_is_deterministic_and_does_not_change_text() -> None:
    source = "دراسة\u00a0مقارنة المادة(١٧)"
    plain = repair_text(source)
    audited = repair_text(source, PipelineConfig(audit_mode=AuditMode.FULL))

    assert audited.text == plain.text
    assert audited.audit is not None
    assert audited.audit.schema == "arafix.recovery-audit.v1"
    assert audited.audit.original_sha256 != audited.audit.repaired_sha256
    assert audited.reversible_patch is not None
    assert audited.reversible_patch.revert(audited.text) == source
    assert audited.audit.to_json() == audited.audit.to_json()

    payload = json.loads(audited.audit.to_json())
    assert payload["events"]
    assert all(event["decision"] == "safe" for event in payload["events"])
    assert all(event["reversible"] for event in payload["events"])


def test_summary_keeps_spans_without_retaining_changed_text() -> None:
    result = repair_text("دراسة\u00a0مقارنة", PipelineConfig(audit_mode="summary"))

    assert result.audit is not None
    assert result.audit.mode is AuditMode.SUMMARY
    assert result.audit.events
    assert all(event.before is None and event.after is None for event in result.audit.events)
    assert result.reversible_patch is None


def test_ambiguous_lam_alef_is_recorded_as_abstention() -> None:
    result = repair_text("المجالت", PipelineConfig(audit_mode="full", use_core_lexicon=False))

    assert result.text == "المجالت"
    assert result.audit is not None
    assert any(
        event.rule == "LAM_ALEF_AMBIGUOUS"
        and event.decision is RepairDecision.UNCERTAIN
        for event in result.audit.abstentions
    )


def test_broken_cmap_is_unsafe_and_text_is_preserved() -> None:
    result = repair_text("\ue000 نص", PipelineConfig(audit_mode="full"))

    assert result.text == "\ue000 نص"
    assert result.audit is not None
    assert any(
        event.rule == "BROKEN_CMAP_NOT_RESOLVED_IN_TEXT_MODE"
        and event.decision is RepairDecision.UNSAFE
        for event in result.audit.abstentions
    )


def test_audit_off_has_no_runtime_audit_object() -> None:
    result = repair_text("نص سليم")
    assert isinstance(result, RepairResult)
    assert result.audit is None
    assert result.reversible_patch is None


def test_pdf_page_patch_is_guarded_by_page_original() -> None:
    pdf = Path("tests/fixtures/real_pdf_narrative/file.pdf")
    document = extract_pdf(str(pdf), PipelineConfig(audit_mode="full"))
    page = document.pages[0]

    assert page.repair.audit is not None
    assert page.repair.reversible_patch is not None
    assert page.repair.reversible_patch.revert(page.text) == page.repair.original
