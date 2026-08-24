"""بوابة إشارة الجليف — الحسم الحتمي مقابل الذهب (v2، كل الحالات).

لكل حالة في gold_manifest.json: يعيد فتح الـfixture، ويقارن لكل جليفٍ
مرسومٍ بين ما تبلغه طبقة النص (ToUnicode الفاسدة) وما يحسمه الخط المضمّن
نفسه (cmap + أسماء الجليفات عبر arafix.cmap.build_glyph_map).

البوابة الصارمة لكل حالة (خروج 1 عند خرق أيٍّ منها):
  * كل جليف مرسومٍ حقيقتُه حرفُ الحقيقة يتناقض = ضُبط.
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


def verify_case(manifest: dict, case: dict) -> bool:
    doc = fitz.open(ASSETS / case["pdf"])
    page = doc[0]
    font_xref = doc.get_page_fonts(0)[0][0]
    name, _ext, _t, data = doc.extract_font(font_xref)
    gm = build_glyph_map(data, name)

    reported: dict[int, set[str]] = {}
    for span in page.get_texttrace():
        if span.get("type") != 0:
            continue
        for uni, gid, _origin, _bbox in span["chars"]:
            reported.setdefault(gid, set()).add(chr(uni))

    true_ch = case["pair"]["true"]
    conflicts: set[int] = set()
    false_conflicts: list[tuple[int, str, str]] = []
    painted_truth: set[int] = set()
    for gid, chars in reported.items():
        truth = gm.lookup_id(gid)
        if truth is None or len(truth) != 1:
            continue
        if normalize(truth) == true_ch:
            painted_truth.add(gid)
        if any(normalize(ch) != normalize(truth) for ch in chars):
            if normalize(truth) == true_ch:
                conflicts.add(gid)
            else:
                false_conflicts.append((gid, "".join(sorted(chars)), truth))

    missed = painted_truth - conflicts
    ok = not false_conflicts and not missed
    print(f"[{case['key']}] {true_ch}->{case['pair']['lie']}: "
          f"painted_truth={len(painted_truth)} conflicts={len(conflicts)} "
          f"missed={len(missed)} false={len(false_conflicts)} "
          f"{'OK' if ok else 'FAIL'}")
    if not ok:
        for gid, chs, truth in false_conflicts[:3]:
            print(f"   FALSE gid={gid}: text={chs!r} vs font={truth!r}")
    return ok


def main() -> int:
    manifest = json.loads((ASSETS / "gold_manifest.json").read_text(encoding="utf-8"))
    print(f"schema={manifest['schema']} | cases={len(manifest['cases'])}\n")
    all_ok = True
    for case in manifest["cases"]:
        all_ok = verify_case(manifest, case) and all_ok

    print()
    if all_ok:
        print("PASS: كشف حتمي دقيق في كل الحالات — لا فوت ولا تناقض زائف")
        return 0
    print("FAIL: راجع الحالات أعلاه")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
