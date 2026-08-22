"""القياس الحاسم: شواهد الاتجاه على مخرَج PyMuPDFExtractor نفسه."""
import re  # noqa: E402
import sys  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "../..")

import fitz  # noqa: E402

from arafix.diagnose import (  # noqa: E402
    _signal_definite_article,
    _signal_final_only_letters,
    _signal_joining_forms,
    detect_visual_order,
)
from arafix.extractors import PyMuPDFExtractor  # noqa: E402
from arafix.hygiene import sanitize_extraction  # noqa: E402
from arafix.normalize import fold_simple_forms  # noqa: E402

TOKEN = "[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+"


def witnesses(label: str, text: str) -> None:
    tokens = re.findall(TOKEN, text)
    fo = _signal_final_only_letters(tokens)
    jn = _signal_joining_forms(text)
    da = _signal_definite_article(tokens)
    print(f"--- {label} ---")
    print("  final_only:", fo)
    print("  joining   :", jn)
    print("  article   :", da)
    score, _ = detect_visual_order(fold_simple_forms(text), shaped_source=text)
    print(f"  الدرجة المركبة على هذا النص: {score:+.3f}")
    print()


# 1) قراءة MuPDF النصية المباشرة (ما قستُه سابقاً)
raw_fitz = fitz.open("pdfs/relativity.pf_visual.pdf")[0].get_text()
witnesses("fitz.get_text() خام", raw_fitz)

# 2) مخرَج المستخرج الفعلي الذي يمر في الأنبوب
ex = PyMuPDFExtractor(layout_mode="auto")
pages = list(ex.pages("pdfs/relativity.pf_visual.pdf"))
raw_extractor = pages[0].text
witnesses("PyMuPDFExtractor.pages()[0].text", raw_extractor)

# 3) بعد hygiene كما في الأنبوب
cleaned = sanitize_extraction(raw_extractor)
witnesses("بعد sanitize_extraction", cleaned)

# 4) بعد التطبيع (النص الذي تقيسه بوابة الدرجة ٢ فعلاً)
folded = fold_simple_forms(cleaned)
witnesses("المطبَّع (دخل البوابة)", folded)

print("=== هل مخرجا get_text والمستخرج متطابقان؟ ===")
print("مطابق حرفياً:", raw_fitz == raw_extractor)
if raw_fitz != raw_extractor:
    print(f"أطوال: fitz={len(raw_fitz)} extractor={len(raw_extractor)}")
    print("fitz أول 120 :", repr(raw_fitz[:120]))
    print("extr أول 120 :", repr(raw_extractor[:120]))
