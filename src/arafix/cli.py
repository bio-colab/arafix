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
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .diagnose import diagnose
from .pipeline import PipelineConfig, extract_pdf, repair_text
from .unicode_tables import unicode_version


def _nonneg_int(value: str) -> int:
    """argparse type: أعداد الصفحات يجب أن تكون صحيحة غير سالبة."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"رقم غير صالح: {value!r}") from None
    if n < 0:
        raise argparse.ArgumentTypeError(
            f"عدد الصفحات لا يقبل قيماً سالبة: {n}"
        )
    return n


def _ensure_utf8_stdio() -> None:
    """ثبّت ترميز UTF-8 للمداخل والمخارج القياسية.

    عند التحويل بأنبوب (pipe) على Windows يستخدم stdin/stdout ترميز صفحة
    الأكواد ANSI (cp1252/cp1256) وليس UTF-8، فانهار قراءة عربية أو — أسوأ —
    تُفكّ ترميزياً بصمت ثم «تُصلَّح» كنصٍّ معطوب. انظر PEP 540/597.
    """
    for stream, errors in (
        (sys.stdin, "strict"),
        (sys.stdout, "replace"),
        (sys.stderr, "replace"),
    ):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(OSError, ValueError):  # pragma: no cover
            reconfigure(encoding="utf-8", errors=errors)


def _cmd_diagnose(args: argparse.Namespace) -> int:
    from .extractors import get_extractor

    ex = get_extractor(args.extractor)
    report: list[dict[str, Any]] = []
    for raw in ex.pages(args.path):
        dg = diagnose(raw.text)
        report.append(
            {
                "page": raw.number,
                "chars": dg.char_count,
                "arabic_ratio": round(dg.arabic_ratio, 3),
                "defects": [d.value for d in dg.defects],
                "confidence": dg.confidence,
                "defect_confidence": {
                    k.value: v for k, v in dg.defect_confidence.items()
                },
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
        conf = r["defect_confidence"]
        detail = "، ".join(f"{d} ({conf.get(d, 0):.2f})" for d in r["defects"])
        print(f"   العلل    : {detail}")
        print(f"   الثقة    : {r['confidence']}  (أضعف حلقة)")
        print(f"   الحروف   : {r['chars']}  (عربية {r['arabic_ratio']:.0%})")
        if r["fonts"]:
            print(f"   الخطوط   : {', '.join(r['fonts'][:4])}")
        if args.verbose:
            for e in r["evidence"]:
                print(f"     · {e['name']:22s} {e['value']:+.3f}  {e['detail']}")
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    from .layout import LayoutConfig

    lay_cfg = LayoutConfig(reading_order=args.reading_order)
    cfg = PipelineConfig(
        extractor=args.extractor,
        force_reorder=args.force_reorder,
        layout=args.layout,
        layout_config=lay_cfg,
    )
    doc = extract_pdf(args.path, cfg)

    out = doc.text
    if args.output:
        if Path(args.output).resolve() == Path(args.path).resolve():
            raise RuntimeError(
                f"المخرج يطابق الملف المصدر ({args.output}) — الرفض يمنع "
                "محو الأصل؛ اختر اسماً مختلفاً لـ -o"
            )
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"كُتب {len(out)} حرفاً في {args.output}", file=sys.stderr)
    else:
        print(out)

    print(f"الثقة الدنيا عبر {len(doc.pages)} صفحة: {doc.confidence}", file=sys.stderr)
    if args.verbose:
        print(
            f"بنية: أعمدة≤{doc.metadata.get('max_columns', 1)} "
            f"جداول={doc.metadata.get('table_count', 0)} "
            f"layout={doc.metadata.get('layout')}",
            file=sys.stderr,
        )
        for p in doc.pages:
            if p.n_columns > 1 or p.tables:
                print(
                    f"  صفحة {p.page_number}: {p.n_columns} عمود، "
                    f"{len(p.tables)} جدول",
                    file=sys.stderr,
                )
        if args.tables and doc.all_tables:
            print("\n── جداول ──", file=sys.stderr)
            for i, grid in enumerate(doc.all_tables):
                print(f"جدول {i + 1}: {len(grid)}×{len(grid[0]) if grid else 0}", file=sys.stderr)
                for row in grid:
                    print("  | " + " | ".join(row) + " |")
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


def _cmd_blocks(args: argparse.Namespace) -> int:
    """أصلح سطوراً/خلايا من stdin (سطر = كتلة) — للجداول والأنابيب."""
    from .pipeline import repair_blocks
    from .types import TextBlock

    lines = [ln.rstrip("\n\r") for ln in sys.stdin]
    if args.skip_empty:
        lines = [ln for ln in lines if ln.strip()]
    blocks = [TextBlock(text=ln, id=f"L{i}", role="line") for i, ln in enumerate(lines)]
    out = repair_blocks(blocks)
    for b in out.blocks:
        print(b.text)
    if args.verbose:
        print(
            f"─ {len(out.blocks)} كتلة · ثقة دنيا {out.confidence}",
            file=sys.stderr,
        )
        n_changed = sum(1 for b in out.blocks if b.repair.changed)
        print(f"─ تغيّر منها: {n_changed}", file=sys.stderr)
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
    if not reports:
        raise RuntimeError(
            "لم ينتج أي مستخرج تقريراً — راجع رسائل الخطأ أعلاه"
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

    if getattr(args, "scientific", False):
        from .pipeline import extract_pdf
        from .scientific import scientific_audit

        truth = Path(args.truth).read_text(encoding="utf-8-sig")
        hyp = extract_pdf(args.path).text
        print("\n── scientific (MCS / DBR / BFE / SHDR) ──")
        print(scientific_audit(truth, hyp, label=best.label))

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
    d.add_argument("-n", "--pages", type=_nonneg_int, default=0, help="حدّ الصفحات")
    d.set_defaults(func=_cmd_diagnose)

    x = sub.add_parser("extract", help="استخرج وأصلح")
    x.add_argument("path")
    x.add_argument("-o", "--output")
    x.add_argument("--force-reorder", action="store_true", help="اعكس بلا شاهد")
    x.add_argument(
        "--layout",
        choices=["auto", "linear", "columns", "full"],
        default="auto",
        help="تحليل البنية: auto|linear|columns|full",
    )
    x.add_argument(
        "--reading-order",
        choices=["rtl", "ltr"],
        default="rtl",
        help="ترتيب قراءة الأعمدة (افتراضي rtl)",
    )
    x.add_argument("-v", "--verbose", action="store_true", help="اعرض ملخص البنية")
    x.add_argument("--tables", action="store_true", help="اطبع الجداول المستخرجة")
    x.set_defaults(func=_cmd_extract)

    t = sub.add_parser("text", help="أصلح نصاً مباشراً أو من stdin")
    t.add_argument("text", nargs="?")
    t.add_argument("-v", "--verbose", action="store_true")
    t.set_defaults(func=_cmd_text)

    b = sub.add_parser(
        "blocks",
        help="أصلح كتلًا مستقلة من stdin (سطر=كتلة) — جداول وأنابيب",
    )
    b.add_argument("-v", "--verbose", action="store_true")
    b.add_argument(
        "--skip-empty",
        action="store_true",
        help="تجاهل الأسطر الفارغة",
    )
    b.set_defaults(func=_cmd_blocks)

    v = sub.add_parser("eval", help="قِس مقابل حقيقةٍ مرجعية (CER/WER)")
    v.add_argument("path")
    v.add_argument("--truth", required=True, help="ملفٌ نصّيّ فيه النصّ الصحيح")
    v.add_argument("--compare", action="store_true", help="قِس كل المسارات ورتّبها")
    v.add_argument("--ignore-diacritics", action="store_true")
    v.add_argument("--ignore-punctuation", action="store_true")
    v.add_argument(
        "--scientific",
        action="store_true",
        help="MCS / DBR / BFE / SHDR (scientific layer)",
    )
    v.add_argument("-v", "--verbose", action="store_true", help="اسرد أسوأ السطور")
    v.set_defaults(func=_cmd_eval)

    f = sub.add_parser("fonts", help="افحص الخطوط المضمَّنة (الدرجة ٣)")
    f.add_argument("path")
    f.set_defaults(func=_cmd_fonts)

    return p


def _normalize_argv(argv: list[str]) -> list[str]:
    """
    تيسير سطر الأوامر (Smart CLI Routing):
    إذا مرّر المستخدم ملف PDF أو نصاً دون تحديد أمر فرعي صريح
    (مثل `arafix file.pdf` أو `arafix 'مرحبا'`)، نوجهه تلقائياً
    للأمر المناسب بدل رمي خطأ syntax غامض.
    """
    if not argv:
        return argv

    known_cmds = {
        "diagnose",
        "extract",
        "text",
        "blocks",
        "eval",
        "fonts",
        "-h",
        "--help",
        "-v",
        "--version",
    }

    first_non_opt_idx = -1
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-e", "--extractor"):
            i += 2
            continue
        if arg.startswith("-"):
            i += 1
            continue
        first_non_opt_idx = i
        break

    if first_non_opt_idx == -1:
        return argv

    first_arg = argv[first_non_opt_idx]
    if first_arg in known_cmds:
        return argv

    # لم يحدد أمراً فرعياً: خمن بذكاء
    if first_arg.lower().endswith(".pdf") or Path(first_arg).suffix.lower() == ".pdf":
        return argv[:first_non_opt_idx] + ["extract"] + argv[first_non_opt_idx:]

    return argv[:first_non_opt_idx] + ["text"] + argv[first_non_opt_idx:]


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    if argv is None:
        raw_argv = sys.argv[1:]
        # إذا كان الدخل من الطرفية واستُدعي بلا معاملات، تحقق إن كان أنبوباً
        is_tty = getattr(sys.stdin, "isatty", lambda: True)()
        if not raw_argv and not is_tty:
            raw_argv = ["text"]
    else:
        raw_argv = list(argv)

    if not raw_argv:
        build_parser().print_help()
        return 0

    norm_argv = _normalize_argv(raw_argv)
    args = build_parser().parse_args(norm_argv)
    try:
        return args.func(args)
    except (RuntimeError, KeyError, FileNotFoundError) as exc:
        print(f"خطأ: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
