# -*- coding: utf-8 -*-
"""تشريح الأخطاء المتبقية في yaseen.pf_visual (الوضع الأفضل)."""
import difflib
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "../..")

from arafix import PipelineConfig, extract_pdf  # noqa: E402


def is_mn(c: str) -> bool:
    return unicodedata.category(c) == "Mn"


gold = (Path("quran") / "yaseen.simple.gold.txt").read_text(encoding="utf-8")
res = extract_pdf("quran/pdfs/yaseen.pf_visual.pdf", PipelineConfig())
out = "\n".join(p.text.strip() for p in res.pages)

sm = difflib.SequenceMatcher(None, gold, out, autojunk=False)
kinds: Counter[str] = Counter()
samples: list[str] = []
shown = 0
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "equal":
        continue
    g, o = gold[i1:i2], out[j1:j2]
    if g.strip() == "" or o.strip() == "":
        kinds["مسافات"] += 1
        cause = "مسافة"
    else:
        gm = "".join(c for c in g if is_mn(c))
        om = "".join(c for c in o if is_mn(c))
        gl = "".join(c for c in g if not is_mn(c))
        ol = "".join(c for c in o if not is_mn(c))
        if gl == ol and gm != om:
            kinds["ترتيب/نوع الحركات"] += 1
            cause = f"حركات: ذهب={gm!r} خرج={om!r}"
        elif gl != ol and gm == om:
            kinds["حروف"] += 1
            cause = f"حروف: {gl!r}→{ol!r}"
        else:
            kinds["مختلط"] += 1
            cause = f"حروف {gl!r}→{ol!r} | حركات {gm!r}→{om!r}"
    if shown < 18:
        shown += 1
        samples.append(f"[{tag}] {cause}\n     سياق: …{gold[max(0,i1-20):i2+20]!r}")

print("=== تصنيف الأخطاء ===")
for k, v in kinds.most_common():
    print(f"  {k}: {v}")
print(f"  الإجمالي: {sum(kinds.values())}")
print("\n=== عينات ===")
for s in samples:
    print(" ", s)
