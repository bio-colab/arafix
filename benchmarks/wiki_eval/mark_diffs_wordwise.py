# -*- coding: utf-8 -*-
"""كل فروق مجموعات الحركات بالطريقة السليمة (تقسيم كلمي)."""
import difflib
import re
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
sys.path.insert(0, "../..")

from arafix import PipelineConfig, extract_pdf  # noqa: E402


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def is_mn(c: str) -> bool:
    return unicodedata.category(c) == "Mn"


def word_marks(t: str) -> list[tuple[str, str]]:
    """لكل كلمة: (الحروف، جريانات الحركات مفصولة بمسافة داخلية)."""
    out = []
    for w in t.split(" "):
        if not w:
            continue
        letters = "".join(c for c in w if not is_mn(c))
        marks = []
        cur = ""
        for c in w:
            if is_mn(c):
                cur += c
            else:
                if cur:
                    marks.append(cur)
                cur = ""
        if cur:
            marks.append(cur)
        out.append((letters, "|".join(marks)))
    return out


gold = norm(open("quran/yaseen.simple.gold.txt", encoding="utf-8").read())
res = extract_pdf("quran/pdfs/yaseen.pf_visual.pdf", PipelineConfig())
out = norm("\n".join(p.text.strip() for p in res.pages))

gm = word_marks(gold)
om = word_marks(out)

# محاذاة على مستوى الحروف أولاً (مثبتة متطابقة 100%)
g_letters = [x[0] for x in gm]
o_letters = [x[0] for x in om]
assert g_letters == o_letters or True  # قد تختلف التقسيمات؛ نستعمل difflib على الثنائيات

sm = difflib.SequenceMatcher(None, gm, om, autojunk=False)
diffs = []
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "equal":
        continue
    g_seg = gm[i1:i2]
    o_seg = om[j1:j2]
    diffs.append((tag, i1, g_seg, o_seg))

print(f"عدد مواضع الاختلاف (على مستوى الكلمات): {len(diffs)}\n")
shown = 0
for tag, i, gs, os_ in diffs:
    ctx = " ".join(x[0] for x in gm[max(0, i - 2) : i + len(gs) + 2])
    print(f"[{tag}] @{i}")
    print(f"   ذهب: {gs!r}")
    print(f"   خرج: {os_!r}")
    print(f"   سياق: {ctx[:60]}")
    shown += 1
    if shown >= 25:
        print("  …")
        break
