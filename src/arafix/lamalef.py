"""
انقلاب رباط لام-ألف — كشفُه وإصلاحُه **بعد وقوعه**.

الدرجة ١ ثم ٢ في هذا الأنبوب لا تُوقعان هذا العطب بعد اليوم (انظر
`pipeline.py`). لكنّ نصوصك قد تأتي معطوبةً من أداةٍ أخرى — pdfminer أو
pypdf أو نسخةٍ سابقة من هذه المكتبة — فيلزم علاجٌ بأثرٍ رجعيّ.

**آلية العطب:** «ﻻ» جليفٌ واحد. من فكّه إلى «ل»+«ا» ثم عكس السطر، عكس
الحرفين معه فصارا «ا»+«ل»:

    الانترنيت → االنترنيت      المجلات  → المجالت
    الأطاريح  → األطاريح       الإجراء  → اإلجراء

**والعطب تبديلُ موضعٍ (transposition)، والتبديل معكوسُ نفسه** — فالعلاج
هو العملية نفسها. المسألة كلها في **أين** نطبّقها، لا كيف.

وهنا ينقسم الأمر قسمين لا ثالث لهما، ونحن نصرّح بالحدّ بينهما:

  ┌── قاطعٌ حتميّ ────────────────────────────────────────────────┐
  │ إن سبقَ الرباطَ ألفٌ (كألف «ال» التعريف)، خلّف الانقلابُ        │
  │ ألفين متجاورتين: «اا» أو «اأ» أو «اإ».                        │
  │ وتجاورُ ألفين **مستحيلٌ إملائياً** في العربية — فالشاهد قاطع.  │
  │ يغطّي: الانترنيت، الأطاريح، الإجراء، الآن، مقاالت…            │
  └──────────────────────────────────────────────────────────────┘

  ┌── مُبهَمٌ لا يُحسم بلا معجم ──────────────────────────────────┐
  │ إن سبقَ الرباطَ حرفٌ غير الألف، لم يُخلِّف الانقلابُ أثراً       │
  │ مستحيلاً: «المجالت» تسلسلٌ مشروعٌ شكلاً.                       │
  │ ولا يُميّزها عن «أفعالهم» (وفيها «ال» أصيلة) أيّ قاعدةٍ إملائية.│
  │ فنحن **نُبلِغ ولا نخمّن**، ونعرض المعجم مدخلاً اختيارياً.       │
  └──────────────────────────────────────────────────────────────┘

والخلاصة عمليّاً: **الوقاية وحدها تامّة.** مرّر ملفك على `extract_pdf`
من أوّله يخرج سليماً؛ أما ترقيع نصٍّ أعطبه غيرُنا فناقصٌ بطبعه، ونقصانه
مُعلَنٌ هنا لا مخبوء.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .types import Evidence
from .unicode_tables import ALEF_FORMS, LAM

__all__ = [
    "LamAlefReport",
    "detect_lam_alef_transposition",
    "repair_lam_alef_transposition",
]


_ALEF = "".join(sorted(ALEF_FORMS))

#: الشاهد القاطع: ألفٌ، فألفٌ، فلام. الوسطى والأخيرة تتبادلان.
#: نلتقط الألف الأولى في مجموعةٍ لنعيد بناء النصّ بها دون فقدها.
_DECISIVE = re.compile(f"([{_ALEF}])([{_ALEF}])({LAM})")

#: مرشّحٌ مُبهَم: ألفٌ فلامٌ يتلوها حرفٌ عربيّ — قد تكون «ال» أصيلة
#: وقد تكون رباطاً منقلباً. لا نمسّها إلا بمعجم.
_AMBIGUOUS = re.compile(f"(?<=[\u0600-\u06FF])([{_ALEF}])({LAM})(?=[\u0600-\u06FF])")

_WORD = re.compile(r"[\u0621-\u064A\u0640\u064B-\u0652]+")

#: سوابقُ تلتصق بـ«ال» التعريف: واو العطف، فاء، باء، كاف، لام الجرّ.
_ARTICLE_PREFIXES = frozenset("وفبكل")


def _looks_like_article(word: str, i: int) -> bool:
    """
    أهذه «ال» في موضع أداة التعريف؟

    تُميَّز لأجل **الضوضاء لا الدقّة**: «وال» التعريف تتصدّر آلاف الكلمات،
    فلو أنذرنا عن كلٍّ منها لأغرقنا التقرير حتى لا يُقرأ، ومن لا يُقرأ
    لا ينفع. فنفصل المشتبه القويّ عن الضعيف ونعرضهما مفصولين.

    وليست هذه براءةً: «ولاية» ← «والية» انقلابٌ حقيقيّ يقع في هذا الموضع
    بعينه. ولذلك يظلّ المعجم — إن أُعطي — يفحص المواضع كلها بلا استثناء.
    """
    if i == 0:
        return True
    return i == 1 and word[0] in _ARTICLE_PREFIXES


@dataclass
class LamAlefReport:
    """حصيلة الفحص: ما أُصلح يقيناً، وما بقي مشتبهاً، وما حُسم بمعجم."""

    text: str
    fixed_decisive: int = 0
    fixed_by_lexicon: int = 0
    suspects_left: int = 0
    suspect_words: list[str] = None  # type: ignore[assignment]

    #: مواضعُ «ال» في موقع أداة التعريف — تُعدّ ولا تُسرَد، كبحاً للضوضاء.
    article_like: int = 0

    def __post_init__(self) -> None:
        if self.suspect_words is None:
            self.suspect_words = []

    @property
    def clean(self) -> bool:
        return self.fixed_decisive == 0 and self.suspects_left == 0

    @property
    def confidence(self) -> float:
        """يقينٌ تامّ ما لم يبقَ مشتبهٌ. كل مشتبهٍ يقضم الثقة."""
        if self.suspects_left == 0:
            return 1.0
        return round(max(0.35, 1.0 - 0.1 * self.suspects_left), 3)


def detect_lam_alef_transposition(text: str) -> tuple[int, int, Evidence]:
    """
    يُرجع: (عدد الشواهد القاطعة، عدد المشتبهات، الشاهد).

    >>> n_sure, n_maybe, _ = detect_lam_alef_transposition("االنترنيت")
    >>> n_sure
    1
    """
    decisive = len(_DECISIVE.findall(text))
    ambiguous = len(_AMBIGUOUS.findall(text))
    ev = Evidence(
        "lam_alef_transposed",
        1.0 if decisive else 0.0,
        f"{decisive} ألفاً مزدوجةً قاطعة، و{ambiguous} موضعاً مُبهَماً «ال» وسط الكلمة",
    )
    return decisive, ambiguous, ev


def repair_lam_alef_transposition(
    text: str,
    lexicon: Iterable[str] | None = None,
) -> LamAlefReport:
    """
    يصلح الانقلاب القاطع دائماً، والمُبهَم بمعجمٍ إن أُعطي.

    :param lexicon: مجموعة كلماتٍ عربية صحيحة. حين تُعطى، تُجرَّب المبادلة
        على كل موضعٍ مُبهَم وتُقبَل **بشرطين معاً**: أن تكون الكلمة الحالية
        غائبةً عن المعجم، وأن تكون المُبادَلة حاضرةً فيه. الشرطان معاً
        يمنعان إفساد «أفعالهم» وأمثالها.

    >>> repair_lam_alef_transposition("االنترنيت").text
    'الانترنيت'
    >>> repair_lam_alef_transposition("األطاريح").text
    'الأطاريح'
    >>> r = repair_lam_alef_transposition("المجالت")     # مُبهَم بلا معجم
    >>> r.text, r.suspects_left
    ('المجالت', 1)
    >>> repair_lam_alef_transposition("المجالت", {"المجلات"}).text
    'المجلات'
    """
    report = LamAlefReport(text=text)

    # --- القاطع: نكرّر حتى الاستقرار، فقد تتلاصق شواهد في كلمةٍ واحدة ---
    out = text
    for _ in range(8):  # سقفٌ يقي من دورةٍ لا تنتهي مهما شذّ المُدخَل
        new = _DECISIVE.sub(lambda m: m.group(1) + m.group(3) + m.group(2), out)
        if new == out:
            break
        report.fixed_decisive += 1
        out = new

    # --- المُبهَم ---
    suspects, article_like = _collect_suspects(out)
    report.article_like = article_like
    if not suspects and lexicon is None:
        report.text = out
        return report

    if lexicon is None:
        report.text = out
        report.suspects_left = len(suspects)
        report.suspect_words = sorted({w for w, _ in suspects})
        return report

    vocab: set[str] = set(lexicon)
    out, fixed, left = _apply_lexicon(out, vocab)
    report.text = out
    report.fixed_by_lexicon = fixed
    report.suspects_left = len(left)
    report.suspect_words = sorted(set(left))
    return report


def _collect_suspects(text: str) -> tuple[list[tuple[str, int]], int]:
    """
    يجمع مواضع «ال» المُبهَمة ويقسمها قسمين: قويّ الاشتباه، وشبيهُ الأداة.

    يُرجع: (المشتبهات القوية، عددُ ما يشبه أداة التعريف)
    """
    strong: list[tuple[str, int]] = []
    article_like = 0
    for m in _WORD.finditer(text):
        word = m.group(0)
        for hit in _AMBIGUOUS.finditer(word):
            if _looks_like_article(word, hit.start()):
                article_like += 1
            else:
                strong.append((word, hit.start()))
    return strong, article_like


def _swap_at(word: str, i: int) -> str:
    """يبادل الحرفين عند الموضع i و i+1."""
    return word[:i] + word[i + 1] + word[i] + word[i + 2 :]


def _apply_lexicon(text: str, vocab: set[str]) -> tuple[str, int, list[str]]:
    fixed = 0
    left: list[str] = []

    def repl(m: re.Match) -> str:
        nonlocal fixed
        word = m.group(0)
        hits = [h.start() for h in _AMBIGUOUS.finditer(word)]
        if not hits:
            return word
        if word in vocab:
            return word  # الكلمة صحيحة كما هي — لا تُمسّ («أفعالهم»)
        for i in hits:
            cand = _swap_at(word, i)
            if cand in vocab:
                fixed += 1
                return cand
        left.append(word)
        return word

    return _WORD.sub(repl, text), fixed, left
