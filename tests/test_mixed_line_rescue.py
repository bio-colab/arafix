"""اختبارات إنقاذ الأسطر المختلطة (P1) — الانعكاس الجزئي داخل صفحة سالمة.

الخلفية المعمارية: التصويت على مستوى النص كله يُغرق الأقلية المعكوسة،
فيمرّ سطرٌ معكوسٌ في صفحةٍ سليمة بلا علاج (قياساً: درجة الصفحة ‎-0.53
والعتبة 0.30). ``rescue_mixed_lines`` يفحص كل سطرٍ بالشواهد والعتبة
نفسيهما ولا يعكس إلا من اجتازها وحده.
"""

from __future__ import annotations

import pytest

from arafix import PipelineConfig, Stage, repair_text
from arafix.diagnose import detect_visual_order
from arafix.normalize import fold_simple_forms

HEALTHY_LINES = [
    "تتناول هذه الدراسة أهم جوانب النظرية البنيوية في النقد الأدبي الحديث",
    "حيث يرصد الكاتب تطور المدرسة منذ نشأتها في عشرينيات القرن الماضي",
    "ويبحث أثرها العميق في الدراسات اللغوية والأنثروبولوجيا المعاصرة",
]

# «الكتاب الذي كان يتفضل درجاته الإلهام من اللغة والأدب» معكوسةً حرفياً
REVERSED_LINE = "ةماعلاو ةغللا نم راداهإ هتاجرد لضفت ناوك يذلا باتكلا"


def _mixed_page() -> str:
    return "\n".join([HEALTHY_LINES[0], REVERSED_LINE, HEALTHY_LINES[1], HEALTHY_LINES[2]])


@pytest.fixture()
def rescue_cfg():
    return PipelineConfig(rescue_mixed_lines=True)


class TestMixedLineRescue:
    def test_reversed_line_repaired_when_enabled(self, rescue_cfg):
        page = _mixed_page()
        r = repair_text(page, rescue_cfg)
        assert REVERSED_LINE not in r.text
        # الأسطر السليمة لم تُمسّ
        for h in HEALTHY_LINES:
            assert h in r.text

    def test_default_behavior_preserved_when_disabled(self):
        """الافتراضي مطابق للسلوك التاريخي — لا كسر لمن لا يفعّل."""
        page = _mixed_page()
        r = repair_text(page, PipelineConfig())
        assert REVERSED_LINE in r.text

    def test_stage_and_note_recorded(self, rescue_cfg):
        r = repair_text(_mixed_page(), rescue_cfg)
        assert Stage.REORDER in r.stages_applied
        assert any("إنقاذ مختلط" in n for n in r.notes)

    def test_audit_trail_records_rule(self):
        cfg = PipelineConfig(rescue_mixed_lines=True, audit_mode="summary")
        r = repair_text(_mixed_page(), cfg)
        assert r.audit is not None
        rules = [e.rule for e in r.audit.events]
        assert "MIXED_LINE_RESCUE" in rules

    def test_healthy_page_untouched_in_both_modes(self, rescue_cfg):
        page = "\n".join(HEALTHY_LINES * 3)
        assert repair_text(page).text == page
        assert repair_text(page, rescue_cfg).text == page

    def test_fully_reversed_page_unaffected_by_flag(self, rescue_cfg):
        rev_page = "\n".join(
            [
                "ةماعلاو ةغللا نم راداهإ هتاجرد لضفت ناوك يذلا باتكلا",
                "ةيبنلالاو ةيغللا تاساردلا ىف هريثأتلا قيبطتسملا رصع نم رظيرت",
            ]
        )
        expected = repair_text(rev_page, PipelineConfig()).text
        got = repair_text(rev_page, rescue_cfg).text
        assert got == expected  # المسار القديم يعالجها؛ الإنقاذ لا يمرّ أصلاً

    def test_latin_heavy_lines_untouched(self, rescue_cfg):
        page = (
            HEALTHY_LINES[0]
            + "\n"
            + "The Prague Linguistic Circle was founded in 1926 by Mathesius"
            + "\n"
            + HEALTHY_LINES[1]
        )
        r = repair_text(page, rescue_cfg)
        assert "The Prague Linguistic Circle" in r.text
        for h in (HEALTHY_LINES[0], HEALTHY_LINES[1]):
            assert h in r.text

    def test_short_line_without_proof_not_rescued(self, rescue_cfg):
        """سطر قصير بلا برهان وصل: حارس كفاية العيّنة يحرسه."""
        tiny_reversed = "ةماعلاو"
        page = HEALTHY_LINES[0] + "\n" + tiny_reversed + "\n" + HEALTHY_LINES[1]
        r = repair_text(page, rescue_cfg)
        assert tiny_reversed in r.text

    def test_idempotence_with_flag_on(self, rescue_cfg):
        page = _mixed_page()
        once = repair_text(page, rescue_cfg)
        twice = repair_text(once.text, rescue_cfg)
        assert twice.text == once.text

    def test_confidence_is_weakest_rescued_line(self, rescue_cfg):
        r = repair_text(_mixed_page(), rescue_cfg)
        assert r.confidence >= 0.5  # درجات أسطر الإنقاذ عالية هنا


class TestPerLineDetection:
    def test_reversed_line_scores_above_threshold_alone(self):
        score, _ = detect_visual_order(fold_simple_forms(REVERSED_LINE))
        assert score > 0.30

    def test_healthy_line_scores_below_threshold_alone(self):
        for h in HEALTHY_LINES:
            score, _ = detect_visual_order(fold_simple_forms(h))
            assert score <= 0.30, f"سطر سليم تجاوز العتبة: {score:.2f}"
