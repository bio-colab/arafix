"""
اختبارات 0.7.0 — النظافة، الكتل، معجم الوثيقة، المهايئات.
"""

from __future__ import annotations

import pytest
from arafix import (
    PipelineConfig,
    Stage,
    TextBlock,
    as_blocks,
    count_artifacts,
    fix_any,
    fix_table,
    harvest_document_lexicon,
    repair_blocks,
    repair_text,
    sanitize_extraction,
)
from arafix.adapters import repair_extracted, wrap_callable


class TestHygiene:
    def test_nbsp_becomes_regular_space(self):
        assert sanitize_extraction("دراسة\u00a0مقارنة") == "دراسة مقارنة"

    def test_soft_hyphen_becomes_ascii_hyphen(self):
        assert sanitize_extraction("[أ\u00adج]") == "[أ-ج]"

    def test_thin_space_folded(self):
        assert sanitize_extraction("أ\u2009ب") == "أ ب"

    def test_healthy_untouched(self):
        assert sanitize_extraction("نص سليم 2024") == "نص سليم 2024"

    def test_zero_width_artifacts_are_removed(self):
        raw = "كتاب\u200bجديد\u200f\ufeff"
        assert sanitize_extraction(raw) == "كتابجديد"
        result = repair_text(raw)
        assert result.text == "كتابجديد"
        assert Stage.HYGIENE in result.stages_applied

    def test_zero_width_hygiene_honors_normalize_config(self):
        from arafix import NormalizeConfig

        raw = "كتاب\u200bجديد"
        result = repair_text(raw, PipelineConfig(normalize=NormalizeConfig(strip_zero_width=False)))
        assert result.text == raw

    def test_count_artifacts(self):
        c = count_artifacts("a\u00a0b\u00adc")
        assert c["nbsp_like"] == 1
        assert c["soft_hyphen"] == 1

    def test_repair_text_applies_hygiene_and_reports_stage(self):
        r = repair_text("دراسة\u00a0مقارنة\u00a0في")
        assert r.text == "دراسة مقارنة في"
        assert Stage.HYGIENE in r.stages_applied
        assert any("مسافة" in n for n in r.notes)

    def test_hygiene_can_be_disabled(self):
        r = repair_text(
            "دراسة\u00a0مقارنة",
            PipelineConfig(enable_hygiene=False),
        )
        assert "\u00a0" in r.text
        assert Stage.HYGIENE not in r.stages_applied

    def test_hygiene_plus_presentation_forms(self):
        # مرحبا as PF with NBSP prefix noise
        raw = "\u00a0\ufee3\ufeae\ufea3\ufe92\ufe8e"
        r = repair_text(raw)
        assert r.text.strip() == "مرحبا"

    def test_thousands_sep_becomes_arabic_comma_in_prose(self):
        """macOS CI: Arial/cmap يُخرج U+066C بدل الفاصلة العربية U+060C."""
        raw = "أولاً\u066c ثانياً\u066c ثالثاً؛ ثم توقف!"
        assert sanitize_extraction(raw) == "أولاً، ثانياً، ثالثاً؛ ثم توقف!"
        r = repair_text(raw)
        assert "أولاً، ثانياً، ثالثاً؛ ثم توقف!" in r.text
        assert Stage.HYGIENE in r.stages_applied

    def test_thousands_sep_kept_between_digits(self):
        """لا تُمسّ ١٬٠٠٠ — فاصل الآلاف الحقيقي."""
        raw = "السعر ١\u066c٠٠٠ دينار"
        assert sanitize_extraction(raw) == raw
        assert "\u066c" in repair_text(raw).text

    def test_does_not_early_fold_spacing_damma(self):
        """تشكيل PF يبقى إلى ما بعد العكس — وإلا نشُرت."""
        visual = "\ufe95\ufeae\ufeb8\ufe79\ufee7"
        # hygiene alone must NOT convert FE79 (that would break reverse)
        assert "\ufe79" in sanitize_extraction(visual)
        assert repair_text(visual).text == "نُشرت"


