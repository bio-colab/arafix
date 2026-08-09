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
#: ``الم…`` (lam/meem swap after ``ا``). Seen: املتاحف، املسيح، املعجزات…
#: Require ≥3 Arabic letters after ``امل`` so ``كاملة`` / ``شامل`` stay intact.
AL_MEEM_ARTICLE_RE = re.compile(r"امل(?=[\u0621-\u064A]{3,})")

#: Word-internal / whole-token confusions (longest keys first when applying).
#: Pair form: (broken, corrected). Closed list from Safahat book samples.
YE_REH_CONFUSIONS: tuple[tuple[str, str], ...] = (
    # multi-char / affixed first
    ("العاديني", "العاديين"),
    ("المسلمني", "المسلمين"),
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
    ("فريفعه", "فيرفعه"),
)


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
    >>> repair_pdf_confusions("اهتمامٍكبريعندي").text
    'اهتمامٍكبيرعندي'
    >>> repair_pdf_confusions("غري ذلك").text
    'غير ذلك'
    """
    if not text:
        return PdfConfusionReport(text=text)

    out = text
    al_n = 0
    ye_n = 0

    def _al_sub(m: re.Match[str]) -> str:
        nonlocal al_n
        al_n += 1
        return "الم"

    out2 = AL_MEEM_ARTICLE_RE.sub(_al_sub, out)
    out = out2

    # Short tokens (≤3 letters, e.g. غري): require start/non-letter/clitic
    # so مغري is safe. Longer tokens (كثري، كبري…): global replace — books
    # glue hard (الاستمتاعكثريًا) and false friends are rare at length ≥4.
    _B = r"\u0621-\u064A"
    _CLITIC = "وفبكل"
    for broken, fixed in YE_REH_CONFUSIONS:
        if broken not in out:
            continue
        if len(broken) >= 4:
            n = out.count(broken)
            out = out.replace(broken, fixed)
            ye_n += n
            continue
        pat = re.compile(
            rf"(?:(?<![{_B}])|(?<=[{_CLITIC}])){re.escape(broken)}"
        )
        out, n = pat.subn(fixed, out)
        ye_n += n

    return PdfConfusionReport(text=out, al_meem_fixes=al_n, ye_reh_fixes=ye_n)
