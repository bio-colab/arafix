# -*- coding: utf-8 -*-
"""تشريح المجموعات الشاذة الـ30 في تسلسل حركات سورة يس."""
import re
import sys
import unicodedata
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
sys.path.insert(0, "../..")

from arafix import PipelineConfig, extract_pdf  # noqa: E402


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def is_mn(c: str) -> bool:
    return unicodedata.category(c) == "Mn"


def base_only(t: str) -> str:
    return "".join(c for c in t if "\u0621" <= c <= "\u064a" or "\u0671" <= c <= "\u06d3")


def mark_groups(t: str) -> list[tuple[str, int]]:
    """(جريان الحركات، فهرس الكلمة الحروفية)."""
    groups = []
    cur_marks = ""
    wi = -1
    prev_letter = False
    for c in t:
        if is_mn(c):
            cur_marks += c
            prev_letter = False
        elif "\u0621" <= c <= "\u064a" or "\u0671" <= c <= "\u06d3":
            if prev_letter and cur_marks:
                pass  # استمرار نفس الكلمة
            wi += 1 if cur_marks or prev_letter else 1
            if cur_marks:
                groups.append((cur_marks, wi))
            cur_marks = ""
            prev_letter = True
        # غير عربي/فراغ: نبدأ مجموعة جديدة عند أول حرف قادم
    return groups


gold = norm(open("quran/yaseen.simple.gold.txt", encoding="utf-8").read())
res = extract_pdf("quran/pdfs/yaseen.pf_visual.pdf", PipelineConfig())
out = norm("\n".join(p.text.strip() for p in res.pages))

# محاذاة مباشرة: النصان متطابقان بالحروف، إذن نفس المواضع — نقارن جريانات
# العلامات حول كل حرف عبر مسح متزامن.
pairs = []
gi = oi = 0
g_last_marks = o_last_marks = ""
while gi < len(gold) and oi < len(out):
    gc, oc = gold[gi], out[oi]
    if is_mn(gc) and is_mn(oc):
        g_run = o_run = ""
        while gi < len(gold) and is_mn(gold[gi]):
            g_run += gold[gi]
            gi += 1
        while oi < len(out) and is_mn(out[oi]):
            o_run += out[oi]
            oi += 1
        if g_run != o_run:
            ctx_g = gold[max(0, gi - 6) : min(len(gold), gi + 6)]
            pairs.append((g_run, o_run, ctx_g))
    elif is_mn(gc):
        g_run = ""
        while gi < len(gold) and is_mn(gold[gi]):
            g_run += gold[gi]
            gi += 1
        pairs.append((g_run, "(مفقود)", gold[max(0, gi - 6) : gi + 6]))
    elif is_mn(oc):
        o_run = ""
        while oi < len(out) and is_mn(out[oi]):
            o_run += out[oi]
            oi += 1
        pairs.append(("(زائد)", o_run, out[max(0, oi - 6) : oi + 6]))
    else:
        gi += 1
        oi += 1

print(f"إجمالي الجريانات الشاذة: {len(pairs)}\n")
patterns = Counter((g, o) for g, o, _ in pairs)
print("=== الأنماط المتكررة ===")
for (g, o), n in patterns.most_common():
    print(f"  ×{n:2d}  {g!r} → {o!r}")

print("\n=== السياقات ===")
for g, o, ctx in pairs[:30]:
    print(f"  {g!r}→{o!r} | …{ctx!r}…")
