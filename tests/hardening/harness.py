"""
أدوات مشتركة لحملة ARAFIX HARDENING.

مبادئ الحقيبة:
  * لا اختبار يفحص سلوكاً افتراضياً — كل فحص يستدعي الكود الحقيقي.
  * كل عتبة تُهاجَم من الجانبين (تحتها وفوقها).
  * الفروق تُصنَّف: مقصود/غير مقصود — الغير مقصود فشلٌ صريح.
"""
from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# مولدات النصوص العدائية
# ---------------------------------------------------------------------------

ARABIC_WORDS = [
    "الكتاب", "علم", "المجلات", "الثالث", "خالد", "مدرسة", "القمر",
    "صلى", "الله", "عليه", "وسلم", "رضي", "عنه", "الحقيقة",
]
ENGLISH_WORDS = ["Report", "GDP", "USD", "v1.2.3", "project_v2.py"]
DIGITS = ["2024", "125", "3.5", "1,250.00"]
PUNCT = ["(", ")", "،", "؛", ".", ":", "-", "/", "%", "$", "+", "=", "«", "»"]
BIDI_CONTROLS = ["\u200f", "\u200e", "\u202b", "\u202c"]  # RLE/LRE/PDF
ZW = ["\u200c", "\u200d", "\u200b"]  # ZWNJ/ZWJ/ZWSP
PF_SAMPLE = ["\ufee3", "\ufeae", "\ufea3", "\ufe92", "\ufe8e", "\ufefb"]
HARAKAT = ["\u064b", "\u064c", "\u064d", "\u064e", "\u064f", "\u0650",
           "\u0651", "\u0652", "\u0653", "\u0654", "\u0655", "\u0670"]
QURANIC_MARKS = [chr(c) for c in list(range(0x06D6, 0x06DD)) + list(range(0x06DF, 0x06E9))]


def seeded(rng_seed: int = 20260822) -> random.Random:
    return random.Random(rng_seed)


def mixed_line(rng: random.Random, n_segments: int = 8) -> str:
    """سطر مختلط الاتجاه من شرائح واقعية."""
    pools = [ARABIC_WORDS, ENGLISH_WORDS, DIGITS, PUNCT]
    parts = []
    for _ in range(n_segments):
        pool = rng.choice(pools)
        parts.append(rng.choice(pool))
    line = " ".join(parts)
    if rng.random() < 0.3:
        line = f"({line})"
    if rng.random() < 0.2:
        i = rng.randrange(len(line))
        line = line[:i] + rng.choice(PUNCT) + line[i:]
    return line


def vocalized(word: str, density: float = 1.0, rng: random.Random | None = None) -> str:
    """يضيف حركاتٍ لكلمات بنسبة تغطية معينة."""
    out = []
    for ch in word:
        out.append(ch)
        if ("\u0621" <= ch <= "\u064a") and (rng is None or rng.random() < density):
            out.append(rng.choice(HARAKAT) if rng else HARAKAT[3])  # fatha default
    return "".join(out)


# ---------------------------------------------------------------------------
# محرك طفرات الحركات (H11)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarkMutation:
    kind: str          # move|delete|duplicate|detach|reverse_run|re_anchor|cross_letter|cross_word
    position: int
    detail: str = ""


def split_marks(text: str) -> list[tuple[str, str]]:
    """(حرف أساسي، جريان علاماته) — المحارف غير العربية وحدات مستقلة."""
    units: list[tuple[str, str]] = []
    for ch in text:
        if unicodedata.category(ch) == "Mn" and units:
            base, marks = units[-1]
            units[-1] = (base, marks + ch)
        else:
            units.append((ch, ""))
    return units


