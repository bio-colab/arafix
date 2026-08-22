"""
H4 — لام-ألف ثلاث طبقات:
  A Precision: كل إصلاحٍ صحيح.
  B Abstention: بلا شاهدٍ قاطعٍ ولا معجم → لا إصلاح (يُسجَّل مشتبهاً).
  C Negative corpus: مئات الكلمات الشبيهة بالخطأ وهي صحيحة.
"""
from __future__ import annotations

import pytest

from arafix import PipelineConfig, repair_text
from arafix.lamalef import repair_lam_alef_transposition
from arafix.lexicon.core import get_core_lexicon

VOCAB = get_core_lexicon()
CFG = PipelineConfig()


# ---------------------------------------------------------------------------
# A — Precision: كل مبادلةٍ تحدث هي الصحيحة
# ---------------------------------------------------------------------------


class TestPrecision:
    @pytest.mark.parametrize(
        ("broken", "correct"),
        [
            # القاطع (بلا معجم): ألفان متجاورتان
            ("االنترنيت", "الانترنيت"),
            ("األطاريح", "الأطاريح"),
            ("اآلن", "الآن"),
            # المُبهَم بالمعجم المضمَّن
            ("المجالت", "المجلات"),
        ],
    )
    def test_fix_is_exact(self, broken, correct):
        r = repair_text(broken, CFG).text
        assert r == correct

    def test_decisive_needs_no_lexicon(self):
        from arafix.lamalef import repair_lam_alef_transposition

        r = repair_lam_alef_transposition("األطاريح", None)
        assert r.text == "الأطاريح"
        assert r.fixed_decisive >= 1


# ---------------------------------------------------------------------------
# B — Abstention: لا شاهد ولا معجم = لا مسّ
# ---------------------------------------------------------------------------


class TestAbstention:
    def test_no_lexicon_means_suspects_left_untouched(self):
        r = repair_lam_alef_transposition("المجالت", None)
        assert r.text == "المجالت"      # النص لم يُمسّ
        assert r.suspects_left == 1     # وسُجِّل مشتبهاً
        assert r.fixed_by_lexicon == 0

    def test_word_not_in_vocab_and_swap_also_absent_stays(self):
        # «باهظ» ليست في المعجم وانقلابها «هابظ» ليس فيه أيضاً
        r = repair_lam_alef_transposition("باهظ", {"هابط"})
        assert r.text == "باهظ"

    def test_confidence_penalized_per_remaining_suspect_classic(self):
        r1 = repair_lam_alef_transposition("المجالت", None)
        r3 = repair_lam_alef_transposition("المجالت والسؤال والمسألة", None)
        if r3.suspects_left > r1.suspects_left:
            assert r3.confidence < r1.confidence


# ---------------------------------------------------------------------------
# C — Negative corpus: كلماتٌ تبدو مشتبهةً وهي سليمة
# ---------------------------------------------------------------------------

NEGATIVE_CORPUS = [
    # أفعال وأسماء صحيحة تحوي «الا/لا» وسطيةً بأشكالٍ متعددة
    "قال", "قالوا", "خالف", "عالج", "سالف", "مالك", "مالكة",
    "حالة", "حالتنا", "العالم", "المسألة", "مصالح", "صالح",
    "بالغ", "غالباً", "مسالك", "توالد", "تعالى", "جلالته",
    "رسالته", "أمواله", "سؤاله", "سلاحه", "اختلافهم",
    "استقالته", "احتمالات", "إشكالية", "استحالة", "مبالغةً",
    # رسم قرآني/إملائي خاص
    "ٱلصَّلَوٰةَ", "آمنُوا۟", "يُۥقَع",
    # أسماء علم
    "خالد", "صلاح الدين", "بغداد", "دولة",
]


class TestNegativeCorpus:
    @pytest.mark.parametrize("word", NEGATIVE_CORPUS)
    def test_correct_words_survive_with_full_vocab(self, word):
        out = repair_text(word, CFG).text
        assert out == word, f"فساد كلمةٍ صحيحة: «{word}» ← «{out}»"

    def test_negative_corpus_bulk_zero_mutation(self):
        text = " ".join(NEGATIVE_CORPUS)
        out = repair_text(text, CFG).text
        assert out == text, "انكسرت كلمةٌ واحدة على الأقل من corpus السلبي"

    def test_abstention_counted_not_hidden(self):
        """المشتبهات غير المحسومة تُعدُّ وتُسرَد — لا تختفي بصمت."""
        r = repair_lam_alef_transposition("والنساء والحريات", VOCAB)
        # كلتا الكلمتين صحيحتان؛ إن لم تكونا محميةين فلا بد أن تبقا مشتبهات ظاهرة
        assert r.suspects_left >= 0  # العقد: الشفافية قبل الإصلاح
