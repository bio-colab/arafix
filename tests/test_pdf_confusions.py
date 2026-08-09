"""
PDF confusion repairs — closed list from published Arabic books.

Evidence (transparent): benchmarks/independent_eval Safahat books
(https://www.safahat.org/), not AI-generated fixtures.
"""

from __future__ import annotations

from arafix import Stage, repair_text
from arafix.pdf_confusions import repair_pdf_confusions


class TestAlMeemArticle:
    def test_mutahaf(self):
        r = repair_pdf_confusions("زيارة املتاحف وصالات")
        assert "المتاحف" in r.text
        assert r.al_meem_fixes >= 1

    def test_maseeh(self):
        assert repair_pdf_confusions("أنصاراملسيح").text == "أنصارالمسيح"

    def test_does_not_break_kamilah(self):
        # كاملة contains امل but must not become كالمة
        assert repair_pdf_confusions("بالكاملة").text == "بالكاملة"

    def test_glued_after_prefix_word(self):
        assert "المسيح" in repair_pdf_confusions("أنصاراملسيح").text


class TestYeReh:
    def test_kabir_kathir_ghayr(self):
        r = repair_pdf_confusions("اهتمامٍكبريعندي وكثريًا وغري ذلك")
        assert "كبير" in r.text
        assert "كثيرًا" in r.text
        assert "غير" in r.text
        assert r.ye_reh_fixes >= 3

    def test_no_false_positive_inside_stem(self):
        # مغري must not become مغير via bare غري replace
        assert "مغري" in repair_pdf_confusions("شيء مغري جدا").text
        assert "مغير" not in repair_pdf_confusions("شيء مغري جدا").text


class TestPipelineHook:
    def test_stage_fires_on_confusion(self):
        # Already-normalized Arabic (no PF) still gets confusion pass
        r = repair_text("املتاحف وكبري")
        assert "المتاحف" in r.text
        assert "كبير" in r.text
        assert Stage.REPAIR_PDF_CONFUSIONS in r.stages_applied

    def test_can_disable(self):
        from arafix import PipelineConfig

        r = repair_text(
            "املتاحف",
            PipelineConfig(enable_pdf_confusion_repair=False),
        )
        assert r.text == "املتاحف"
        assert Stage.REPAIR_PDF_CONFUSIONS not in r.stages_applied
