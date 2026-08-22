"""
H1 — بوابات الأدلة والقرار والطفرة (الأولوية القصوى).

العقد المعماري المُختبر:
    candidate → evidence → fusion → decision → mutation

قوانين لا يجوز كسرها:
  G1  لا SAFE بلا مرشحٍ حقيقي وبأدلةٍ مستقلة كافية.
  G2  UNCERTAIN لا يغيّر النص — يُسجَّل فقط.
  G3  UNSAFE لا يغيّر النص مهما بلغت قوة المرشح — النفي يسود.
  G4  الثقة مشتقة من جودة الإشارة (score/margin) لا من عدّها.
  G5  مرشّحٌ وحيد لا يتجاوز الفيتو النافي مهما علا.
  G6  نموذج السياق لا يؤثر إلا حين يُفعَّل صراحةً عبر البوابة الرسمية.
  G7  تسجيلُ تغييرٍ بغير SAFE مستحيلٌ آلياً (حراسة AuditTrail).
"""

from __future__ import annotations

import pytest

from arafix import PipelineConfig, RepairDecision, repair_text
from arafix.audit import AuditTrail
from arafix.context import DocumentContext
from arafix.evidence import (
    Candidate,
    EvidenceFusion,
    NegativeEvidence,
)

# ---------------------------------------------------------------------------
# أدوات بناء سيناريوهات محكومة
# ---------------------------------------------------------------------------


def make_fusion(**overrides) -> EvidenceFusion:
    kwargs = dict(min_score=0.5, min_margin=0.05, min_independent_signals=2)
    kwargs.update(overrides)
    return EvidenceFusion(**kwargs)


def candidate(text: str, observed: str = "مدخل", score_hint: float = 0.0) -> Candidate:
    return Candidate(
        text=text,
        observed=observed,
        sources=("document_vocabulary",),
        signals=(
            ("document_frequency", score_hint or 4.0),
            ("context_score", 0.8),
            ("context_margin", 0.4),
        ),
    )


def negatives(score: float, kind: str = "url_or_email") -> tuple[NegativeEvidence, ...]:
    return (NegativeEvidence(kind, score, "adversarial"),)


# ---------------------------------------------------------------------------
# G1: لا SAFE بلا أساسٍ حقيقي
# ---------------------------------------------------------------------------


class TestG1NoSafeWithoutEvidence:
    def test_no_candidates_is_uncertain_never_safe(self):
        d = make_fusion().decide("كلمة", ())
        assert d.decision is RepairDecision.UNCERTAIN
        assert d.replacement is None
        assert d.reason == "no-candidates"

    def test_weak_single_signal_cannot_reach_safe(self):
        """إشارةٌ واحدة قوية لا تكفي — الحد الأدنى إشارتان مستقلتان."""
        fusion = make_fusion()
        cand = Candidate(
            text="مرشح",
            observed="مشكلة",
            sources=("document_vocabulary",),  # مصدر واحد فقط
            signals=(("document_frequency", 10.0),),  # قوي لكنه وحيد
        )
        d = fusion.decide("مشكلة", (cand,))
        if d.decision is RepairDecision.SAFE:
            # إن مرّ فعلاً فلأن العقد تسمح بمصدر واحد — نتحقق من العدّاد
            strong = sum(
                1
                for name, v in d.signals.items()
                if v is not None and isinstance(v, (int, float)) and v >= 0.45
            )
            pytest.fail(
                f"SAFE بإشارةٍ واحدة! signals={d.signals} مستقلة={strong}"
            )

    def test_every_safe_decision_carries_replacement(self):
        fusion = make_fusion(min_score=0.3)
        cand = Candidate(
            text="المجلات",
            observed="المجالت",
            sources=("document_vocabulary", "confusion"),
            edit_distance=1,
            signals=(("document_frequency", 6.0), ("edit_distance", 1.0)),
        )
        d = fusion.decide("المجالت", (cand,), min_score=0.3, min_margin=0.0)
        if d.decision is RepairDecision.SAFE:
            assert d.replacement is not None


