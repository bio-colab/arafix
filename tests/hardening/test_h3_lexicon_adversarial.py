"""
H3 — معجم الخصوم: هل يرفع المعجم إصلاحاً زائفاً على كلمةٍ صحيحة؟

الفئات المُهاجَمة:
  A الكلمة الصحيحة الشائعة (المجلات، الثالث…)
  B الكلمة المعطوبة (المجالت) — يجب الإصلاح
  C الصحيحة **الشبيهة** بالمعطوبة (عالم/علام، عمل/عمل…) — خطر القمة
  D الصحيحة النادرة (أفعالهم، سالفات…) — لا تُلمس
  E المختلفة بحرفٍ واحد عن معطوبٍ شائع
"""
from __future__ import annotations

import pytest

from arafix import PipelineConfig, repair_text
from arafix.lexicon.core import get_core_lexicon

CFG = PipelineConfig()


class TestCorrectWordsNeverTouched:
    """A + C + D: كلمات صحيحة تبقى صحيحة حرفياً عبر الأنبوب."""

    @pytest.mark.parametrize(
        "word",
        [
            # شائعة
            "المجلات", "الثالث", "العالم", "العمل", "السلام",
            "مسألة", "مصالح", "حالة", "قالوا", "فعالية",
            # أزواجٌ صحيحة الطرفين (خطر القمة)
            "خلاف", "خالد", "عالم", "طلاب", "طالب",
            # نادرة لكنها صحيحة
            "أفعالهم", "سالفة", "مسالك", "توالد",
            # مختلفة بحرفٍ واحد عن معطوب شائع
            "بالغ", "غالب", "صالح", "مالك",
        ],
    )
    def test_untouched(self, word):
        out = repair_text(word, CFG).text
        assert out == word, f"فساد: «{word}» ← «{out}»"

    @pytest.mark.parametrize(
        "sentence",
        [
            "رأيت المجلات العلمية في المكتبة",
            "هذا هو الفصل الثالث من الكتاب",
            "العالِمُ يعمل بجد",
            "قالوا إن الحقَّ منتصر",
            "أفعالهم حسنة وسالك مستقيم",
            "والبالغ في العمر غالباً ما يندم",
        ],
    )
    def test_sentences_untouched(self, sentence):
        out = repair_text(sentence, CFG).text
        assert out == sentence, f"فساد جملة سليمة:\n  قبل={sentence!r}\n  بعد={out!r}"


class TestBrokenFormsRepaired:
    @pytest.mark.parametrize(
        ("broken", "fixed"),
        [
            ("المجالت", "المجلات"),
            # «الثلاث→الثالث» ليست هنا عمداً: الطرفان في المعجم =
            # حمايةٌ متبادلة، والإصلاح يتطلب سياقاً (harvest) — انظر أدناه
            ("احتالله", "احتلاله"),
            ("جاللته", "جلالته"),
        ],
    )
    def test_broken_repaired(self, broken, fixed):
        out = repair_text(broken, CFG).text
        assert out == fixed, f"«{broken}» لم تُصلح إلى «{fixed}» بل بقيت «{out}»"

    def test_both_sides_present_means_protection_wins(self):
        """قاعدة الطرفين: وجود الشكلين = الحماية تمنع المبادلة عمياء.
        الإصلاح يتطلب شاهدَ سياقٍ (harvest المستند)."""
        from arafix.lexicon.core import get_core_lexicon

        vocab = get_core_lexicon()
        assert "الثلاث" in vocab and "الثالث" in vocab
        assert repair_text("الثلاث", CFG).text == "الثلاث"

    def test_context_harvest_breaks_the_tie_correctly(self):
        """مع شاهد السياق («العمل الثالث») يُحسم الاتجاه صوب الصحيح."""
        text = "أما العمل الثالث فكان عبارة عن سلسلة"
        out = repair_text(text, CFG).text
        assert "العمل الثالث" in out


# ---------------------------------------------------------------------------
# فحص الخصوم على مستوى المعجم نفسه (بلا أنبوب): كل ثنائية متجاورة
# ---------------------------------------------------------------------------


class TestLexiconAdversarialPairs:
    """
    لكل كلمة في المعجم: إن كان انقلاب ا/ل فيها ينتج كلمةً موجودة أيضاً،
    فهذا زوجٌ حساس — يجب أن تكون الكلمة الأصلية محميةً (وجودها في
    المعجم يمنع المبادلة).
    """

    KNOWN_SAFE_PAIRS = {
        # أزواجٌ حساسة طرفاها في المعجم عمداً (قاعدة الطرفين):
        ("الثلاث", "الثالث"),
        ("ثلاثة", "ثالثة"),
        ("خلاف", "خالف"),
        ("علاج", "عالج"),
        ("سلام", "سالم"),
        ("حلال", "حالل"),
        ("ولادة", "والدة"),
    }
    # ملاحظة: كان/كنا وعلم/عمل لا زوجين آليين (بلا زوج وسطي) —
    # حذفُهما من المعجم كان مقصوداً في تطوير المعجم.

    def test_both_sides_of_sensitive_pairs_present(self):
        vocab = get_core_lexicon()
        missing = [
            w for pair in self.KNOWN_SAFE_PAIRS for w in pair if w not in vocab
        ]
        assert not missing, f"أطراف أزواج حساسة غائبة عن المعجم: {missing}"

    def test_no_false_positive_on_correct_lookalikes(self):
        """نصٌّ صحيحٌ كثيف الكلمات المشتبه لا يُمسّ حرفياً."""
        text = (
            "العالم يعلم أن العمل خير، وكان كنا نعلم، والخلاف حول العلاج "
            "لا يفسد من السلام شيء، والمجلات نشرت مسألة العالم"
        )
        out = repair_text(text, CFG).text
        assert out == text, f"فساد نصٍّ سليم كثيف المشتبهات:\n{out!r}"