class TestRepairBlocks:
    def test_independent_cells(self):
        """خلية معطوبة لا تُفسد جارةً سليمة — لبّ API الكتل."""
        pf = "\ufee3\ufeae\ufea3\ufe92\ufe8e"
        out = repair_blocks(
            [
                TextBlock(pf, id="bad", role="cell"),
                TextBlock("نص سليم تماماً هنا مع كلمات كافية", id="good", role="cell"),
            ]
        )
        assert out.by_id()["bad"].text == "مرحبا"
        assert out.by_id()["good"].text == "نص سليم تماماً هنا مع كلمات كافية"
        assert not out.by_id()["good"].repair.changed or (
            Stage.HYGIENE not in out.by_id()["good"].repair.stages_applied
            or out.by_id()["good"].text == "نص سليم تماماً هنا مع كلمات كافية"
        )

    def test_accepts_plain_strings(self):
        out = repair_blocks(["\ufee3\ufeae\ufea3\ufe92\ufe8e"])
        assert out.texts == ["مرحبا"]

    def test_accepts_id_text_tuples(self):
        out = repair_blocks([("c1", "\ufee3\ufeae\ufea3\ufe92\ufe8e")])
        assert out.by_id()["c1"].text == "مرحبا"

    def test_accepts_dicts(self):
        out = repair_blocks([{"id": "x", "text": "\ufee3\ufeae\ufea3\ufe92\ufe8e", "role": "cell"}])
        assert out.blocks[0].block.role == "cell"
        assert out.texts[0] == "مرحبا"

    def test_join_and_confidence(self):
        out = repair_blocks(["مرحبا", "عالم"])
        assert "مرحبا" in out.join(" ")
        assert 0.0 <= out.confidence <= 1.0

    def test_rejects_garbage(self):
        with pytest.raises(TypeError):
            repair_blocks([123])  # type: ignore[list-item]


class TestFixTable:
    def test_table_cells_independent(self):
        rows = [
            ["\ufee3\ufeae\ufea3\ufe92\ufe8e", "OK"],
            ["سطر", "\ufee3\ufeae\ufea3\ufe92\ufe8e"],
        ]
        fixed = fix_table(rows)
        assert fixed == [["مرحبا", "OK"], ["سطر", "مرحبا"]]

    def test_as_blocks_ids(self):
        blocks = as_blocks([["a", "b"]])
        assert blocks[0].id == "r0c0"
        assert blocks[1].meta["col"] == 1


class TestDocumentLexicon:
    def test_harvest_collects_words(self):
        vocab = harvest_document_lexicon(["المجلات العلمية", "بحث جديد"])
        assert "المجلات" in vocab
        assert "العلمية" in vocab

    def test_cross_block_lexicon_resolves_ambiguous(self):
        """
        كتلة فيها «المجلات» الصحيحة تعلّم جارةً فيها «المجالت».
        """
        out = repair_blocks(
            [
                TextBlock("نُشرت في المجلات المحكمة هذا العام", id="good"),
                TextBlock("راجع المجالت القديمة أيضاً", id="bad"),
            ],
            PipelineConfig(harvest_document_lexicon=True),
        )
        assert "المجلات" in out.by_id()["bad"].text
        assert "المجالت" not in out.by_id()["bad"].text


class TestAdapters:
    def test_fix_any(self):
        assert fix_any("\ufee3\ufeae\ufea3\ufe92\ufe8e").text == "مرحبا"



    def test_wrap_callable(self):
        def extractor(path: str) -> str:
            return "\ufee3\ufeae\ufea3\ufe92\ufe8e"

        wrapped = wrap_callable(extractor)
        assert wrapped("x.pdf").text == "مرحبا"

    def test_repair_extracted(self):
        assert repair_extracted("مرحبا\u00a0بكم").text == "مرحبا بكم"
