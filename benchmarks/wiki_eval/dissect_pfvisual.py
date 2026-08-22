"""تشريح مباشر: أين تدخل forward_flank_marks في ملفٍ منطقيٍّ التخزين؟"""
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "../..")

from arafix import PipelineConfig, extract_pdf  # noqa: E402
from arafix.diagnose import detect_visual_order, diagnose  # noqa: E402

slug, mode = "relativity", "pf_visual"
pdf = f"pdfs/{slug}.{mode}.pdf"

cfg_off = PipelineConfig()
cfg_on = PipelineConfig(forward_flank_marks=True)

r_off = extract_pdf(pdf, cfg_off)
r_on = extract_pdf(pdf, cfg_on)

print("=== مراحل كل صفحة ===")
for i, (po, pn) in enumerate(zip(r_off.pages, r_on.pages)):
    so = [s.value for s in po.repair.stages_applied]
    sn = [s.value for s in pn.repair.stages_applied]
    same_text = po.text == pn.text
    print(f"p{i+1}: نفس النص={same_text}")
    if not same_text:
        print("   off:", so)
        print("   on :", sn)

# درجة الاتجاه للاستخراج الخام لهذا الملف
import fitz  # noqa: E402

doc = fitz.open(pdf)
raw = "\n".join(p.get_text() for p in doc)
doc.close()
score, evs = detect_visual_order(raw)
print(f"\nدرجة الاتجاه على الخام: {score:+.3f} | العتبة 0.30")
for e in evs:
    print(f"   {e.name}: {e.value:+.2f} — {e.detail}")

# أين اختلف النص سطراً سطراً؟
print("\n=== فروق الأسطر ===")
shown = 0
lo = ln = 0
off_lines = r_off.pages[0].text.splitlines()
on_lines = r_on.pages[0].text.splitlines()
gold_lines = Path(f"articles/{slug}.gold.txt").read_text(encoding="utf-8").splitlines()
for i in range(max(len(off_lines), len(on_lines))):
    o = off_lines[i] if i < len(off_lines) else ""
    n = on_lines[i] if i < len(on_lines) else ""
    if o != n and shown < 6:
        shown += 1
        g_ctx = gold_lines[min(i, len(gold_lines) - 1)] if gold_lines else "?"
        print(f"L{i}:")
        print(f"   ذهب : {g_ctx[:70]!r}")
        print(f"   off : {o[:70]!r}")
        print(f"   on  : {n[:70]!r}")

# هل بوابة العكس اشتغل أصلاً؟ شخّص خام الصفحة الأولى
dg = diagnose(raw[:3000])
print("\nتشخيص الخام: defects=", [d.value for d in dg.defects])
