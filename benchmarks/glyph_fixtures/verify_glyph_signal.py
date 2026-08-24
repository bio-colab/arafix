"""بوابة إشارة الجليف — الحسم الحتمي مقابل الذهب.

يعيد فتح الـfixture المولَّد، ويقارن لكل جليفٍ مرسومٍ بين ما تبلغه طبقة
النص (ToUnicode الفاسدة) وما يحسمه الخط المضمّن نفسه (cmap + أسماء
الجليفات عبر arafix.cmap.build_glyph_map).

البوابة الصارمة (خروج 1 عند خرقها):
  * كل التناقضات = بالضبط cids الذهب (لا زائفة، لا فائتة).
  * صفر تناقض على أي جليف غير مفسود.

    python benchmarks/glyph_fixtures/verify_glyph_signal.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import fitz  # noqa: E402

from arafix.cmap import build_glyph_map  # noqa: E402
from arafix.unicode_tables import PF_TO_BASE  # noqa: E402

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


def normalize(ch: str) -> str:
    return PF_TO_BASE.get(ch, ch)


def main() -> int:
    manifest = json.loads((ASSETS / "gold_manifest.json").read_text(encoding="utf-8"))
    pdf_path = ASSETS / f"glyph_{manifest['pair']['true']}_to_{manifest['pair']['lie']}.pdf"

    doc = fitz.open(pdf_path)
    page = doc[0]
    font_xref = doc.get_page_fonts(0)[0][0]
    name, _ext, _t, data = doc.extract_font(font_xref)
    gm = build_glyph_map(data, name)
    print(f"GlyphMap: source={gm.source} coverage={gm.coverage} "
          f"by_id={len(gm.by_id)}")

    reported: dict[int, set[str]] = {}
    for span in page.get_texttrace():
        if span.get("type") != 0:
            continue
        for uni, gid, _origin, _bbox in span["chars"]:
            reported.setdefault(gid, set()).add(chr(uni))

    conflicts: dict[int, tuple[str, str]] = {}
    false_conflicts: dict[int, tuple[str, str]] = {}
    for gid, chars in sorted(reported.items()):
        truth = gm.lookup_id(gid)
        if truth is None or len(truth) != 1:
            continue
        for ch in chars:
            if normalize(ch) == normalize(truth):
                continue
            gold_truth = manifest["corrupted_cids"].get(str(gid))
            if gold_truth is not None and normalize(truth) == manifest["pair"]["true"]:
                conflicts[gid] = (ch, truth)
            else:
                false_conflicts[gid] = (ch, truth)

    print(f"conflicts (مطابقة للذهب)   : {len(conflicts)}")
    print(f"false conflicts (خارج الذهب): {len(false_conflicts)}")
    for gid, (ch, truth) in list(conflicts.items())[:4]:
        print(f"  gid={gid}: text={ch!r} vs font={truth!r}")
    if false_conflicts:
        for gid, (ch, truth) in list(false_conflicts.items())[:4]:
            print(f"  FALSE gid={gid}: text={ch!r} vs font={truth!r}")

    gold_cids = {int(cid) for cid in manifest["corrupted_cids"]}
    # الحكم على المرسوم فقط: cids ذهبية لم ترسمها هذه الوثيقة لا يمكن أن
    # تتناقض — تكفي مطابقة كل جليف مرسومٍ حقيقته «ه» مع التناقضات.
    painted_gold = {
        gid for gid in reported
        if gid in gold_cids or (
            (truth := gm.lookup_id(gid)) is not None
            and len(truth) == 1 and normalize(truth) == manifest["pair"]["true"]
        )
    }
    missed_gold = painted_gold - set(conflicts)

    print(f"painted gold gids: {sorted(painted_gold)} "
          f"(of {len(gold_cids)} corrupted cids in ToUnicode)")
    if false_conflicts or missed_gold:
        if missed_gold:
            print(f"missed gold (مرسوم بلا تناقض): {sorted(missed_gold)}")
        print("FAIL: الإشارة ليست حتمية — راجع أعلاه")
        return 1
    print("PASS: كشف حتمي دقيق — كل الذهب المرسوم ضُبط ولا تناقضَ خارجَه")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