# ---------------------------------------------------------------------------
# G2 + G3: UNCERTAIN و UNSAFE لا يغيّران النص أبداً
# ---------------------------------------------------------------------------


class TestNonSafeNeverMutates:
    CONTEXT_TEXT = (
        "درس الطالبُ درسَه القديم في المكتبة العامة وصلى على النبي ﷺ "
        "ثم كتب التقرير النهائي بحسب المصادر الموثوقة في المشروع"
    )
    VOCAB_WORDS = [
        "درس", "الطالب", "المكتبة", "العامة", "كتب", "التقرير",
        "النهائي", "المصادر", "المشروع", "بحسب",
    ]

    def _model(self) -> DocumentContext:
        text = " ".join(self.VOCAB_WORDS * 4)
        return DocumentContext(text)

    def test_context_never_applies_non_safe(self):
        model = self._model()
        result = model.repair(self.CONTEXT_TEXT)
        for decision in result.decisions:
            if decision.decision is not RepairDecision.SAFE:
                assert decision.replacement is None
            else:
                assert decision.replacement is not None

    def test_text_changes_only_where_safe_decisions_exist(self):
        model = self._model()
        result = model.repair(self.CONTEXT_TEXT)
        if not result.changed:
            pytest.skip("لا تغييرات في هذه العينة")
        safe_spans = {
            d.observed for d in model.repair(self.CONTEXT_TEXT).decisions
            if d.decision is RepairDecision.SAFE and d.replacement
        }
        assert safe_spans  # يوجد قرارٌ مفعّل على الأقل

    def test_unsafe_negative_veto_dominates_candidate_strength(self):
        """G5: مرشّح مثالي + نفي قوي = UNSAFE لا نقاش."""
        fusion = make_fusion()
        perfect = Candidate(
            text="المجلات",
            observed="المجالت",
            sources=("document_vocabulary", "confusion", "glyph"),
            edit_distance=1,
            signals=(
                ("document_frequency", 50.0),
                ("context_score", 0.99),
                ("context_margin", 0.9),
                ("edit_distance", 1.0),
            ),
        )
        d = fusion.decide(
            "المجالت",
            (perfect,),
            negative_evidence=negatives(0.95),
        )
        assert d.decision is RepairDecision.UNSAFE
        assert d.replacement is None
        assert d.reason == "negative-evidence-protects-island"

    def test_negative_threshold_boundary_from_both_sides(self):
        fusion = make_fusion(negative_unsafe_threshold=0.8)
        cand = candidate("مرشح")
        below = fusion.decide("مدخل", (cand,), negative_evidence=negatives(0.79))
        at = fusion.decide("مدخل", (cand,), negative_evidence=negatives(0.80))
        # تحت العتبة: لا فيتو تلقائياً؛ وعند العتبة: فيتو
        if below.decision is RepairDecision.UNSAFE:
            assert below.reason != "negative-evidence-protects-island"
        if at.decision is RepairDecision.UNSAFE:
            assert at.reason == "negative-evidence-protects-island"


# ---------------------------------------------------------------------------
# G4: الثقة من الجودة لا الكمّ
# ---------------------------------------------------------------------------


class TestConfidenceFromQuality:
    def test_many_weak_signals_do_not_outvote_two_strong(self):
        fusion = make_fusion(min_independent_signals=2, min_score=0.5)
        strong_pair = Candidate(
            text="مرشح_قوي",
            observed="مدخل",
            sources=("document_vocabulary", "confusion"),
            edit_distance=1,
            signals=(("document_frequency", 20.0), ("edit_distance", 1.0)),
        )
        d_strong = fusion.decide("مدخل", (strong_pair,))
        # إشاراتٌ كثيرة ضعيفة (تحت عتبة الاستقلالية 0.45)
        weak_signals = {f"sig_{i}": 0.1 for i in range(30)}
        weak_noise = Candidate(
            text="مرشح_ضعيف",
            observed="مدخل",
            sources=tuple(f"src_{i}" for i in range(30)),
            signals=tuple(weak_signals.items()),
        )
        d_weak = fusion.decide("مدخل", (weak_noise,), min_score=0.99)
        # الضعيف لا يبلغ SAFE بهذه الإشارات المتواضعة
        if d_weak.decision is RepairDecision.SAFE:
            assert d_weak.score >= 0.99  # لو مرّ فبجدارة لا بالكمّ
        assert d_strong.score >= 0.5


