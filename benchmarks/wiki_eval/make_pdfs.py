"""
يحوّل الملفات الذهبية إلى PDF بثلاثة أنماط تخزين — محاكاةً لأجيال
مولّدات PDF العربية التاريخية:

  clean      ترميزٌ يونيكودي منطقيّ بحروفٍ أساسية (المولّدات الحديثة)
             ← الاستخراج يعيد النص سليماً تقريباً (مجموعة ضبط).

  pf         أشكالٌ رسومية (U+FB50–FEFF) بترتيبٍ منطقي — أسلوب تحويلات
             Word/RTF القديمة عبر arabic_reshaper.

  pf_visual  أشكالٌ رسومية **بترتيبٍ بصري معكوس** (arabic_reshaper +
             python-bidi) — أسوأ حالة: تصديرات InDesign/Quark القديمة.

المهم لصحة التجربة: reportlab يكتب في content stream المحارفَ التي
نمررها وينشئ ToUnicode CMap لها، فاستخراجُ PyMuPDF يعيد **نفس النقاط**
التي خزّناها. فنحن نتحكم بالإتلاف تحكماً تاماً، والذهب هو ما قبل التحويل.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
ARTICLES_DIR = ROOT / "articles"
PDFS_DIR = ROOT / "pdfs"

# درسٌ موثَّق: إعداد arabic_reshaper الافتراضي يحذف الحركات
# (delete_harakat=True) فتُدمَّر معلومة قبل أن ترى المكتبة.
# نعطّله حتى يبقى الإتلافُ في بنية التخزين لا في محو المحتوى.
_RESHAPER = arabic_reshaper.ArabicReshaper(configuration={"delete_harakat": False})

FONT_PATH = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_NAME = "WikiEval-Arabic"
FONT_SIZE = 12
LEADING = FONT_SIZE * 1.7
MARGIN = 56
PAGE_W, PAGE_H = A4
TEXT_WIDTH = PAGE_W - 2 * MARGIN


def wrap_words(text: str, font: str, size: float, max_width: float) -> list[str]:
    """يلفّ الأسطر على الكلمات قبل أي تشكيل — الوصل لا يعبر حدود السطر."""
    lines: list[str] = []
    for para_line in text.split("\n"):
        if not para_line.strip():
            lines.append("")
            continue
        words = para_line.split(" ")
        current = ""
        for w in words:
            candidate = f"{current} {w}".strip()
            if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
    return lines


def transform(text: str, mode: str) -> str:
    """يطبّق نمط الإتلاف على نصٍّ منطقيٍّ بعد اللف."""
    if mode == "clean":
        return text
    if mode == "pf":
        return _RESHAPER.reshape(text)
    if mode == "pf_visual":
        return get_display(_RESHAPER.reshape(text))
    raise ValueError(f"نمط غير معروف: {mode}")


def render_pdf(out_path: Path, text: str, mode: str) -> int:
    """يرسم النص ويُرجع عدد الصفحات."""
    c = canvas.Canvas(str(out_path), pagesize=A4)
    c.setFont(FONT_NAME, FONT_SIZE)
    y = PAGE_H - MARGIN
    wrapped = wrap_words(text, FONT_NAME, FONT_SIZE, TEXT_WIDTH)
    pages = 1

    def flush_page() -> None:
        nonlocal y, pages
        c.showPage()
        c.setFont(FONT_NAME, FONT_SIZE)
        y = PAGE_H - MARGIN
        pages += 1

    # نلفّ ثم نحوّل: التشكيل سياقيٌّ داخل الكلمة لا عبر الفراغات.
    for src_line in wrapped:
        drawn = transform(src_line, mode)
        c.drawRightString(PAGE_W - MARGIN, y - FONT_SIZE, drawn)
        y -= LEADING
        if y < MARGIN + LEADING:
            flush_page()

    c.save()
    return pages  # noqa: F841 — العدد للاستعمال التشخيصي عند الحاجة


def main() -> int:
    if not FONT_PATH.exists():
        print(f"خط مفقود: {FONT_PATH}", file=sys.stderr)
        return 1
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))

    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    modes = ("clean", "pf", "pf_visual")
    manifest = json.loads((ROOT / "articles.json").read_text(encoding="utf-8"))
    slugs = [a["slug"] for a in manifest["articles"]]

    total = 0
    for slug in slugs:
        gold_path = ARTICLES_DIR / f"{slug}.gold.txt"
        if not gold_path.exists():
            print(f"  SKIP {slug} (لا ذهب)", file=sys.stderr)
            continue
        text = gold_path.read_text(encoding="utf-8")
        for mode in modes:
            out = PDFS_DIR / f"{slug}.{mode}.pdf"
            pages = render_pdf(out, text, mode)
            total += 1
        print(f"  OK   {slug:14s} ×{len(modes)} أنماط")

    print(f"\n{total} ملف PDF جاهز في {PDFS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
