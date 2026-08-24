"""مولّد مدونة الـfixtures المُعنونة لطبقة Glyph Evidence (v2).

يبني PDF لكل زوج التباسٍ: طبقةُ `ToUnicode` فيه مفسودةٌ عمداً — كل cid
تعادُ قيمتُه اليونيكودية بحرفٍ «كاذب» بينما الخط المضمّن (Amiri، رخصة
OFL) يحفظ الحقيقة في جدول cmap وأسماء الجليفات.

الأزواج الأربعة (كلٌّ في وثيقةٍ مستقلة كي يبقى الذهب نقيَّ التفسير):
  ه→ة · ي→ى · د→ذ · ر→ز

تصميم كل حالة:
  * صفحة هدف تحوي كلمات الهدف + ضوابط FPR حقيقية (حرف الكذبة أصلاً).
  * سياقات نظيفة تغطي كل كلمات الهدف بجيران ≥3 أحرف.

الذهب: gold_manifest.json بعقد arafix.glyph-fixture.v2 (قائمة حالات).

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

#: تعريف الحالات — الحقيقة، الكذبة، صفحة الهدف، السياقات النظيفة.
CASES: list[dict] = [
    {
        "key": "heh_teh",
        "true": "ه",
        "lie": "ة",
        "truth_lines": [
            "الشهادة الرسمية ظهرت",
            "الهلال فوق الفهري",
            "شاهد هدى وهب الجامعة",
        ],
        "context_lines": [
            "الشهادة الرسمية وصلت المحكمة",
            "ظهرت الشهادة أمام القضاة",
            "الهلال يظهر فوق المدرسة",
            "الفهري يدرس داخل الجامعة",
            "المحقق ينشر الدليل والوثيقة",
            "شاهد المحقق هدى وهب المسيرة",
        ],
    },
    {
        "key": "yeh_maksura",
        "true": "ي",
        "lie": "ى",
        # «على/الرصيف/مستشفى» ضوابط: ى حقيقية لا تُمسّ.
        "truth_lines": [
            "الفهري يدرس الدليل",
            "على الرصيف مستشفى",
            "وصل الدفتر الجديد",
        ],
        "context_lines": [
            "الفهري يدرس داخل الجامعة",
            "الدليل الرسمي وصل أمس",
            "على الرصيف وقف الطلاب",
            "المستشفى العام يستقبل الزوار",
            "وصل الدفتر الجديد صباحا",
            "الطلاب فوق الرصيف",
        ],
    },
    {
        "key": "dal_dhal",
        "true": "د",
        "lie": "ذ",
        # «الذهب/والذكر/هنا» ضوابط: ذ حقيقية. «إلى» جسرُ عباراتٍ نظيفٌ
        # يربط (ورد،إلى) و(إلى،المدينة) في سياقات الهدفين.
        "truth_lines": [
            "الدليل فوق الجدول",
            "ورد إلى المدينة",
            "الذهب والذكر هنا",
        ],
        "context_lines": [
            "الدليل الرسمي ورد أمام المحكمة",
            "الجدول الجديد شمل المدينة",
            "ورد إلى المدينة صباحا",
            "الذهب والذكر في النص القديم",
            "اليوم بدأت الجلسة الأولى",
        ],
    },
    {
        "key": "ra_zay",
        "true": "ر",
        "lie": "ز",
        # «الزيتون» ضابطة نقية: لا تحوي حرف الهدف إطلاقاً.
        "truth_lines": [
            "الترتيب الأول للرحلة",
            "النهر يجري فوق الصخر",
            "الزيتون في الحقل",
        ],
        "context_lines": [
            "الترتيب الجديد للرحلة صدر",
            "النهر يجري تحت الجسر الكبير",
            "زار الفريق الحقل أول الأمر",
            "الصخر كبير والنهر واسع",
            "الأول من الرحلة انتهى",
        ],
    },
    {
        # عائلة النقاط: ب/ت/ث
        "key": "ba_ta",
        "true": "ب",
        "lie": "ت",
        "truth_lines": [
            "كتب المحقق التقرير",
            "صبر الجميل عادة",
            "التاريخ والترتيب",
        ],
        "context_lines": [
            "كتب المحقق التقرير أمس",
            "صبر الجميل من الأخلاق",
            "التاريخ والترتيب في الأرشيف",
            "المحقق ينشر الدليل اليوم",
        ],
    },
    {
        # عائلة النقاط: ج/ح/خ
        "key": "kha_ha",
        "true": "خ",
        "lie": "ح",
        "truth_lines": [
            "الخبير يفحص الأثر",
            "الخلق والخير معا",
            "الحقيقة تهزم الزيف",
        ],
        "context_lines": [
            "الخبير يفحص الأثر القديم",
            "الخلق والخير في الكتاب",
            "الحقيقة تهزم الزيف دائما",
            "الأثر القديم يحكي",
        ],
    },
    {
        # عائلة النقاط: ص/ض
        "key": "dad_sad",
        "true": "ض",
        "lie": "ص",
        "truth_lines": [
            "العدل أساس الملك",
            "وضع القرض جانبا",
            "الصدق والصبر",
        ],
        "context_lines": [
            "العدل أساس الملك",
            "وضع القرض في البنك",
            "الصدق والصبر فضيلة",
            "الملك أمر بالعدل",
        ],
    },
    {
        # عائلة النقاط: ط/ظ
        "key": "tha_zal",
        "true": "ظ",
        "lie": "ط",
        "truth_lines": [
            "الظلم يظهر الحقيقة",
            "الظروف الصعبة تعلمنا",
            "الطيران فوق الطاولة",
        ],
        "context_lines": [
            "الظلم يظهر الحقيقة أخيرا",
            "الظروف الصعبة تعلمنا الكثير",
            "الطيران فوق الطاولة ممنوع",
            "الحقيقة انتصرت اليوم",
        ],
    },
    {
        # عائلة النقاط: س/ش
        "key": "shin_sin",
        "true": "ش",
        "lie": "س",
        "truth_lines": [
            "الشمس تشرق من الشرق",
            "شهود المشهد وصلوا",
            "السماء صافية",
        ],
        "context_lines": [
            "الشمس تشرق من الشرق",
            "شهود المشهد وصلوا",
            "السماء صافية والجو لطيف",
        ],
    },
    {
        # عائلة النقاط: ع/غ
        "key": "ayn_ghayn",
        "true": "غ",
        "lie": "ع",
        "truth_lines": [
            "الغيوم تغطي السماء",
            "اللغة العربية غنية",
            "العلم نور",
        ],
        "context_lines": [
            "الغيوم تغطي السماء",
            "اللغة العربية غنية بالفنون",
            "العلم نور والجهل ظلام",
        ],
    },
    {
        # عائلة الهمزة: ؤ/و
        "key": "waw_hamza",
        "true": "ؤ",
        "lie": "و",
        "truth_lines": [
            "المؤمن يؤمن بالغيب",
            "مؤذن رشيد",
            "الورود والرياض",
        ],
        "context_lines": [
            "المؤمن يؤمن بالغيب",
            "مؤذن رشيد في الحارة",
            "الورود والرياض جميلة",
        ],
    },
    {
        # عائلة الهمزة: ئ/ي
        "key": "yeh_hamza",
        "true": "ئ",
        "lie": "ي",
        "truth_lines": [
            "بئر الماء عميقة",
            "يئس الفريق من التأخير",
            "رأس المال",
        ],
        "context_lines": [
            "بئر الماء عميقة",
            "يئس الفريق من التأخير",
            "رأس المال كبير",
        ],
    },
    {
        # عائلة الهمزة: أ/ا — unify_alef=False افتراضياً فالتمييز ناجٍ
        "key": "alif_hamza",
        "true": "أ",
        "lie": "ا",
        "truth_lines": [
            "أخلاق المحكمين",
            "أرسل الرسالة اليوم",
            "الوفاء عمل",
        ],
        "context_lines": [
            "أخلاق المحكمين معروفة",
            "أرسل الرسالة اليوم",
            "الوفاء عمل الجميع",
        ],
    },
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


def build_case(case: dict) -> dict:
    """يبني وثيقة الحالة ويردّ سجلَّها للذهب."""
    true_ch, lie_ch = case["true"], case["lie"]
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="ar", fontfile=str(FONT_PATH))
    y = 72.0
    for ln in case["truth_lines"]:
        page.insert_text((72, y), ln, fontname="ar", fontsize=14)
        y += 26.0

    font_xref = doc.get_page_fonts(page.number)[0][0]
    tou_xref = int(doc.xref_get_key(font_xref, "ToUnicode")[1].split()[0])
    cid2uni = parse_cmap(doc.xref_stream(tou_xref).decode("latin-1"))

    corrupted = {
        cid: uni for cid, uni in cid2uni.items() if normalize(chr(uni)) == true_ch
    }
    if not corrupted:
        raise RuntimeError(f"لا cids لحرف الحقيقة «{true_ch}» في الخط")
    for cid in corrupted:
        cid2uni[cid] = ord(lie_ch)

    doc.update_stream(tou_xref, rebuild_cmap(cid2uni))
    pdf_path = ASSETS / f"glyph_{true_ch}_to_{lie_ch}.pdf"
    doc.save(pdf_path)
    return {
        "key": case["key"],
        "pair": {"true": true_ch, "lie": lie_ch},
        "pdf": pdf_path.name,
        "corrupted_cids": {str(c): chr(u) for c, u in sorted(corrupted.items())},
        "truth_lines": case["truth_lines"],
        "context_lines": case["context_lines"],
    }


def main() -> int:
    if not FONT_PATH.exists():
        print(f"FAIL: الخط المصدري غائب: {FONT_PATH}")
        return 1
    ASSETS.mkdir(exist_ok=True)

    records = []
    for case in CASES:
        rec = build_case(case)
        records.append(rec)
        print(f"{rec['pair']['true']}->{rec['pair']['lie']}: "
              f"{rec['pdf']} | cids={len(rec['corrupted_cids'])}")

    manifest = {
        "schema": "arafix.glyph-fixture.v2",
        "font": "Amiri-Regular.ttf (SIL OFL 1.1)",
        "cases": records,
    }
    (ASSETS / "gold_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nPASS: {len(records)} حالات مولدة — الذهب v2 كُتب")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