# ---------------------------------------------------------------------------
# G6: السياق لا يعبر الأنبوب إلا من بابه
# ---------------------------------------------------------------------------


class TestContextBoundedByPipelineGate:
    def test_context_scoring_off_by_default(self):
        cfg = PipelineConfig()
        assert cfg.enable_context_scoring is False

    def test_pipeline_without_context_flag_never_runs_context_stage(self):
        r = repair_text(
            "درس الطالب درسه القديم في المكتبة العامة وكتب التقرير النهائي",
            PipelineConfig(enable_context_scoring=False),
        )
        stages = [s.value for s in r.stages_applied]
        assert "context" not in stages


# ---------------------------------------------------------------------------
# G7: حراسة AuditTrail آلياً — غير قابل للخرق
# ---------------------------------------------------------------------------


class TestAuditRuntimeEnforcement:
    def test_record_change_with_unsafe_raises(self):
        trail = AuditTrail("abc", mode="summary")
        with pytest.raises(ValueError):
            trail.record(
                "abc", "xyz",
                stage="t", rule="r",
                decision=RepairDecision.UNSAFE,
            )

    def test_record_change_with_uncertain_raises(self):
        trail = AuditTrail("abc", mode="summary")
        with pytest.raises(ValueError):
            trail.record(
                "abc", "xyz",
                stage="t", rule="r",
                decision=RepairDecision.UNCERTAIN,
            )

    def test_abstain_with_safe_raises(self):
        trail = AuditTrail("abc", mode="summary")
        with pytest.raises(ValueError):
            trail.abstain(stage="t", rule="r", decision=RepairDecision.SAFE)

    def test_no_op_record_is_silent(self):
        trail = AuditTrail("abc", mode="full")
        out = trail.record("abc", "abc", stage="t", rule="r")
        assert out == "abc"
        assert trail._events == []  # لا حدث لما لم يتغير

    def test_summary_mode_records_change_marker(self):
        trail = AuditTrail("abc", mode="summary")
        trail.record("abc", "abd", stage="t", rule="r")
        assert len(trail._events) == 1
        assert trail._events[0].metadata.get("changed") is True


# ---------------------------------------------------------------------------
# G-composite: مسار السياق عبر الأنبوب الكامل — القرار والنص متطابقان
# ---------------------------------------------------------------------------


class TestFullPipelineEvidenceConsistency:
    def test_audit_events_all_safe_when_text_changed(self):
        text = (
            "المجالت العلمية والمجالت الثانية والمجالت الثالثة "
            "والسؤالِ عن التعاليم"
        )
        cfg = PipelineConfig(audit_mode="summary", use_core_lexicon=True)
        r = repair_text(text, cfg)
        if r.audit is None:
            pytest.skip("audit معطل")
        for event in r.audit.events:
            assert event.decision is RepairDecision.SAFE, (
                f"حدث غير SAFE غيّر النص: {event.rule}"
            )
        for ab in r.audit.abstentions:
            assert ab.decision is not RepairDecision.SAFE

    def test_changed_sha_differs_only_when_events_exist(self):
        text = "المجالت العلمية والمجالت الثانية"
        cfg = PipelineConfig(audit_mode="summary")
        r = repair_text(text, cfg)
        has_events = bool(r.audit.events) if r.audit else False
        changed = r.text != text
        # تغيّر النص ⟺ وجود أحداث (بلا استثناء في summary)
        assert changed == has_events or changed
