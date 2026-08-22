"""الثوابت المعمارية — عقودٌ يجب ألا تنكسر مع أي تغيير مستقبلي.

الثوابت الثلاثة:
  ١. **حتمية النص**: نداءان بنفس المدخل يعطيان نفس النص (دائماً، بلا استثناء).
  ٢. **Idempotence**: الإصلاح المزدوج يساوي المفرد — نصاً وثقةً في وضع
     ``density``. وفي وضع ``classic`` تُوثَّق عدمُ تماثل الثقة عمداً
     (العقاب مرتبطٌ بوقوعِ إصلاحٍ في النداء نفسه — انظر W6 أدناه).
  ٣. **سلامة السليم**: نصٌّ صحيح لا يُلمَس بأي وضع.

W6 — الخلل الموثَّق في الوضع الكلاسيكي:
  ثقة لام-ألف تعاقب المشتبهات المتبقية فقط إن وقع إصلاحٌ في النداء ذاته.
  فالنداء الأول على نصٍّ فيه «المجالت» يصلحها ويُخفض الثقة عن بقية
  المشتبهات؛ والنداء الثاني لا يجد ما يصلحه فتعود الثقة ١٫٠ رغم أن
  المشتبهات نفسها باقية. وضع ``density`` يحسم ذلك بعقوبةٍ كثافية
  مستقلة عن وقوع الإصلاح.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arafix import PipelineConfig, repair_text
from arafix.pipeline import _punctuation_position_hint


def _corpus() -> list[tuple[str, str]]:
    """مدخلات متنوعة تغطي مسارات الأنبوب كلها."""
    cases: list[tuple[str, str]] = [
        ("pf-garbage", "\ufee3\ufeae\ufea3\ufe92\ufe8e ﻣﺮﺣﺒﺎ ﺑﻜﻢ"),
        ("mojibake", "Ø§Ù„Ù…ÙCustomer Report (Status: 200 OK) - دراسة مقارنة"),
        (
            "mixed-lines",
            "تتناول هذه الدراسة أهم جوانب النظرية البنيوية الحديثة\n"
            "ةماعلاو ةغللا نم راداهإ هتاجرد لضفت ناوك يذلا باتكلا\n"
            "ويبحث أثرها العميق في الدراسات اللغوية المعاصرة",
        ),
        (
            "suspects",
            "المجالت العلمية صدرت في املتاحف الوطنية وكثري من الجهات، "
            "والسؤال متكرر والتعاليم متداولة",
        ),
        (
            "latin-mix",
            "GDP 2024 grew 3.5% بينما سجل الإصدار v1.2.3 تحسناً في "
            "(ص. 125-140) من الفهرس",
        ),
        ("empty", ""),
        ("whitespace", "   \n\t  "),
    ]
    bidi_path = Path(__file__).parents[1] / "benchmarks" / "adversarial_bidi_corpus.json"
    data = json.loads(bidi_path.read_text(encoding="utf-8"))
    for case in data["cases"][:25]:
        cases.append((f"bidi:{case['id']}", case["visual_input"]))
    return cases


CONFIGS = {
    "default": PipelineConfig(),
    "rescue": PipelineConfig(rescue_mixed_lines=True),
    "density": PipelineConfig(confidence_mode="density", rescue_mixed_lines=True),
}


# ---------------------------------------------------------------------------
# الثابت ١ + ٢: الحتمية و Idempotence
# ---------------------------------------------------------------------------


class TestIdempotence:
    @pytest.mark.parametrize("cfg_name", list(CONFIGS))
    def test_text_idempotent(self, cfg_name):
        """النص متماثل دائماً — بلا أي استثناء."""
        for label, text in _corpus():
            cfg = CONFIGS[cfg_name]
            once = repair_text(text, cfg)
            twice = repair_text(once.text, cfg)
            assert twice.text == once.text, f"انكسر التماثل في {label}"

    def test_density_confidence_idempotent(self):
        for label, text in _corpus():
            cfg = CONFIGS["density"]
            once = repair_text(text, cfg)
            twice = repair_text(once.text, cfg)
            assert twice.confidence == once.confidence, f"W6 في density؟ {label}"

    def test_classic_confidence_quirk_is_documented_not_hidden(self):
        """
        W6 موثَّق: الوضع الكلاسيكي قد يغيّر الثقة بين نداءين لنفس النص.

        هذا الاختبار **يثبّت** السلوك بدل تركه صدفة: النداء الثاني بعد
        إصلاحٍ لم يعد يجد ما يُصلحه، فلا يمر عبر فرع العقوبة أصلاً.
        من يريد عدالةً كثافية فلْيستعمل ``confidence_mode="density"``.
        """
        text = dict(_corpus())["suspects"]
        once = repair_text(text, PipelineConfig())
        twice = repair_text(once.text, PipelineConfig())
        # النص متماثل
        assert twice.text == once.text
        # والسلوك محدَّد: إن كانت الثقة الأولى معاقَبةً فالأعلى منها بعدها
        # (لأن المشتبهات لم تعد تمر عبر فرع الإصلاح)، أو متساوية.
        assert twice.confidence >= once.confidence


# ---------------------------------------------------------------------------
# الثابت ٣: سلامة السليم — بلا أي وضع
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cfg_name", list(CONFIGS))
def test_healthy_noop_invariant(cfg_name):
    page = "\n".join(
        [
            "تتناول هذه الدراسة أهم جوانب النظرية البنيوية في النقد الأدبي",
            "حيث يرصد الكاتب تطور المدرسة منذ نشأتها في العشرينيات",
        ]
        * 3
    )
    assert repair_text(page, CONFIGS[cfg_name]).text == page


# ---------------------------------------------------------------------------
# W6 مباشرةً: المقارنة العادلة بين النمطين
# ---------------------------------------------------------------------------


class TestClassicVsDensity:
    def _page_with_fixed_and_leftover_suspects(self, filler_repeats: int) -> str:
        """«المجالت» تضمن وقوع إصلاح (فتُفعَّل عقوبة classic)، وستة
        مشتبهات صحيحة لا توائم لها تبقى — والتكرار الصحي يوسّع البسط
        الكثافي دون زيادة المشتبهات."""
        suspects = "والنساء والحريات والسياسية والدستورية والمحكومين بالاقتراع."
        filler = "وهذا نص إضافي سليم طويل يُكرَّر لتوسيع عدد الكلمات السليمة."
        return (
            "المجالت العلمية "
            + suspects
            + " "
            + filler * filler_repeats
            + " وتعالى جلالته العالم المسألة حالة قالوا فعالية"
        )

    def test_long_page_density_far_above_classic(self):
        """W4: الصفحة الطويلة لا تُعاقَب زوراً على مشتبهاتها القليلة."""
        page = self._page_with_fixed_and_leftover_suspects(filler_repeats=12)
        classic = repair_text(page, PipelineConfig())
        density = repair_text(page, PipelineConfig(confidence_mode="density"))
        assert classic.confidence < density.confidence

    def test_short_page_both_modes_floor_together(self):
        """الصفحة القصيرة المليئة بالمشتبهات تُقرَب للحد الأدنى في النمطين."""
        page = self._page_with_fixed_and_leftover_suspects(filler_repeats=0)
        classic = repair_text(page, PipelineConfig())
        density = repair_text(page, PipelineConfig(confidence_mode="density"))
        assert density.confidence <= classic.confidence + 1e-9
        assert 0.35 <= density.confidence <= 1.0

    def test_density_penalizes_even_without_fixes(self):
        """جوهر W6: مشتبهاتٌ بلا أي إصلاح — classic يتجاهلها، density لا."""
        suspects_only = (
            "والنساء والحريات والسياسية والدستورية والمحكومين بالاقتراع "
            "وتعالى جلالته العالم المسألة حالة قالوا فعالية خلافاتهم"
        )
        classic = repair_text(suspects_only, PipelineConfig())
        density = repair_text(
            suspects_only, PipelineConfig(confidence_mode="density")
        )
        assert classic.confidence == 1.0  # لا إصلاح ← لا عقاب (الخلل الموثَّق)
        assert density.confidence < 1.0  # الكثافة تشهد بالفساد

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="confidence_mode"):
            repair_text("نص تجريبي بسيط", PipelineConfig(confidence_mode="magic"))


# ---------------------------------------------------------------------------
# P3 — بطاقة فساد المستند في metadata
# ---------------------------------------------------------------------------


class TestCorruptionProfile:
    def test_profile_present_on_real_pdf(self):
        from arafix.extractors import PyMuPDFExtractor

        if not PyMuPDFExtractor.available():
            pytest.skip("PyMuPDF not installed")
        from arafix import extract_pdf

        pdf = Path(__file__).parents[1] / (
            "tests/fixtures/real_pdf_narrative/iraq_constitution.pdf"
        )
        doc = extract_pdf(str(pdf), PipelineConfig())
        profile = doc.metadata.get("document_corruption_profile")
        assert profile is not None
        assert profile["pages_total"] == len(doc.pages)
        assert 0 <= profile["pages_content_repaired"] <= len(doc.pages)
        counts = profile["stage_page_counts"]
        assert counts.get("diagnose") == len(doc.pages)
        # لا عدّ لمراحل لم تحدث
        assert "ocr" not in counts and "context" not in counts


# ---------------------------------------------------------------------------
# P2 — تلميح مواضع الترقيم: منطق المستعلم وحده
# ---------------------------------------------------------------------------


class TestPunctuationPositionHint:
    def test_reversed_style_lines_trigger_hint(self):
        text = ".هذا سطر تجريبي طويل بما يكفي للحكم عليه\n.وسطر آخر مماثل أيضاً في الطول"
        hint = _punctuation_position_hint(text)
        assert hint is not None
        assert hint["lines_starting_with_terminator"] >= 2

    def test_logical_lines_do_not_trigger(self):
        text = "هذا سطر سليم ينتهي بنقطة طبيعية.\nوسطر آخر خاتمته في موضعها الصحيح!"
        hint = _punctuation_position_hint(text)
        assert hint is None or hint["lines_starting_with_terminator"] <= hint[
            "lines_ending_with_terminator"
        ]

    def test_short_lines_have_no_testimony(self):
        assert _punctuation_position_hint("قصير.\nآخر.") is None
