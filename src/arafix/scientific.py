"""
Scientific quality metrics for Arabic PDF recovery (evaluation layer).

These scores exist to **measure**, not to market. Each one answers a
failure mode CER/WER blur together:

  MCS  Morphological Continuity Score
       Is the *letter skeleton* (morphology-bearing stream) continuous
       with the reference? Joining-identity checks catch residual visual
       order without needing a reference.

  DBR  Diacritic-to-Base Ratio / attachment matrix
       Are harakat present in the right amounts *and* glued to the right
       bases? Inventory can be perfect while attachment is broken.

  BFE  Bidi Flow Entropy
       How chaotic is the directional class stream? Clean logical Arabic
       has low run-entropy; visual dumps and broken LTR islands raise it.

  SHDR Semantic Homoglyph Drift Rate
       What fraction of Arabic letters are PDF lookalikes (ی/ھ/…) that
       read the same but break equality, search, and NLP?

No third-party deps. Safe to import from ``arafix.eval`` paths and tests.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .normalize import fold_pdf_homoglyphs

__all__ = [
    "MCSReport",
    "DBRReport",
    "BFEReport",
    "SHDRReport",
    "ScientificReport",
    "morphological_continuity",
    "diacritic_base_matrix",
    "bidi_flow_entropy",
    "homoglyph_drift",
    "scientific_audit",
]


# ── shared constants ────────────────────────────────────────────────────

_TASHKEEL = frozenset(
    "\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0653\u0654\u0655\u0670"
)
_MARK_NAMES = {
    "\u064b": "fathatan",
    "\u064c": "dammatan",
    "\u064d": "kasratan",
    "\u064e": "fatha",
    "\u064f": "damma",
    "\u0650": "kasra",
    "\u0651": "shadda",
    "\u0652": "sukun",
    "\u0653": "maddah",
    "\u0654": "hamza_above",
    "\u0655": "hamza_below",
    "\u0670": "superscript_alef",
}

# Codepoints that *look* like standard Arabic letters in many PDF fonts
# but are different semantic identities for string ops / search / NLP.
_HOMOGLYPH_TO_CANON = {
    "\u06cc": "\u064a",  # Farsi Yeh → Yeh
    "\u06cd": "\u064a",
    "\u06be": "\u0647",  # Heh Doachashmee → Heh
    "\u06c1": "\u0647",
    "\u06c2": "\u0647",
    "\u06a9": "\u0643",  # Keheh → Kaf
    "\u06c3": "\u0629",
}
_HOMOGLYPHS = frozenset(_HOMOGLYPH_TO_CANON)

_ARABIC_LETTER = re.compile(r"[\u0621-\u064A\u066E-\u06D3\u06FA-\u06FF]")

# Bidi classes collapsed into evaluation buckets (UAX #9 families).
_BIDI_BUCKET = {
    "AL": "R",   # Arabic letter
    "R": "R",
    "AN": "AN",  # Arabic number
    "L": "L",
    "EN": "EN",  # European number
    "ES": "EN",  # European separator → number neighborhood
    "ET": "EN",
    "CS": "N",   # common separator
    "ON": "N",
    "WS": "W",
    "S": "W",
    "B": "W",
    "BN": "W",
    "NSM": "M",  # nonspacing mark (harakat)
    "PDF": "N",
    "LRE": "N",
    "RLE": "N",
    "LRO": "N",
    "RLO": "N",
    "LRI": "N",
    "RLI": "N",
    "FSI": "N",
    "PDI": "N",
}


def _strip_marks(s: str) -> str:
    return "".join(c for c in s if c not in _TASHKEEL and unicodedata.category(c) != "Mn")


def _arabic_letters(s: str) -> str:
    return "".join(_ARABIC_LETTER.findall(_strip_marks(s)))


def _canon_letters(s: str) -> str:
    return fold_pdf_homoglyphs(_arabic_letters(s))


# ── MCS ─────────────────────────────────────────────────────────────────


@dataclass
class MCSReport:
    """
    Morphological Continuity Score.

    The morphology of Arabic rides on the *base-letter* stream, not on
    presentation forms or harakat. MCS asks: does that stream stay continuous
    with the reference, and is intrinsic joining identity healthy?
    """

    score: float
    letter_fidelity: float
    token_continuity: float
    joining_integrity: float
    n_ref_letters: int
    n_hyp_letters: int
    joining_pairs: int
    joining_violations: int

    def __str__(self) -> str:
        return (
            f"MCS {self.score:.3f}  "
            f"(letters={self.letter_fidelity:.3f} tokens={self.token_continuity:.3f} "
            f"join={self.joining_integrity:.3f})"
        )


def _joining_integrity(text: str) -> tuple[float, int, int]:
    """
    Intrinsic joining-identity check on presentation forms if present;
    on plain text returns 1.0 with zero pairs (no PF evidence).

    Reuses the linguistic invariant from diagnose: for adjacent PF forms,
    joins_forward(a) == joins_backward(b).
    """
    from .diagnose import _joins_backward, _joins_forward
    from .unicode_tables import PF_JOINING_FORM, PF_TO_BASE, JoiningForm

    token_re = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]+")
    correct = wrong = 0
    for token in token_re.findall(text):
        forms = []
        for c in token:
            f = PF_JOINING_FORM.get(c)
            if f is None or f is JoiningForm.UNKNOWN:
                continue
            base = PF_TO_BASE.get(c, c)
            if base and unicodedata.category(base[0]) == "Mn":
                continue
            forms.append(f)
        for a, b in zip(forms, forms[1:]):
            if _joins_forward(a) == _joins_backward(b):
                correct += 1
            else:
                wrong += 1
    pairs = correct + wrong
    if pairs == 0:
        # No PF evidence — treat as N/A full integrity for plain logical text.
        return 1.0, 0, 0
    return correct / pairs, pairs, wrong


def morphological_continuity(reference: str, hypothesis: str) -> MCSReport:
    """
    MCS ∈ [0, 1], higher is better.

    score = 0.50·letter_fidelity + 0.35·token_continuity + 0.15·joining_integrity

    * letter_fidelity — 1 − CER on canon Arabic letter streams (no marks)
    * token_continuity — SequenceMatcher ratio on letter-only tokens
    * joining_integrity — PF joining-identity hold rate (1.0 if no PF left)
    """
    from .evaluate import cer

    ref_l = _canon_letters(reference)
    hyp_l = _canon_letters(hypothesis)
    letter_fid = 1.0 - cer(ref_l, hyp_l).rate if ref_l else 1.0
    letter_fid = max(0.0, min(1.0, letter_fid))

    ref_tok = [w for w in _canon_letters(" ".join(reference.split())).split() if w]
    # token list: split hypothesis/reference on whitespace then strip to letters
    def letter_tokens(s: str) -> list[str]:
        out = []
        for w in s.split():
            t = _canon_letters(w)
            if t:
                out.append(t)
        return out

    ref_tok = letter_tokens(reference)
    hyp_tok = letter_tokens(hypothesis)
    token_c = SequenceMatcher(None, ref_tok, hyp_tok, autojunk=False).ratio()

    join_i, pairs, viol = _joining_integrity(hypothesis)
    score = 0.50 * letter_fid + 0.35 * token_c + 0.15 * join_i
    return MCSReport(
        score=round(score, 4),
        letter_fidelity=round(letter_fid, 4),
        token_continuity=round(token_c, 4),
        joining_integrity=round(join_i, 4),
        n_ref_letters=len(ref_l),
        n_hyp_letters=len(hyp_l),
        joining_pairs=pairs,
        joining_violations=viol,
    )


# ── DBR ─────────────────────────────────────────────────────────────────


@dataclass
class DBRReport:
    """
    Diacritic-to-Base metrics.

    * inventory_match — cosine similarity of mark-type histograms (ref vs hyp)
    * attachment_accuracy — among aligned bases that carry marks in ref,
      fraction whose mark multiset matches hyp (after canon fold of bases)
    * leading_mark_rate — words starting with a combining mark (should be ~0)
    * marks_per_base — global diacritic density
    * matrix — coarse base-class × mark-type counts on *hypothesis*
    """

    score: float
    inventory_match: float
    attachment_accuracy: float
    leading_mark_rate: float
    marks_per_base_ref: float
    marks_per_base_hyp: float
    n_marks_ref: int
    n_marks_hyp: int
    matrix: dict[str, dict[str, int]] = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"DBR {self.score:.3f}  "
            f"(attach={self.attachment_accuracy:.3f} inv={self.inventory_match:.3f} "
            f"lead={self.leading_mark_rate:.3f})"
        )


def _base_mark_pairs(text: str) -> list[tuple[str, str]]:
    """(base_letter, marks_string) for letter clusters; orphans as ('_', marks)."""
    pairs: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in _TASHKEEL or unicodedata.category(ch) == "Mn":
            marks = ch
            i += 1
            while i < n and (text[i] in _TASHKEEL or unicodedata.category(text[i]) == "Mn"):
                marks += text[i]
                i += 1
            pairs.append(("_", marks))
            continue
        if _ARABIC_LETTER.match(ch):
            base = fold_pdf_homoglyphs(ch)
            marks = ""
            i += 1
            while i < n and (text[i] in _TASHKEEL or unicodedata.category(text[i]) == "Mn"):
                marks += text[i]
                i += 1
            pairs.append((base, marks))
            continue
        i += 1
    return pairs


def _cosine(a: Counter, b: Counter) -> float:
    if not a and not b:
        return 1.0
    keys = set(a) | set(b)
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(v * v for v in a.values())) or 1.0
    nb = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return dot / (na * nb)


def diacritic_base_matrix(reference: str, hypothesis: str) -> DBRReport:
    """
    DBR score ∈ [0, 1], higher is better.

    score = 0.55·attachment_accuracy + 0.30·inventory_match
            + 0.15·(1 − min(1, leading_mark_rate·5))
    """
    ref_pairs = _base_mark_pairs(reference)
    hyp_pairs = _base_mark_pairs(hypothesis)

    ref_hist: Counter = Counter()
    hyp_hist: Counter = Counter()
    for _, marks in ref_pairs:
        for m in marks:
            ref_hist[_MARK_NAMES.get(m, f"U+{ord(m):04X}")] += 1
    for _, marks in hyp_pairs:
        for m in marks:
            hyp_hist[_MARK_NAMES.get(m, f"U+{ord(m):04X}")] += 1

    inv = _cosine(ref_hist, hyp_hist)

    # Align on base letters only
    rb = [(b, m) for b, m in ref_pairs if b != "_"]
    hb = [(b, m) for b, m in hyp_pairs if b != "_"]
    from .order import order_combining_marks

    def _canon_marks(m: str) -> str:
        """Order-insensitive equality: shadda-before-vowel + multiset stable."""
        return order_combining_marks(m) if m else ""

    sm = SequenceMatcher(None, [b for b, _ in rb], [b for b, _ in hb], autojunk=False)
    matched = correct = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            continue
        for ii, jj in zip(range(i1, i2), range(j1, j2)):
            if not rb[ii][1] and not hb[jj][1]:
                continue  # both bare — skip density bias
            if rb[ii][1]:  # reference carries marks
                matched += 1
                if _canon_marks(rb[ii][1]) == _canon_marks(hb[jj][1]):
                    correct += 1
    attach = correct / matched if matched else 1.0

    words = hypothesis.split()
    lead = sum(1 for w in words if w and (w[0] in _TASHKEEL or unicodedata.category(w[0]) == "Mn"))
    lead_rate = lead / len(words) if words else 0.0

    n_base_ref = sum(1 for b, _ in ref_pairs if b != "_") or 1
    n_base_hyp = sum(1 for b, _ in hyp_pairs if b != "_") or 1
    n_mk_ref = sum(len(m) for _, m in ref_pairs)
    n_mk_hyp = sum(len(m) for _, m in hyp_pairs)

    # Coarse matrix on hypothesis: base group × mark name
    matrix: dict[str, dict[str, int]] = {}
    for base, marks in hyp_pairs:
        if base == "_" or not marks:
            continue
        # group: sun-letter-ish is overkill; use the letter itself for top set
        bg = base
        row = matrix.setdefault(bg, {})
        for m in marks:
            name = _MARK_NAMES.get(m, "other")
            row[name] = row.get(name, 0) + 1
    # keep only frequent bases in the exported matrix (noise control)
    top = sorted(matrix.items(), key=lambda kv: -sum(kv[1].values()))[:12]
    matrix = dict(top)

    lead_penalty = 1.0 - min(1.0, lead_rate * 5.0)
    score = 0.55 * attach + 0.30 * inv + 0.15 * lead_penalty
    return DBRReport(
        score=round(score, 4),
        inventory_match=round(inv, 4),
        attachment_accuracy=round(attach, 4),
        leading_mark_rate=round(lead_rate, 4),
        marks_per_base_ref=round(n_mk_ref / n_base_ref, 4),
        marks_per_base_hyp=round(n_mk_hyp / n_base_hyp, 4),
        n_marks_ref=n_mk_ref,
        n_marks_hyp=n_mk_hyp,
        matrix=matrix,
    )


# ── BFE ─────────────────────────────────────────────────────────────────


@dataclass
class BFEReport:
    """
    Bidi Flow Entropy.

    Shannon entropy (bits) over directional *runs* after collapsing Unicode
    bidi classes into buckets {R, L, EN, AN, M, N, W}.

    * entropy_bits — raw H
    * normalized — H / log2(|active buckets|), ∈ [0, 1]
    * n_runs — number of direction runs
    * delta_to_ref — |norm_hyp − norm_ref| when reference given
    """

    entropy_bits: float
    normalized: float
    n_runs: int
    run_histogram: dict[str, int]
    delta_to_ref: float | None = None

    def __str__(self) -> str:
        d = f"  Δref={self.delta_to_ref:.3f}" if self.delta_to_ref is not None else ""
        return (
            f"BFE H={self.entropy_bits:.3f} bit  "
            f"norm={self.normalized:.3f}  runs={self.n_runs}{d}"
        )


def _bidi_bucket(ch: str) -> str:
    cls = unicodedata.bidirectional(ch) or "ON"
    return _BIDI_BUCKET.get(cls, "N")


def _bidi_runs(text: str) -> list[str]:
    runs: list[str] = []
    prev = None
    for ch in text:
        if ch in "\r\n":
            prev = None
            continue
        b = _bidi_bucket(ch)
        if b != prev:
            runs.append(b)
            prev = b
    return runs


def bidi_flow_entropy(text: str, reference: str | None = None) -> BFEReport:
    """
    Lower normalized BFE ≈ cleaner directional flow.
    For Arabic recovery, hyp should approach the reference's BFE, not zero
    (a pure LTR English string has low H too — delta_to_ref is the signal).
    """
    runs = _bidi_runs(text)
    hist = Counter(runs)
    n = len(runs) or 1
    H = 0.0
    for c in hist.values():
        p = c / n
        H -= p * math.log2(p)
    k = len(hist) or 1
    norm = H / math.log2(k) if k > 1 else 0.0

    delta = None
    if reference is not None:
        ref_rep = bidi_flow_entropy(reference, reference=None)
        delta = abs(norm - ref_rep.normalized)

    return BFEReport(
        entropy_bits=round(H, 4),
        normalized=round(norm, 4),
        n_runs=len(runs),
        run_histogram=dict(hist),
        delta_to_ref=round(delta, 4) if delta is not None else None,
    )


# ── SHDR ────────────────────────────────────────────────────────────────


@dataclass
class SHDRReport:
    """
    Semantic Homoglyph Drift Rate.

    * drift_rate — homoglyph codepoints / Arabic letters in hypothesis
    * aligned_homoglyph_fraction — of letter substitutions vs ref, share that
      are pure lookalike pairs (ی/ي, ھ/ه, …)
    * true_letter_error_rate — letter CER after folding lookalikes (content errors)
    * raw_letter_error_rate — letter CER without folding (includes drift)
    """

    drift_rate: float
    n_homoglyphs: int
    n_arabic_letters: int
    aligned_homoglyph_fraction: float
    true_letter_error_rate: float
    raw_letter_error_rate: float

    def __str__(self) -> str:
        return (
            f"SHDR drift={self.drift_rate:.3f}  "
            f"true_err={self.true_letter_error_rate:.3f}  "
            f"raw_err={self.raw_letter_error_rate:.3f}"
        )


def homoglyph_drift(reference: str, hypothesis: str) -> SHDRReport:
    from .evaluate import cer

    letters = _arabic_letters(hypothesis)
    n_h = sum(1 for c in letters if c in _HOMOGLYPHS)
    n_l = len(letters) or 1
    drift = n_h / n_l

    ref_raw = _arabic_letters(reference)
    hyp_raw = letters
    raw_err = cer(ref_raw, hyp_raw).rate if ref_raw else 0.0
    if ref_raw:
        true_err = cer(
            fold_pdf_homoglyphs(ref_raw),
            fold_pdf_homoglyphs(hyp_raw),
        ).rate
    else:
        true_err = 0.0

    # Aligned substitutions that are homoglyph pairs
    sm = SequenceMatcher(None, list(ref_raw), list(hyp_raw), autojunk=False)
    subs = homo_subs = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        for a, b in zip(ref_raw[i1:i2], hyp_raw[j1:j2]):
            subs += 1
            if (
                _HOMOGLYPH_TO_CANON.get(b, b) == a
                or _HOMOGLYPH_TO_CANON.get(a, a) == b
                or (a != b and fold_pdf_homoglyphs(a) == fold_pdf_homoglyphs(b))
            ):
                homo_subs += 1
    homo_frac = homo_subs / subs if subs else 0.0

    return SHDRReport(
        drift_rate=round(drift, 4),
        n_homoglyphs=n_h,
        n_arabic_letters=len(letters),
        aligned_homoglyph_fraction=round(homo_frac, 4),
        true_letter_error_rate=round(true_err, 4),
        raw_letter_error_rate=round(raw_err, 4),
    )


# ── aggregate ───────────────────────────────────────────────────────────


@dataclass
class ScientificReport:
    label: str
    mcs: MCSReport
    dbr: DBRReport
    bfe: BFEReport
    shdr: SHDRReport

    def summary_lines(self) -> list[str]:
        return [
            f"[{self.label}]",
            f"  {self.mcs}",
            f"  {self.dbr}",
            f"  {self.bfe}",
            f"  {self.shdr}",
        ]

    def __str__(self) -> str:
        return "\n".join(self.summary_lines())


def scientific_audit(
    reference: str,
    hypothesis: str,
    label: str = "hyp",
) -> ScientificReport:
    """Run MCS, DBR, BFE, SHDR for one hypothesis against *reference*."""
    return ScientificReport(
        label=label,
        mcs=morphological_continuity(reference, hypothesis),
        dbr=diacritic_base_matrix(reference, hypothesis),
        bfe=bidi_flow_entropy(hypothesis, reference=reference),
        shdr=homoglyph_drift(reference, hypothesis),
    )
