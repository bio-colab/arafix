"""تشريح جذري: لماذا فشلت مقالةٌ معينة؟ يعرض كل خطأٍ بسياقه وسببه."""
from __future__ import annotations  # noqa: E402

import difflib  # noqa: E402
import sys  # noqa: E402
import unicodedata  # noqa: E402
from pathlib import Path  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
from arafix import PipelineConfig, extract_pdf  # noqa: E402


def is_pf(ch: str) -> bool:
    return "\ufb50" <= ch <= "\ufeff"


def is_mn(ch: str) -> bool:
    return unicodedata.category(ch) == "Mn"


def show(slug: str, mode: str, max_show: int = 14) -> None:
    gold = (ROOT / "articles" / f"{slug}.gold.txt").read_text(encoding="utf-8")
    result = extract_pdf(str(ROOT / "pdfs" / f"{slug}.{mode}.pdf"), PipelineConfig())
    out = "\n\n".join(p.text for p in result.pages)

    sm = difflib.SequenceMatcher(None, gold, out, autojunk=False)
    print(f"===== {slug}.{mode} =====")
    shown = 0
    stats = {"equal": 0}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            stats["equal"] += i2 - i1
            continue
        g, o = gold[i1:i2], out[j1:j2]
        ctx_g = gold[max(0, i1 - 25) : i1] + "⟦" + g[:40] + "⟧" + gold[i2 : i2 + 25]
        causes = []
        if any(is_pf(c) for c in o):
            causes.append("PF متبقٍ")
        if o and not o.strip():
            causes.append("مسافة زائدة")
        if g and not g.strip():
            causes.append("مسافة مفقودة")
        if all(is_mn(c) for c in g.strip()) and g.strip():
            causes.append("حركة ساقطة")
        if not causes:
            causes.append("استبدال حروف")
        stats[causes[0]] = stats.get(causes[0], 0) + max(len(g), len(o), 1)
        if shown < max_show:
            shown += 1
            print(f"  [{tag}] {','.join(causes)}")
            print(f"     ذهب: {ctx_g!r}")
            print(f"     خرج: {out[max(0, j1 - 25) : j1]!r} ⟦{o[:40]!r}⟧ {out[j2 : j2 + 25]!r}")
    print(f"  إجمالي الفئات: {stats}")
    print()


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else "andalus"
    mode = sys.argv[2] if len(sys.argv) > 2 else "pf"
    show(slug, mode)
