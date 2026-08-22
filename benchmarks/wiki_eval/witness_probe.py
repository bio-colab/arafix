"""قياس الشواهد الثلاثة على النص المطبَّع نفسه الذي رأتَه بوابة الدرجة ٢."""
import sys  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "../..")

import fitz  # noqa: E402

from arafix.diagnose import (  # noqa: E402
    _signal_definite_article,
    _signal_final_only_letters,
    _signal_joining_forms,
)
from arafix.normalize import fold_simple_forms  # noqa: E402

raw = fitz.open("pdfs/relativity.pf_visual.pdf")[0].get_text()
folded = fold_simple_forms(raw)

print("=== أول 150 محرفاً من المطبَّع ===")
print(repr(folded[:150]))
print()

tokens_folded = __import__("re").findall(
    "[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+", folded
)
print("=== الشواهد على المطبَّع (كما تراه البوابة) ===")
r = _signal_final_only_letters(tokens_folded)
print("final_only :", r)
r = _signal_joining_forms(folded)   # بلا أشكال بعد الطيّ — غالباً لا شهادة
print("joining    :", r)
r = _signal_definite_article(tokens_folded)
print("article    :", r)

# وللمقارنة: الشواهد على الـPF الخام (قبل الطي)
tokens_raw = __import__("re").findall(
    "[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+", raw
)
print("\n=== على الـPF الخام ===")
r = _signal_joining_forms(raw)
print("joining(raw):", r)
