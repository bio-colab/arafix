"""
واجهة سطر الأوامر.

    arafix diagnose thesis.pdf
    arafix extract  thesis.pdf -o out.txt
    arafix eval     thesis.pdf --truth thesis.txt --compare
    arafix text     "ﺎﺒﺣﺮﻣ"
    arafix fonts    thesis.pdf

فلسفة الأمر `diagnose` أنه **لا يكتب شيئاً**. اقرأ تقريره أولاً، ثم
قرّر. الأداة التي تعالج قبل أن تُريك ما وجدت أداةٌ لا تُؤتمن.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .diagnose import diagnose
from .pipeline import PipelineConfig, extract_pdf, repair_text
from .unicode_tables import unicode_version


def _cmd_diagnose(args: argparse.Namespace) -> int:
    from .extractors import get_extractor

    ex = get_extractor(args.extractor)
    report = []
    for raw in ex.pages(args.path):
        dg = diagnose(raw.text)
        report.append(
            {
                "page": raw.number,
                "chars": dg.char_count,
                "arabic_ratio": round(dg.arabic_ratio, 3),
                "defects": [d.value for d in dg.defects],
                "confidence": dg.confidence,
                "fonts": raw.fonts,
                "evidence": [
                    {"name": e.name, "value": round(e.value, 3), "detail": e.detail}
                    for e in dg.evidence
                ],
            }
        )
        if args.pages and raw.number >= args.pages:
            break

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    for r in report:
        print(f"── صفحة {r['page']} " + "─" * 40)
        print(f"   العلل    : {'، '.join(r['defects'])}")
        print(f"   الثقة    : {r['confidence']}")
        print(f"   الحروف   : {r['chars']}  (عربية {r['arabic_ratio']:.0%})")
        if r["fonts"]:
            print(f"   الخطوط   : {', '.join(r['fonts'][:4])}")
        if args.verbose:
            for e in r["evidence"]:
                print(f"     · {e['name']:22s} {e['value']:+.3f}  {e['detail']}")
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    cfg = PipelineConfig(extractor=args.extractor, force_reorder=args.force_reorder)
    doc = extract_pdf(args.path, cfg)

    out = doc.text
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"كُتب {len(out)} حرفاً في {args.output}", file=sys.stderr)
    else:
        print(out)

    print(f"الثقة الدنيا عبر {len(doc.pages)} صفحة: {doc.confidence}", file=sys.stderr)
    if doc.confidence < 0.5:
        print("تحذير: ثقة منخفضة — راجع `arafix diagnose -v`", file=sys.stderr)
        return 2
    return 0


def _cmd_text(args: argparse.Namespace) -> int:
    src = args.text if args.text else sys.stdin.read()
    r = repair_text(src)
    print(r.text)
    if args.verbose:
        print(f"\n─ العلل: {r.diagnosis.summary()}", file=sys.stderr)
        print(f"─ المراحل: {[s.value for s in r.stages_applied]}", file=sys.stderr)
        print(f"─ الثقة: {r.confidence}", file=sys.stderr)
        for n in r.notes:
            print(f"  · {n}", file=sys.stderr)
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from .evaluate import EvalConfig, compare_extractors, evaluate_pdf

    cfg = EvalConfig(
        ignore_diacritics=args.ignore_diacritics,
        ignore_punctuation=args.ignore_punctuation,
    )
    reports = (
        compare_extractors(args.path, args.truth, cfg)
        if args.compare
        else [evaluate_pdf(args.path, args.truth, args.extractor, cfg)]
    )

    print("─" * 68)
    for r in reports:
        print(" ", r)
    print("─" * 68)

    best = reports[0]
    if args.verbose and best.worst_lines:
        print("\nأسوأ السطور في", best.label, ":")
        for i, ref, hyp in best.worst_lines:
            print(f"  سطر {i}")
            print(f"    المرجع : {ref[:70]!r}")
            print(f"    الناتج : {hyp[:70]!r}")

    if len(reports) > 1:
        gap = reports[-1].cer.rate - best.cer.rate
        print(f"\nأفضل مسار: {best.label} — يسبق أسوأهم بـ {gap:.2%} في CER")
    return 0 if best.cer.rate < 0.05 else 3


def _cmd_fonts(args: argparse.Namespace) -> int:
    from .cmap import build_glyph_map
    from .extractors import get_extractor

    ex = get_extractor(args.extractor)
    fonts = ex.font_bytes(args.path)
    if not fonts:
        print("لا خطوط مضمَّنة — الدرجة ٣ غير ممكنة على هذا الملف.")
        return 1
    for name, data in fonts.items():
        try:
            gm = build_glyph_map(data, name)
            print(f"{name:40s} تغطية {gm.coverage:.0%}  ثقة {gm.confidence}  ({gm.source})")
            for note in gm.notes:
                print(f"    ! {note}")
        except Exception as exc:
            print(f"{name:40s} تعذّر التحليل: {exc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="arafix", description="استرجاع النص العربي من ملفات PDF المعطوبة"
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"arafix {__version__} · unicode {unicode_version()}",
    )
    p.add_argument("-e", "--extractor", default="auto", help="محرّك القراءة (auto|pymupdf)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose", help="شخّص ولا تكتب شيئاً")
    d.add_argument("path")
    d.add_argument("-v", "--verbose", action="store_true", help="اعرض الشواهد")
    d.add_argument("--json", action="store_true")
    d.add_argument("-n", "--pages", type=int, default=0, help="حدّ الصفحات")
    d.set_defaults(func=_cmd_diagnose)

    x = sub.add_parser("extract", help="استخرج وأصلح")
    x.add_argument("path")
    x.add_argument("-o", "--output")
    x.add_argument("--force-reorder", action="store_true", help="اعكس بلا شاهد")
    x.set_defaults(func=_cmd_extract)

    t = sub.add_parser("text", help="أصلح نصاً مباشراً أو من stdin")
    t.add_argument("text", nargs="?")
    t.add_argument("-v", "--verbose", action="store_true")
    t.set_defaults(func=_cmd_text)

    v = sub.add_parser("eval", help="قِس مقابل حقيقةٍ مرجعية (CER/WER)")
    v.add_argument("path")
    v.add_argument("--truth", required=True, help="ملفٌ نصّيّ فيه النصّ الصحيح")
    v.add_argument("--compare", action="store_true", help="قِس كل المسارات ورتّبها")
    v.add_argument("--ignore-diacritics", action="store_true")
    v.add_argument("--ignore-punctuation", action="store_true")
    v.add_argument("-v", "--verbose", action="store_true", help="اسرد أسوأ السطور")
    v.set_defaults(func=_cmd_eval)

    f = sub.add_parser("fonts", help="افحص الخطوط المضمَّنة (الدرجة ٣)")
    f.add_argument("path")
    f.set_defaults(func=_cmd_fonts)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, KeyError, FileNotFoundError) as exc:
        print(f"خطأ: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
