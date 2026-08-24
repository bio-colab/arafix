"""مولّد الـfixtures المُعنونة لطبقة Glyph Evidence.

يبني PDF واحد طبقةُ ToUnicode فيه مفسودةٌ عمداً وبشكلٍ متحيّن: كل cid
تعادُ قيمتُه اليونيكودية بحرفٍ «كاذب» بينما الخط المضمّن (Amiri، رخصة
OFL) يحفظ الحقيقة في جدول cmap وأسماء الجليفات.

الفساد: كل cid تطبّعُ قيمتُه إلى «ه» يُبلَّغ عنه لاحقاً بـ«ة».
الذهب: gold_manifest.json يسجّل cids المفسودة وحقيقتها والنصوص الأصلية،
وهو العقد الذي تتحقق منه بوابات القياس واختبارات H14.

    python benchmarks/glyph_fixtures/make_fixtures.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import fitz  # noqa: E402

from arafix.unicode_tables import PF_TO_BASE  # noqa: E402

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
FONT_PATH = ROOT / "fonts" / "Amiri-Regular.ttf"

#: زوج الالتباس المُصنَّع في هذا الإصدار: (الحقيقة، الكذبة)
PAIR = ("ه", "ة")

TRUE_LINES = [
    "الشهادة الرسمية ظهرت",
    "الهلال فوق الفهري",
    "شاهد هدى وهب الجامعة",
]

#: صفحات السياق النظيف (مصدر DocumentContext) — جيران ≥3 أحرف دائماً.
CONTEXT_LINES = [
    "الشهادة الرسمية وصلت المحكمة",
    "ظهرت الشهادة أمام القضاة",
    "الهلال يظهر فوق المدرسة",
    "الفهري يدرس داخل الجامعة",
    "شاهد المحقق هدى وهب المسيرة",
    "المحقق ينشر الدليل والوثيقة",
]


def normalize(ch: str) -> str:
    """طبّع شكل العرض إلى حرف أساسي (فلسفة arafix نفسها)."""
    return PF_TO_BASE.get(ch, ch)


def parse_cmap(stream: str) -> dict[int, int]:
    """يحلّل ToUnicode إلى قاموس cid ← codepoint (bfrange ثم bfchar)."""
    cid2uni: dict[int, int] = {}
    for m in re.finditer(r"beginbfrange(.*?)endbfrange", stream, re.S):
        for line in re.finditer(r"<([0-9A-Fa-f]+)> <([0-9A-Fa-f]+)> <([0-9A-Fa-f]+)>",
                                m.group(1)):
            lo, hi, v = (int(g, 16) for g in line.groups())
            for i in range(hi - lo + 1):
                cid2uni[lo + i] = v + i
    for m in re.finditer(r"beginbfchar(.*?)endbfchar", stream, re.S):
        for line in re.finditer(r"<([0-9A-Fa-f]{4})> <([0-9A-Fa-f]+)>", m.group(1)):
            cid, val = int(line.group(1), 16), line.group(2)
            cid2uni[cid] = int(val[:4], 16)
    return cid2uni


def rebuild_cmap(cid2uni: dict[int, int]) -> bytes:
    """يعيد توليد CMap نظيف البنية (كتل bfchar بحدّ 100 مدخلة)."""
    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo <</Registry(Adobe)/Ordering(UCS)/Supplement 0>> def",
        "/CMapName /Adobe-Identity-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    entries = sorted(cid2uni.items())
    for i in range(0, len(entries), 100):
        chunk = entries[i:i + 100]
        lines.append(f"{len(chunk)} beginbfchar")
        lines += [f"<{cid:04x}> <{uni:04X}>" for cid, uni in chunk]
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop",
              "end", "end"]
    return "\n".join(lines).encode("latin-1")


def main() -> int:
    if not FONT_PATH.exists():
        print(f"FAIL: الخط المصدري غائب: {FONT_PATH}")
        return 1
    ASSETS.mkdir(exist_ok=True)

    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="ar", fontfile=str(FONT_PATH))
    y = 72.0
    for ln in TRUE_LINES:
        page.insert_text((72, y), ln, fontname="ar", fontsize=14)
        y += 26.0

    font_xref = doc.get_page_fonts(page.number)[0][0]
    tou_xref = int(doc.xref_get_key(font_xref, "ToUnicode")[1].split()[0])
    cid2uni = parse_cmap(doc.xref_stream(tou_xref).decode("latin-1"))

    true_ch, lie_ch = PAIR
    corrupted_cids = {
        cid: uni for cid, uni in cid2uni.items() if normalize(chr(uni)) == true_ch
    }
    if not corrupted_cids:
        print("FAIL: لم يُعثر على أي cid لحرف الحقيقة — تحقق من تغطية الخط")
        return 1
    for cid in corrupted_cids:
        cid2uni[cid] = ord(lie_ch)

    doc.update_stream(tou_xref, rebuild_cmap(cid2uni))
    pdf_path = ASSETS / f"glyph_{true_ch}_to_{lie_ch}.pdf"
    doc.save(pdf_path)

    manifest = {
        "schema": "arafix.glyph-fixture.v1",
        "font": "Amiri-Regular.ttf (SIL OFL 1.1)",
        "pair": {"true": true_ch, "lie": lie_ch},
        "corrupted_cids": {str(cid): chr(uni) for cid, uni in sorted(corrupted_cids.items())},
        "truth_lines": TRUE_LINES,
        "context_lines": CONTEXT_LINES,
    }
    manifest_path = ASSETS / "gold_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"fixture : {pdf_path.name}")
    print(f"gold    : {manifest_path.name}")
    print(f"cids مفسودة: {len(corrupted_cids)} "
          f"({sorted({chr(u) for u in corrupted_cids.values()})} -> {lie_ch})")
    print("PASS: التوليد تم")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
