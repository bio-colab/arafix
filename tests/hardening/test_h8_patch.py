"""
H8 — قداسة الـPatch القابل للعكس.

العقد: revert(apply(x)) == x   و   apply(revert(y)) == y
دائماً — على الحالات القاسية كلها — مع حراسة الهاش الثلاثية:
  1. رفض التطبيق إن لم يطابق النص الأصلي.
  2. رفض التطبيق إن اختلفت محتويات المدى المسجَّل.
  3. رفض النتيجة إن اختلفت هاش المخرج المتوقع.
"""
from __future__ import annotations

import itertools

import pytest

from arafix import PipelineConfig, repair_text
from arafix.audit import Patch, sha256_text

ADVERSARIAL_TEXTS = [
    ("empty", ""),
    ("single-char", "ا"),
    ("combining-marks", "مُحَمَّدٌ ﷺ إِنَّ"),
    ("presentation-forms", "\ufee3\ufeae\ufea3\ufe92\ufe8e ﻻ ﻷ ﻵ"),
    ("zwj-zwnj-zwsp", "عرب\u200cي ون\u200dص \u200bفاصل"),
    ("bidi-controls", "\u202bنص معكوس\u202c وبعده \u200fسطر"),
    ("repeated", "لا لا لا " * 50),
    ("huge", "نَصٌّ طويلٌ مكررٌ للتشديد " * 400),
    ("unusual-ws", "أ\tب\n\nج\r\nد\u00a0هـ\u3000و"),
    ("ligatures", "﷽ ﷺ ﷻ"),
    ("mixed-everything", "ﷺ (2024) USD 1,250.00 والنسبية العامة v1.2.3 ﷽ ۞ عَلَىٰ"),
]
_IDS = [label for label, _ in ADVERSARIAL_TEXTS]


class TestPatchRoundTrip:
    @pytest.mark.parametrize(("label", "text"), ADVERSARIAL_TEXTS, ids=_IDS)
    def test_revert_apply_round_trip(self, label, text):
        repaired = repair_text(text, PipelineConfig(audit_mode="full"))
        if repaired.audit is None or repaired.audit.patch is None:
            pytest.skip("لا patch (لا تغيير أو audit off)")
        patch = repaired.audit.patch
        assert patch.apply(patch.revert(repaired.text)) == repaired.text

    @pytest.mark.parametrize(("label", "text"), ADVERSARIAL_TEXTS, ids=_IDS)
    def test_revert_returns_exact_original(self, label, text):
        repaired = repair_text(text, PipelineConfig(audit_mode="full"))
        if repaired.audit is None or repaired.audit.patch is None:
            pytest.skip("لا patch")
        original_back = repaired.audit.patch.revert(repaired.text)
        assert original_back == text


class TestHashGuards:
    def test_apply_rejects_wrong_source(self):
        p = Patch.from_texts("abc", "abd")
        with pytest.raises(ValueError, match="original_sha256"):
            p.apply("xyz")

    def test_revert_rejects_wrong_target(self):
        p = Patch.from_texts("abc", "abd")
        with pytest.raises(ValueError, match="repaired_sha256"):
            p.revert("xyz")

    def test_span_tampering_detected(self):
        """لو عُدِّل نص المدى تحت الـpatch، يرفض التطبيق."""
        p = Patch.from_texts("مرحبا بالعالم", "مرحبا يا عالم")
        # نزوير: نصٌّ يطابق الهاش؟ مستحيل عملياً — لكن مدىً مختلفاً بنفس
        # الطول يمكن بناؤه عبر patch مصنوع يدوياً:
        from arafix.audit import PatchOperation

        forged = Patch(
            original_sha256=sha256_text("مرحبا بالعالم"),
            repaired_sha256=p.repaired_sha256,
            operations=(
                PatchOperation(0, 6, 0, 9, "مرحبا ", "تحريف "),
                *p.operations[1:],
            ),
        )
        with pytest.raises(ValueError):
            forged.apply("مرحبا بالعالم")

    def test_result_hash_mismatch_rejected(self):
        from arafix.audit import PatchOperation

        # عملياتٌ صحيحة المصدر لكن هاش النتيجة مزوَّر
        ops = (
            PatchOperation(0, 3, 0, 3, "abc", "abd"),
        )
        p = Patch(
            original_sha256=sha256_text("abc"),
            repaired_sha256=sha256_text("ZZZ"),  # هاش كاذب
            operations=ops,
        )
        with pytest.raises(ValueError, match="repaired_sha256"):
            p.apply("abc")


class TestPatchEdgeShapes:
    def test_adjacent_patches(self):
        """رقعتان متلاصقتان بلا فاصل — يجب ألا تتداخلا."""
        p = Patch.from_texts("abcdef", "abXYZef")
        assert len(p.operations) == 1 or all(
            op.end_before <= nxt.start_before
            for op, nxt in zip(p.operations, p.operations[1:])
        )
        assert p.apply("abcdef") == "abXYZef"

    def test_overlapping_via_single_matcher_is_impossible(self):
        """SequenceMatcher لا يولّد تداخلات؛ نتحقق آلياً."""
        for a, b in [
            ("aaaa", "bbbb"),
            ("أبأبأب", "بأبابأ"),
            ("x" * 100, "y" * 37),
        ]:
            p = Patch.from_texts(a, b)
            for o1, o2 in zip(p.operations, p.operations[1:]):
                assert o1.end_before <= o2.start_before
                assert o1.end_after <= o2.start_after

    def test_empty_to_something_and_back(self):
        p = Patch.from_texts("", "نص جديد")
        back = p.revert(p.apply(""))
        assert back == ""

    def test_something_to_empty_and_back(self):
        p = Patch.from_texts("محتوى كامل", "")
        applied = p.apply("محتوى كامل")
        assert applied == ""
        assert p.revert("") == "محتوى كامل"

    @pytest.mark.parametrize(
        ("a", "b"),
        list(itertools.product(["نص قصير", "﷽ ﷺ"], ["", "نص آخر مختلف الطول"])),
    )
    def test_pairwise_round_trips(self, a, b):
        p = Patch.from_texts(a, b)
        assert p.apply(a) == b
        assert p.revert(b) == a


class TestAuditNoNewChainsOnRerun:
    """
    أخطر الفشل: الإصلاح الأول يصنع شكلاً يبدو مدخلاً فاسداً جديداً،
    فيغيّره الثاني. الاختبار يقيس: هل audit النداء الثاني يولّد أحداثاً؟
    """

    SAMPLES = [
        "المجالت العلمية والمجالت الثانية",
        "ﺎﺒﺣﺮﻣ ﻻ ﻷ",
        "Ø§Ù„Ù…ÙCustomer Report 200 OK",
        "درس الطالب درسه في المكتبة العامة",
        "أَطْعَمَهُۥٓ إِذ جاء",
    ]

    @pytest.mark.parametrize("text", SAMPLES)
    def test_second_run_audit_has_zero_events(self, text):
        cfg = PipelineConfig(audit_mode="summary")
        first = repair_text(text, cfg)
        second = repair_text(first.text, cfg)
        events = second.audit.events if second.audit else []
        assert not events, (
            f"silent corruption! النداء الثاني ولّد {len(events)} حدث إصلاح: "
            f"{[e.rule for e in events][:5]}"
        )
