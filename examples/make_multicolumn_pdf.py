#!/usr/bin/env python3
"""
يولّد PDF بعمودين عربيين + ترويسة + تذييل — لاختبار layout.

    python examples/make_multicolumn_pdf.py multi.pdf
    arafix extract multi.pdf --layout columns -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def find_font() -> str:
    for c in [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]:
        if Path(c).exists():
            return c
    raise SystemExit("لا خط عربي")


def build(out: str, font: str | None = None) -> None:
    font = font or find_font()
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="ar", fontfile=font)

    page.insert_text((180, 36), "صحيفة الجامعة — عدد تجريبي", fontname="ar", fontsize=14)

    right = [
        "في العمود الأيمن نقرأ أولاً",
        "لأن العربية من اليمين",
        "وهذا سطر ثالث يميني",
        "سطر رابع في اليمين",
        "وخامس يختتم العمود",
    ]
    left = [
        "ثم ننتقل للعمود الأيسر",
        "بعد انتهاء الأيمن",
        "سطر أيسر ثالث هنا",
        "سطر أيسر رابع",
        "وآخر سطر يساري",
    ]
    y = 100
    for line in right:
        page.insert_text((320, y), line, fontname="ar", fontsize=12)
        y += 30
    y = 100
    for line in left:
        page.insert_text((50, y), line, fontname="ar", fontsize=12)
        y += 30

    page.insert_text((260, 810), "الصفحة 1 من 1", fontname="ar", fontsize=10)
    doc.save(out)
    doc.close()
    print(f"كُتب: {out}")
    print(f"جرّب: arafix extract {out} --layout full")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "multi.pdf")
