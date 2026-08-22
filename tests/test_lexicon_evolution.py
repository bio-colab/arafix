from __future__ import annotations

import pytest

from arafix import repair_text
from arafix.lamalef import repair_lam_alef_transposition
from arafix.lexicon.core import COMPRESSED_LEXICON, core_lexicon_size, get_core_lexicon

# اختبارات انحدار تطوير المعجم (أغسطس ٢٠٢٦).
#
# تُثبِّت ثلاث ركائز:
#   1. لا فساد على نصٍّ صحيح: الأزواج الصحيحة المتبادلة (ثالث/ثلاث…)
#      يجب أن تظل محميةً من الجهتين.
#   2. الحماية: الكلمات الشائعة الحاوية «ال» وسطية لا تبقى مشتبهات.
#   3. الإصلاح: الأشكال المكسورة الموثقة من كتب حقيقية تُرد إلى صحتها.
#
# الخلفية: اكتُشفت ثغرة حية كان فيها المعجم القديم يُفسد «الثالث» إلى
# «الثلاث» في دستور العراق نفسه (اختبار الانحدار أدناه يثبت العلاج).


@pytest.fixture(scope="module")
def vocab():
    return get_core_lexicon()


# ---------------------------------------------------------------------------
# ١) الثغرة الحية التاريخية: الأعداد الترتيبية
# ---------------------------------------------------------------------------


class TestOrdinalPairsAreSafe:
    """كان «الثالث» يُفسد إلى «الثلاث» لأن طرفاً الزوج لم يكونا معاً."""

    @pytest.mark.parametrize(
        "word",
        ["الثالث", "ثالث", "الثالثة", "ثالثة", "ثالثاً"],
    )
    def test_ordinal_side_is_protected(self, vocab, word):
        r = repair_lam_alef_transposition(word, vocab)
        assert r.text == word, f"فُسدت «{word}» إلى «{r.text}»"

    @pytest.mark.parametrize("word", ["الثلاث", "ثلاثة", "ثلاثاً"])
    def test_cardinal_side_still_works(self, vocab, word):
        assert word in vocab

    def test_constitution_sentence_untouched(self):
        healthy = "أولاً، ثانياً، ثالثاً؛ ثم توقف!"
        assert repair_text(healthy).text == healthy


# ---------------------------------------------------------------------------
# ٢) أزواج صحيحة متبادلة أخرى — قاعدة الطرفين
# ---------------------------------------------------------------------------


class TestValidPairBothSides:
    @pytest.mark.parametrize(
        "pair",
        [
            # أزواج تختلف بمبادلة مجاورة واحدة على نمط المشتبهات —
            # كلاهما كلمة عربية صحيحة، فيجب أن يحمي المعجم الطرفين معاً.
            ("الثلاث", "الثالث"),
            ("خلاف", "خالف"),
            ("علاج", "عالج"),
            ("طلاق", "طالق"),
            ("سلام", "سالم"),
            ("حلال", "حالل"),
            ("ولادة", "والدة"),
            ("قتلاه", "قتاله"),
            ("مولاي", "موالي"),
            ("ثلاثاً", "ثالثاً"),
        ],
    )
    def test_both_sides_present(self, vocab, pair):
        for w in pair:
            assert w in vocab, f"طرف الزوج {w!r} غائب — خطر فساد على النص الصحيح"


# ---------------------------------------------------------------------------
# ٣) الحماية: مشتبهات شائعة في نص صحيح لا تعدّ بعد اليوم
# ---------------------------------------------------------------------------


class TestProtectionCoverage:
    @pytest.mark.parametrize(
        "word",
        [
            "تعالى",
            "وتعالى",
            "العالم",
            "العالمية",
            "المسألة",
            "مسألة",
            "مصالح",
            "حالة",
            "حالتها",
            "قالوا",
            "فعالية",
            "جلالته",
            "رسالته",
            "الدلالة",
        ],
    )
    def test_common_words_not_flagged(self, vocab, word):
        r = repair_lam_alef_transposition(word, vocab)
        assert r.suspects_left == 0, f"«{word}» ما تزال مشتبهاً"


# ---------------------------------------------------------------------------
# ٤) الإصلاح: أشكال مكسورة موثقة من كتب منشورة تُرد صحيحة
# ---------------------------------------------------------------------------


class TestRepairTargetsFromBooks:
    @pytest.mark.parametrize(
        ("broken", "correct"),
        [
            ("احتالله", "احتلاله"),
            ("بالخالفة", "بالخلافة"),
            ("جاللته", "جلالته"),
            ("سالحه", "سلاحه"),
            ("كالمي", "كلامي"),
            ("مالحة", "ملاحة"),
            ("بالغية", "بلاغية"),
            ("داللة", "دلالة"),
            ("لألقمار", "للأقمار"),
            ("موالنا", "مولانا"),
            ("فعالً", "فعلاً"),
            ("طويالً", "طويلاً"),
        ],
    )
    def test_broken_form_repaired(self, vocab, broken, correct):
        r = repair_lam_alef_transposition(broken, vocab)
        assert r.text == correct, f"«{broken}» بقي معطوباً"


# ---------------------------------------------------------------------------
# ٥) نظافة المعجم ذاته
# ---------------------------------------------------------------------------


class TestLexiconHygiene:
    def test_no_non_arabic_entries(self, vocab):
        intruders = [w for w in vocab if not all("\u0600" <= c <= "\u06ff" for c in w)]
        assert intruders == [], f"مداخل غير عربية: {intruders[:10]}"

    def test_no_mechanism_dead_entries(self, vocab):
        """كل مدخل إما مشتبه قابل للمطابقة أو مرشَّح قابل للبلوغ."""
        alefs = "\u0627\u0623\u0625\u0622\u0671"
        dead = []
        for w in vocab:
            useful = False
            n = len(w)
            for i in range(1, n - 2):
                if (w[i] in alefs and w[i + 1] == "\u0644") or (
                    w[i] == "\u0644" and w[i + 1] in alefs
                ):
                    useful = True
                    break
            if not useful:
                dead.append(w)
        assert dead == [], f"{len(dead)} مدخلاً ميتاً ميكانيكياً، منها: {dead[:8]}"

    def test_size_is_bounded_and_lazy(self):
        size = core_lexicon_size()
        assert 1500 <= size <= 2500

    def test_compressed_blob_is_single_ascii_line(self):
        body = COMPRESSED_LEXICON.strip()
        assert "\n" not in body
        assert body.isascii()


# ---------------------------------------------------------------------------
# ٦) سلامة النص السليم عبر المسار الكامل — عينة الدستور
# ---------------------------------------------------------------------------


class TestHealthyPathNoFalseFixes:
    def test_definite_article_with_waw_untouched(self, vocab):
        """والنساء/والحرية صحيحة — لا تُبدَّل ولا تعاقب الثقة عندها زوراً."""
        for w in ["والنساء", "والحرية", "والسياسية"]:
            r = repair_lam_alef_transposition(w, vocab)
            assert r.text == w
