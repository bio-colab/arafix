#!/usr/bin/env python3
"""
مولّد ملف PDF معطوب عمداً — كي تجرّب المكتبة قبل أن تخاطر بملفٍّ يهمّك.

يحاكي هذا السكربت ما يفعله مُصدِّر PDF رديء بالضبط:

    ١. يطبخ الحروف إلى أشكالها الرسومية (U+FE70–FEFF).
    ٢. يخزّنها بترتيبها البصري (معكوسةً).
    ٣. يرسمها في الصفحة، فتبدو للعين سليمةً تماماً.

والنتيجة ملفٌّ يقرؤه البشر بلا عناء، وتعجز عنه أدوات بايثون —
وهو بعينه ما يشتكي منه الناس.

    python examples/make_broken_pdf.py broken.pdf
    arafix diagnose broken.pdf -v
    arafix extract  broken.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz  # PyMuPDF

# نستورد الجداول من المكتبة نفسها — لا نكرّرها. المولّد يعكس ما يصلحه
# المصلِح بالضبط، فيصير الاختبار دورةً مغلقة.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from arafix.unicode_tables import PF_JOINING_FORM, PF_TO_BASE, JoiningForm  # noqa: E402

SAMPLE = [
    "دراسة مقارنة في السياسة العامة",
    "جامعة تكريت - كلية العلوم السياسية",
    "الفصل الثاني: مراجعة الأدبيات",
    "نُشرت هذه الدراسة عام 2024 في مجلة محكمة",
    "المؤشر GDP ارتفع بنسبة 3.5 بالمئة",
]

#: حروف لا تتصل بما بعدها — بعدها يبدأ الحرف التالي من جديد.
_NON_JOINING = set("ادذرزوأإآؤءة")

_BY_FORM: dict[tuple[str, JoiningForm], str] = {}
for _pf, _base in PF_TO_BASE.items():
    if len(_base) == 1:
        _BY_FORM.setdefault((_base, PF_JOINING_FORM[_pf]), _pf)


def shape(text: str) -> str:
    """يطبخ النص إلى أشكاله الرسومية — عكس ما تفعله الدرجة ١ تماماً."""
    out = []
    prev_joins = False
    for i, ch in enumerate(text):
        nxt = text[i + 1] if i + 1 < len(text) else ""
        joins_next = bool(nxt) and (nxt in PF_TO_BASE.values() or "\u0600" <= nxt <= "\u06FF")
        joins_next = joins_next and ch not in _NON_JOINING and nxt not in " \n\t"

        if prev_joins and joins_next:
            form = JoiningForm.MEDIAL
        elif prev_joins:
            form = JoiningForm.FINAL
        elif joins_next:
            form = JoiningForm.INITIAL
        else:
            form = JoiningForm.ISOLATED

        out.append(_BY_FORM.get((ch, form), _BY_FORM.get((ch, JoiningForm.ISOLATED), ch)))
        prev_joins = joins_next
    return "".join(out)


def to_visual(line: str) -> str:
    """
    يبني الترتيب البصري — كما يفعل المُصدِّر حين يرسم السطر.

    نستعمل `reverse_visual_line` من المكتبة نفسها، لا `line[::-1]`، لأن
    التحويل **انعكاسيّ** (involution): الدالة التي تحوّل البصريَّ منطقياً
    هي عينها التي تحوّل المنطقيَّ بصرياً. فالمولّد والمصلِح وجهان لمعادلة
    واحدة، وهذا ما يجعل الاختبار دورةً مغلقةً حقاً لا محاكاةً تقريبية.

    ولاحظ: المُصدِّر الواقعي **لا يعكس الأرقام** — «2024» تبقى «2024».
    من يحاكيه بـ `[::-1]` يحاكي عطباً لا وجود له.
    """
    from arafix.order import reverse_visual_line

    return reverse_visual_line(line)


def find_font() -> str:
    """يبحث عن خطٍّ يغطّي الأشكال الرسومية العربية."""
    candidates = [
        "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    raise SystemExit("لم أجد خطاً عربياً. مرّر مساراً: make_broken_pdf.py out.pdf /path/font.ttf")


def build(out_path: str, font_path: str | None = None) -> None:
    font_path = font_path or find_font()
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_font(fontname="ar", fontfile=font_path)

    y = 90
    for line in SAMPLE:
        broken = to_visual(shape(line))
        page.insert_text((70, y), broken, fontname="ar", fontsize=16)
        y += 40

    doc.save(out_path)
    doc.close()
    print(f"كُتب ملف معطوب عمداً: {out_path}")
    print("جرّب:  arafix diagnose", out_path, "-v")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "broken.pdf"
    font = sys.argv[2] if len(sys.argv) > 2 else None
    build(out, font)