def mutate_marks(
    text: str,
    kind: str,
    rng: random.Random,
    count: int = 1,
) -> tuple[str, list[MarkMutation]]:
    """يطبّق طفراتٍ على مواضع الحركات ويُرجع النص المتحول وسجل الطفرات."""
    mutations: list[MarkMutation] = []
    for _ in range(count):
        units = split_marks(text)
        marked_idx = [i for i, (_, m) in enumerate(units) if m]
        if not marked_idx:
            break
        src_i = rng.choice(marked_idx)
        base, marks = units[src_i]
        mi = rng.randrange(len(marks))
        mark = marks[mi]
        remaining = marks[:mi] + marks[mi + 1:]
        units[src_i] = (base, remaining)

        if kind == "delete":
            mutations.append(MarkMutation(kind, src_i, mark))
        elif kind == "duplicate":
            units[src_i] = (base, marks + mark)
            mutations.append(MarkMutation(kind, src_i, mark))
        elif kind == "move":
            dst = rng.randrange(len(units))
            b2, m2 = units[dst]
            units[dst] = (b2, m2[:mi % (len(m2) + 1)] + mark + m2[mi % (len(m2) + 1):])
            mutations.append(MarkMutation("move", dst, f"{mark} من {src_i} إلى {dst}"))
        elif kind == "reverse_run":
            units[src_i] = (base, marks[::-1])
            mutations.append(MarkMutation("reverse_run", src_i, marks))
        elif kind == "cross_letter":
            others = [i for i in range(len(units)) if i != src_i and units[i][0] != " "]
            if not others:
                units[src_i] = (base, marks)
                break
            dst = rng.choice(others)
            b2, m2 = units[dst]
            units[dst] = (b2, m2 + mark)
            mutations.append(MarkMutation("cross_letter", dst, f"{mark} من {base} إلى {b2}"))
        elif kind == "detach":
            mutations.append(MarkMutation("detach", src_i, mark))
        else:
            raise ValueError(kind)

    return "".join(b + m for b, m in units), mutations


# ---------------------------------------------------------------------------
# مصفوفة الإعدادات (H7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigVariant:
    name: str
    overrides: dict = field(default_factory=dict)


CONFIG_MATRIX: list[ConfigVariant] = [
    ConfigVariant("default"),
    ConfigVariant("audit-full", {"audit_mode": "full"}),
    ConfigVariant("density", {"confidence_mode": "density"}),
    ConfigVariant("forward-marks", {"forward_flank_marks": True}),
    ConfigVariant("no-spacing", {"enable_spacing_repair": False}),
    ConfigVariant("no-confusions", {"enable_pdf_confusion_repair": False}),
    ConfigVariant("no-lamalef", {"enable_lam_alef_repair": False}),
    ConfigVariant("no-hygiene", {"enable_hygiene": False}),
    ConfigVariant("no-reorder", {"enable_reorder": False}),
    ConfigVariant("no-normalize", {"enable_normalize": False}),
    ConfigVariant("no-mojibake", {"enable_mojibake_fix": False}),
    ConfigVariant("linear-layout", {"layout": "linear"}),
]


# ---------------------------------------------------------------------------
# أدوات المقارنة
# ---------------------------------------------------------------------------


def letter_skeleton(t: str) -> str:
    """الهيكل الحرفي فقط: بلا فراغات ولا ترقيم ولا علامات."""
    return "".join(
        c
        for c in t
        if (
            "\u0621" <= c <= "\u064a"
            or "\u0671" <= c <= "\u06d3"
            or c.isascii()
            and (c.isalnum())
        )
    )


def unexpected_mutations(
    gold_logical: str, repaired_visual_order_input: str, out: str
) -> list[str]:
    """
    لفحص Bidi: المخرج الصحيح هو الذهب المنطقي نفسه (لأن المدخل انعكاسُه).
    نرجع قائمة الاختلافات الوصفية إن وُجدت.
    """
    import difflib

    sm = difflib.SequenceMatcher(None, gold_logical, out, autojunk=False)
    diffs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            diffs.append(f"{tag}: {gold_logical[i1:i2][:20]!r}->{out[j1:j2][:20]!r}")
    return diffs
