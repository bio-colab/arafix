from __future__ import annotations

import pytest
from arafix import DocumentContext, PipelineConfig, Stage, extract_pdf, repair_text
from arafix.extractors.base import Extractor, RawPage

PHRASE = "نناقش الطاقة المتجددة في العراق."


def test_context_scoring_recovers_document_phrase() -> None:
    model = DocumentContext(" ".join([PHRASE] * 4))
    result = model.repair("نناقش الطاقة المتجدة في العراق.")

    assert result.text == PHRASE
    assert result.accepted_count == 1
    assert result.decisions[0].replacement == "المتجددة"
    assert result.decisions[0].candidates[0].document_frequency == 4


def test_context_scoring_abstains_without_independent_support() -> None:
    model = DocumentContext("نص عربي مختلف لا يكرر المرشح")
    result = model.repair("نص عربي مختلف لا يكرر المرشح")

    assert result.text == "نص عربي مختلف لا يكرر المرشح"
    assert not result.decisions


def test_context_scoring_is_opt_in_and_auditable() -> None:
    model = DocumentContext(" ".join([PHRASE] * 4))
    source = "نناقش الطاقة المتجدة في العراق."

    plain = repair_text(source)
    disabled = repair_text(source, PipelineConfig(context_model=model))
    audited = repair_text(
        source,
        PipelineConfig(
            context_model=model,
            enable_context_scoring=True,
            audit_mode="full",
        ),
    )

    assert plain.text == source
    assert disabled.text == source
    assert audited.text == PHRASE
    assert Stage.CONTEXT in audited.stages_applied
    assert audited.audit is not None
    assert any(event.rule == "DOCUMENT_CONTEXT_SCORING" for event in audited.audit.events)
    assert audited.reversible_patch is not None
    assert audited.reversible_patch.revert(audited.text) == source


def test_extract_pdf_builds_document_context_and_preserves_page_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeExtractor(Extractor):
        name = "fake-context"

        def pages(self, path: str):
            yield RawPage(number=1, text=" ".join([PHRASE] * 4))
            yield RawPage(number=2, text="نناقش الطاقة المتجدة في العراق.")

        def font_bytes(self, path: str) -> dict[str, bytes]:
            return {}

    import arafix.pipeline as pipeline

    monkeypatch.setattr(pipeline, "get_extractor", lambda _: FakeExtractor())
    document = extract_pdf(
        "unused",
        PipelineConfig(
            extractor="fake-context",
            enable_context_scoring=True,
            enable_lam_alef_repair=False,
            enable_pdf_confusion_repair=False,
            audit_mode="full",
        ),
    )

    page = document.pages[1].repair
    assert page.text == PHRASE
    assert Stage.CONTEXT in page.stages_applied
    assert page.reversible_patch is not None
    assert page.reversible_patch.revert(page.text) == page.original
    assert document.metadata["document_context_pages_touched"] == 1
