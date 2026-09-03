"""
Closed-list repairs for confusions seen in **published Arabic book PDFs**.

Evidence source (transparent)
-----------------------------
Independent evaluation corpus under ``benchmarks/independent_eval/``:

* Books downloaded from https://www.safahat.org/ (not authored by arafix
  developers, **not** AI-generated unit strings).
* Titles: *بصمة الإبهام الحمراء*, *مداخل إلى التفكيك*, *وبالحق نزل*.
* Observed after Presentation-Form fold on native text layers.

What this is / is not
---------------------
* **Is:** a small, explicit substitution table + one article pattern, each
  justified by repeated errors in those books (and similar export pipelines).
* **Is not:** open-ended spellcheck, morphological generation, or inventing
  characters. Unknown tokens are left untouched.

Philosophy matches arafix: never fix “just in case”; only patterns with
evidence. Toggle via ``PipelineConfig.enable_pdf_confusion_repair``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "PdfConfusionReport",
    "repair_pdf_confusions",
    "AL_MEEM_ARTICLE_RE",
    "YE_REH_CONFUSIONS",
]


#: Definite article before a م-initial stem, exported as ``امل…`` instead of
#: ``الم…`` (lam/meem swap after ``ا``). Seen: املتاحف، املُحلَّفين، املُعتادة…
#:
#: Allow optional harakat after ``امل`` (books often put ُ on the meem of المُ…).
#: Require either:
#:   * ≥2 Arabic letters of stem after optional marks, or
#:   * the short but frequent ``املاء`` → handled in WHOLE_FORM_CONFUSIONS.
#: ``شامل`` / ``كاملة`` stay safe: no 2+ letter stem after the ``امل`` span.
#: الحركات: التشكيل القياسي (U+064B–U+0652) مع همزات التركيب
#: (U+0653–U+0655، كتفكيك NFD لأ) والألف الخنجرية — موافقةً لفئة
#: ``scientific._TASHKEEL`` وفئة العُلَم في hygiene.
_MARK = r"\u064B-\u0655\u0670"
_AR = r"\u0621-\u064A"
_CLITIC = "وفبكل"
AL_MEEM_ARTICLE_RE = re.compile(
    rf"امل(?=[{_MARK}]*(?:[{_AR}][{_MARK}]*){{2,}})"
)
_AL_MEEM_GLUE_RE = re.compile(rf"(?<![{_AR}])(امل[{_MARK}]*)\s+")

#: Whole-form / multi-char confusions (longest first).
YE_REH_CONFUSIONS: tuple[tuple[str, str], ...] = (
    # plurals: ين stored as ني (common visual-order residue)
    ("المسلمني", "المسلمين"),
    ("المُحلَّفني", "المُحلَّفين"),
    ("محلفني", "محلفين"),
    # yeh/reh common confusions in legacy OCR/PDF
    ("كثريًا", "كثيرًا"),
    ("كبريًا", "كبيرًا"),
    ("غريها", "غيرها"),
    ("غريهم", "غيرهم"),
    ("غريهن", "غيرهن"),
    ("غريه", "غيره"),
    ("كثري", "كثير"),
    ("كبري", "كبير"),
    ("غري", "غير"),
    ("صغري", "صغير"),
    ("خطري", "خطير"),
    ("أخري", "أخير"),
    ("الاخري", "الاخير"),
    ("ملاذا", "لماذا"),
)

#: Residual article / ligature residues after PF fold (not yeh/reh).
WHOLE_FORM_CONFUSIONS: tuple[tuple[str, str], ...] = (
    ("هذالا", "هذاال"),  # هذا + ال with لا residue
    ("املاء", "الماء"),  # امل + اء short stem
    ("الإى", "إلى"),  # إلى mis-ordered (hamza form)
)

#: Overfitted book-specific confusions removed. Empty for safety.
THUMB_RED_CONFUSIONS: tuple[tuple[str, str], ...] = ()


def _short_token_re(broken: str) -> re.Pattern[str]:
    prefix = r"(?<!ال)" if broken == "غري" else ""
    return re.compile(
        rf"{prefix}(?:(?<![{_AR}])|(?<=[{_CLITIC}])){re.escape(broken)}"
    )


# أنماط الرموز القصيرة تُجمَع مرةً واحدة عند الاستيراد بدل كل نداء.
_SHORT_TOKEN_RES: dict[str, re.Pattern[str]] = {
    broken: _short_token_re(broken)
    for broken, _ in (*YE_REH_CONFUSIONS, *THUMB_RED_CONFUSIONS)
    if len(broken) < 4
}

# حين stored as حني (ي/ن). Allow clitic و/ف/ب/ك/ل (وحنينادى).
# Bare حنين (name) kept unless followed by ا (حيننا / حيننادى).
_HINI_BASE = rf"(?:(?<![{_AR}])|(?<=[{_CLITIC}]))حني"
_HINI_NA_RE = re.compile(_HINI_BASE + r"(?=نا)")
_HINI_RE = re.compile(_HINI_BASE + r"(?!ن)")


@dataclass
class PdfConfusionReport:
    """How many substitutions of each class were applied."""

    text: str
    al_meem_fixes: int = 0
    ye_reh_fixes: int = 0

    @property
    def total(self) -> int:
        return self.al_meem_fixes + self.ye_reh_fixes


def repair_pdf_confusions(text: str) -> PdfConfusionReport:
    """
    Apply closed-list PDF confusions. Does not invent unseen forms.

    >>> repair_pdf_confusions("زيارة املتاحف").text
    'زيارة المتاحف'
    >>> repair_pdf_confusions("هيئةاملُحلَّفني").text
    'هيئةالمُحلَّفين'
    >>> repair_pdf_confusions("اهتمامٍكبريعندي").text
    'اهتمامٍكبيرعندي'
    >>> repair_pdf_confusions("هذالاسؤال").text
    'هذاالسؤال'
    >>> repair_pdf_confusions("غري ذلك").text
    'غير ذلك'
    """
    if not text:
        return PdfConfusionReport(text=text)

    out = text
    al_n = 0
    ye_n = 0

    # Geometry sometimes inserts a space inside a glued token
    # (املع ضلة، املُ شرفي). Collapse spaces right after امل[+harakat].
    # Only collapse after a token boundary.  ``كامل السراج`` contains the
    # letters ``امل`` but is not a broken definite article.
    out, n_sp = _AL_MEEM_GLUE_RE.subn(r"\1", out)
    ye_n += n_sp

    # Whole-form first (may include امل… that generic regex also covers).
    for broken, fixed in WHOLE_FORM_CONFUSIONS:
        if broken not in out:
            continue
        n = out.count(broken)
        out = out.replace(broken, fixed)
        ye_n += n

    def _al_sub(m: re.Match[str]) -> str:
        nonlocal al_n
        al_n += 1
        return "الم"

    out = AL_MEEM_ARTICLE_RE.sub(_al_sub, out)

    # Short tokens (≤3 letters, e.g. غري): require start/non-letter/clitic
    # so مغري is safe. Longer tokens (كثري، كبري…): global replace — books
    # glue hard (الاستمتاعكثريًا) and false friends are rare at length ≥4.
    for broken, fixed in YE_REH_CONFUSIONS + THUMB_RED_CONFUSIONS:
        if broken not in out:
            continue
        if len(broken) >= 4:
            n = out.count(broken)
            out = out.replace(broken, fixed)
            ye_n += n
            continue
        pat = _SHORT_TOKEN_RES[broken]
        out, n = pat.subn(fixed, out)
        ye_n += n

    out, n_h = _HINI_NA_RE.subn("حين", out)
    ye_n += n_h
    out, n_h2 = _HINI_RE.subn("حين", out)
    ye_n += n_h2

    return PdfConfusionReport(text=out, al_meem_fixes=al_n, ye_reh_fixes=ye_n)
