"""
الدرجة ٣ — إعادة بناء الخريطة من الخط المضمَّن نفسه.

هذه أصعب الحالات وأندرها: ملفٌ يعرض العربية سليمةً على الشاشة، وحين
تستخرجه تحصل على رموز PUA أو خانات فارغة. السبب أن جدول
`ToUnicode` — وهو الجسر الوحيد بين رقم الجليف ومعناه — مفقود أو تالف.

المفتاح الذي يغفل عنه أكثر الناس: **الخط مضمَّنٌ في الملف**. وفي
الخط نفسه ثلاثة مصادر مستقلة للمعنى، نجرّبها بالترتيب:

  المصدر ١: جدول `cmap` داخل الخط
      يعيّن يونيكود ← جليف. نعكسه فنحصل على جليف ← يونيكود.
      كثيراً ما يكون سليماً حتى حين يتلف ToUnicode في الـ PDF.

  المصدر ٢: أسماء الجليفات (جدول `post` أو أسماء CFF)
      أسماء كـ `uni0645` أو `afii57411` أو `alefmaksura` تُفكّ مباشرة.
      يعرفها fontTools عبر قوائم AGL القياسية، أو محلّل OpenType الثنائي المدمج.

  المصدر ٣: عكس شجرة جدول `GSUB` داخل الخط
      يربط الأشكال السياقية (init/medi/fina) والرباطات (liga/rlig) بأصولها اليونيكودية حتمياً.

الترتيب مقصود: من اليقينيّ إلى الاحتماليّ، ولا ننزل درجةً إلا بعد
سقوط ما فوقها. وكل نتيجة تحمل ثقتها معها.

يتطلّب: مكتبة بايثون القياسية فقط (يدعم fontTools اختيارياً إن وُجد،
ويعمل بدونه عبر محلّل OpenType ثنائي مدمج).
"""

from __future__ import annotations

import contextlib
import re
import struct
from dataclasses import dataclass, field
from typing import Any

from .unicode_tables import PF_TO_BASE, is_arabic

__all__ = ["GlyphMap", "decode_glyph_name", "reverse_font_cmap", "build_glyph_map"]


# ---------------------------------------------------------------------------
# قوائم أسماء الجليفات القياسية المدمجة (Built-in AGL / Mac Standard Names)
# ---------------------------------------------------------------------------

_MAC_STANDARD_NAMES: tuple[str, ...] = (
    ".notdef", ".null", "nonmarkingreturn", "space", "exclam", "quotedbl", "numbersign",
    "dollar", "percent", "ampersand", "quotesingle", "parenleft", "parenright", "asterisk",
    "plus", "comma", "hyphen", "period", "slash", "zero", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine", "colon", "semicolon", "less", "equal", "greater",
    "question", "at", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N",
    "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "bracketleft", "backslash",
    "bracketright", "asciicircum", "underscore", "grave", "a", "b", "c", "d", "e", "f", "g",
    "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x",
    "y", "z", "braceleft", "bar", "braceright", "asciitilde",
)

_BUILTIN_AGL: dict[str, str] = {
    "space": " ", "exclam": "!", "quotedbl": '"', "numbersign": "#", "dollar": "$",
    "percent": "%", "ampersand": "&", "quotesingle": "'", "parenleft": "(", "parenright": ")",
    "asterisk": "*", "plus": "+", "comma": ",", "hyphen": "-", "period": ".", "slash": "/",
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "colon": ":", "semicolon": ";",
    "less": "<", "equal": "=", "greater": ">", "question": "?", "at": "@",
    "bracketleft": "[", "backslash": "\\", "bracketright": "]", "underscore": "_",
    "braceleft": "{", "bar": "|", "braceright": "}", "asciitilde": "~",
    # Adobe Glyph List / AFII Arabic mappings
    "afii57388": "،", "afii57403": "؛", "afii57407": "؟", "afii57409": "ء",
    "afii57410": "آ", "afii57411": "أ", "afii57412": "ؤ", "afii57413": "إ",
    "afii57414": "ئ", "afii57415": "ا", "afii57416": "ب", "afii57417": "ة",
    "afii57418": "ت", "afii57419": "ث", "afii57420": "ج", "afii57421": "ح",
    "afii57422": "خ", "afii57423": "د", "afii57424": "ذ", "afii57425": "ر",
    "afii57426": "ز", "afii57427": "س", "afii57428": "ش", "afii57429": "ص",
    "afii57430": "ض", "afii57431": "ط", "afii57432": "ظ", "afii57433": "ع",
    "afii57434": "غ", "afii57440": "ـ", "afii57441": "ف", "afii57442": "ق",
    "afii57443": "ك", "afii57444": "ل", "afii57445": "م", "afii57446": "ن",
    "afii57470": "ه", "afii57448": "و", "afii57449": "ى", "afii57450": "ي",
    "afii57451": "\u064b", "afii57452": "\u064c", "afii57453": "\u064d",
    "afii57454": "\u064e", "afii57455": "\u064f", "afii57456": "\u0650",
    "afii57457": "\u0651", "afii57458": "\u0652",
    "afii57392": "٠", "afii57393": "١", "afii57394": "٢", "afii57395": "٣",
    "afii57396": "٤", "afii57397": "٥", "afii57398": "٦", "afii57399": "٧",
    "afii57400": "٨", "afii57401": "٩",
    # Common descriptive Arabic glyph names
    "hamza": "ء", "alefmadda": "آ", "alefhamzaabove": "أ", "wawhamza": "ؤ",
    "alefhamzabelow": "إ", "yehhamza": "ئ", "alef": "ا", "beh": "ب",
    "tehmarbuta": "ة", "teh": "ت", "theh": "ث", "jeem": "ج", "hah": "ح",
    "khah": "خ", "dal": "د", "thal": "ذ", "reh": "ر", "zain": "ز",
    "seen": "س", "sheen": "ش", "sad": "ص", "dad": "ض", "tah": "ط",
    "zah": "ظ", "ain": "ع", "ghain": "غ", "tatweel": "ـ", "kashida": "ـ",
    "feh": "ف", "qaf": "ق", "kaf": "ك", "lam": "ل", "meem": "م",
    "noon": "ن", "heh": "ه", "waw": "و", "alefmaksura": "ى", "yeh": "ي",
    "lamalef": "لا", "lam_alef": "لا",
    **{c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"},
}


# ---------------------------------------------------------------------------
# فكّ أسماء الجليفات
# ---------------------------------------------------------------------------

_UNI_NAME = re.compile(r"^uni([0-9A-Fa-f]{4})((?:[0-9A-Fa-f]{4})*)$")
_U_NAME = re.compile(r"^u([0-9A-Fa-f]{4,6})$")
_CID_NAME = re.compile(r"^(?:cid|g|glyph|index)(\d+)$", re.IGNORECASE)


def _safe_cp(value: int) -> str | None:
    """يرفض النقاط المستحيلة قبل تحويلها إلى محرف."""
    if 0xD800 <= value <= 0xDFFF or value > 0x10FFFF:
        return None
    return chr(value)


def decode_glyph_name(name: str) -> str | None:
    """
    يحاول فكّ اسم جليف إلى نصّه اليونيكودي. يُرجع None إن عجز.

    >>> decode_glyph_name("uni0645")
    'م'
    >>> decode_glyph_name("uni06450631")
    'مر'
    >>> decode_glyph_name("u0631")
    'ر'
    >>> decode_glyph_name("cid1234") is None
    True
    """
    if not name:
        return None

    stem = name.split(".", 1)[0]

    m = _UNI_NAME.match(stem)
    if m:
        hexes = [m.group(1)] + re.findall(r"[0-9A-Fa-f]{4}", m.group(2) or "")
        chars = [c for h in hexes if (c := _safe_cp(int(h, 16)))]
        return "".join(chars) or None

    m = _U_NAME.match(stem)
    if m:
        return _safe_cp(int(m.group(1), 16))

    if _CID_NAME.match(stem):
        return None  # لا معنى فيه — لا تخترع

    # استعلام AGL القياسي إن توفّر fontTools، وإلا الجدول المدمج
    try:
        from fontTools.agl import toUnicode

        val = toUnicode(stem)
        if val:
            return val
    except Exception:
        pass

    norm_stem = stem.lower().removesuffix("-ar").removesuffix("_ar")
    return _BUILTIN_AGL.get(stem) or _BUILTIN_AGL.get(norm_stem)


# ---------------------------------------------------------------------------
# محلّل OpenType/TrueType الثنائي المدمج (Zero-Dependency Binary SFNT Parser)
# ---------------------------------------------------------------------------

def _parse_sfnt_tables(data: bytes) -> dict[str, bytes]:
    if len(data) < 12:
        return {}
    # دعم TTC (TrueType Collection) بأخذ الخط الأول
    if data[:4] == b"ttcf":
        if len(data) < 16:
            return {}
        first_offset = struct.unpack(">I", data[12:16])[0]
        data_hdr = data[first_offset:]
    else:
        data_hdr = data
    if len(data_hdr) < 12:
        return {}
    num_tables = struct.unpack(">H", data_hdr[4:6])[0]
    tables: dict[str, bytes] = {}
    pos = 12
    for _ in range(num_tables):
        if pos + 16 > len(data_hdr):
            break
        tag = data_hdr[pos : pos + 4].decode("latin1", errors="ignore")
        offset, length = struct.unpack(">II", data_hdr[pos + 8 : pos + 16])
        if offset + length <= len(data):
            tables[tag] = data[offset : offset + length]
        pos += 16
    return tables


def _parse_num_glyphs(maxp: bytes) -> int:
    if len(maxp) >= 6:
        return struct.unpack(">H", maxp[4:6])[0]
    return 0


def _parse_post_names(post: bytes, num_glyphs: int) -> list[str]:
    default_order = [f"glyph{i:05d}" for i in range(num_glyphs)]
    if default_order:
        default_order[0] = ".notdef"
    if len(post) < 32:
        return default_order
    version = struct.unpack(">I", post[:4])[0]
    if version == 0x00010000:
        return [
            _MAC_STANDARD_NAMES[i] if i < len(_MAC_STANDARD_NAMES) else f"glyph{i:05d}"
            for i in range(num_glyphs)
        ]
    if version != 0x00020000 or len(post) < 34:
        return default_order
    n = struct.unpack(">H", post[32:34])[0]
    pos = 34
    indices: list[int] = []
    for _ in range(n):
        if pos + 2 > len(post):
            break
        indices.append(struct.unpack(">H", post[pos : pos + 2])[0])
        pos += 2
    extra_names: list[str] = []
    while pos < len(post):
        ln = post[pos]
        pos += 1
        if pos + ln > len(post):
            break
        extra_names.append(post[pos : pos + ln].decode("latin1", errors="ignore"))
        pos += ln
    names: list[str] = []
    for idx in indices:
        if idx < 258:
            names.append(
                _MAC_STANDARD_NAMES[idx] if idx < len(_MAC_STANDARD_NAMES) else f"glyph{idx:05d}"
            )
        else:
            ext_idx = idx - 258
            names.append(
                extra_names[ext_idx] if ext_idx < len(extra_names) else f"glyph{idx:05d}"
            )
    while len(names) < num_glyphs:
        names.append(f"glyph{len(names):05d}")
    return names[:num_glyphs] if num_glyphs else names


def _parse_cmap_subtable(sub: bytes) -> dict[int, int]:
    if len(sub) < 4:
        return {}
    fmt = struct.unpack(">H", sub[:2])[0]
    res: dict[int, int] = {}
    if fmt == 4 and len(sub) >= 14:
        seg_count_x2 = struct.unpack(">H", sub[6:8])[0]
        seg_count = seg_count_x2 // 2
        pos = 14
        if pos + seg_count * 8 + 2 > len(sub):
            return {}
        end_codes = struct.unpack(f">{seg_count}H", sub[pos : pos + seg_count * 2])
        pos += seg_count * 2 + 2
        start_codes = struct.unpack(f">{seg_count}H", sub[pos : pos + seg_count * 2])
        pos += seg_count * 2
        id_deltas = struct.unpack(f">{seg_count}h", sub[pos : pos + seg_count * 2])
        pos += seg_count * 2
        id_range_offset_pos = pos
        id_range_offsets = struct.unpack(f">{seg_count}H", sub[pos : pos + seg_count * 2])
        for i in range(seg_count):
            start, end, delta, ro = (
                start_codes[i],
                end_codes[i],
                id_deltas[i],
                id_range_offsets[i],
            )
            if start == 0xFFFF and end == 0xFFFF:
                continue
            for cp in range(start, end + 1):
                if ro == 0:
                    gid = (cp + delta) & 0xFFFF
                else:
                    roff = id_range_offset_pos + i * 2 + ro + (cp - start) * 2
                    if roff + 2 > len(sub):
                        continue
                    gid = struct.unpack(">H", sub[roff : roff + 2])[0]
                    if gid != 0:
                        gid = (gid + delta) & 0xFFFF
                if gid != 0:
                    res[cp] = gid
    elif fmt == 12 and len(sub) >= 16:
        num_groups = struct.unpack(">I", sub[12:16])[0]
        pos = 16
        for _ in range(num_groups):
            if pos + 12 > len(sub):
                break
            start_cp, end_cp, start_gid = struct.unpack(">III", sub[pos : pos + 12])
            pos += 12
            if end_cp - start_cp > 0x10000:
                continue
            for cp in range(start_cp, end_cp + 1):
                gid = start_gid + (cp - start_cp)
                if gid != 0:
                    res[cp] = gid
    elif fmt == 6 and len(sub) >= 10:
        first_code, entry_count = struct.unpack(">HH", sub[6:10])
        pos = 10
        for i in range(entry_count):
            if pos + 2 > len(sub):
                break
            gid = struct.unpack(">H", sub[pos : pos + 2])[0]
            pos += 2
            if gid != 0:
                res[first_code + i] = gid
    return res


def _parse_best_cmap(cmap: bytes) -> dict[int, int]:
    if len(cmap) < 4:
        return {}
    num_tables = struct.unpack(">H", cmap[2:4])[0]
    pos = 4
    best: dict[int, int] = {}
    for _ in range(num_tables):
        if pos + 8 > len(cmap):
            break
        _pid, _eid, offset = struct.unpack(">HHI", cmap[pos : pos + 8])
        pos += 8
        if offset < len(cmap):
            sub = _parse_cmap_subtable(cmap[offset:])
            if len(sub) > len(best):
                best = sub
    return best


def _parse_coverage(data: bytes, offset: int) -> list[int]:
    if offset + 4 > len(data):
        return []
    fmt = struct.unpack(">H", data[offset : offset + 2])[0]
    if fmt == 1:
        cnt = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        if offset + 4 + cnt * 2 > len(data):
            return []
        return list(struct.unpack(f">{cnt}H", data[offset + 4 : offset + 4 + cnt * 2]))
    if fmt == 2:
        rcnt = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        pos = offset + 4
        glyphs: list[int] = []
        for _ in range(rcnt):
            if pos + 6 > len(data):
                break
            start_g, end_g, _start_cov = struct.unpack(">HHH", data[pos : pos + 6])
            pos += 6
            if end_g >= start_g:
                glyphs.extend(range(start_g, end_g + 1))
        return glyphs
    return []


def _parse_gsub_subtable(
    gsub: bytes,
    st_off: int,
    l_type: int,
) -> tuple[
    list[tuple[int, int]],
    list[tuple[int, list[int]]],
    list[tuple[int, list[int]]],
]:
    single_rules: list[tuple[int, int]] = []
    multi_rules: list[tuple[int, list[int]]] = []
    lig_rules: list[tuple[int, list[int]]] = []
    if st_off + 4 > len(gsub):
        return single_rules, multi_rules, lig_rules

    if l_type == 7:
        if st_off + 8 > len(gsub):
            return single_rules, multi_rules, lig_rules
        _fmt, ext_type, ext_rel = struct.unpack(">HHI", gsub[st_off : st_off + 8])
        return _parse_gsub_subtable(gsub, st_off + ext_rel, ext_type)

    if l_type == 1:
        fmt, cov_rel = struct.unpack(">HH", gsub[st_off : st_off + 4])
        cov = _parse_coverage(gsub, st_off + cov_rel)
        if fmt == 1 and st_off + 6 <= len(gsub):
            delta = struct.unpack(">h", gsub[st_off + 4 : st_off + 6])[0]
            for g in cov:
                single_rules.append((g, (g + delta) & 0xFFFF))
        elif fmt == 2 and st_off + 6 <= len(gsub):
            gcnt = struct.unpack(">H", gsub[st_off + 4 : st_off + 6])[0]
            if st_off + 6 + gcnt * 2 <= len(gsub):
                subs = struct.unpack(f">{gcnt}H", gsub[st_off + 6 : st_off + 6 + gcnt * 2])
                for g, s in zip(cov, subs):
                    single_rules.append((g, s))

    elif l_type == 2 and st_off + 6 <= len(gsub):
        fmt, cov_rel, seq_cnt = struct.unpack(">HHH", gsub[st_off : st_off + 6])
        if fmt == 1 and st_off + 6 + seq_cnt * 2 <= len(gsub):
            cov = _parse_coverage(gsub, st_off + cov_rel)
            seq_offs = struct.unpack(f">{seq_cnt}H", gsub[st_off + 6 : st_off + 6 + seq_cnt * 2])
            for g, so in zip(cov, seq_offs):
                s_abs = st_off + so
                if s_abs + 2 > len(gsub):
                    continue
                gc = struct.unpack(">H", gsub[s_abs : s_abs + 2])[0]
                if s_abs + 2 + gc * 2 <= len(gsub):
                    comps = list(struct.unpack(f">{gc}H", gsub[s_abs + 2 : s_abs + 2 + gc * 2]))
                    multi_rules.append((g, comps))

    elif l_type == 4 and st_off + 6 <= len(gsub):
        fmt, cov_rel, set_cnt = struct.unpack(">HHH", gsub[st_off : st_off + 6])
        if fmt == 1 and st_off + 6 + set_cnt * 2 <= len(gsub):
            cov = _parse_coverage(gsub, st_off + cov_rel)
            set_offs = struct.unpack(f">{set_cnt}H", gsub[st_off + 6 : st_off + 6 + set_cnt * 2])
            for first_g, set_rel in zip(cov, set_offs):
                ls_abs = st_off + set_rel
                if ls_abs + 2 > len(gsub):
                    continue
                lig_cnt = struct.unpack(">H", gsub[ls_abs : ls_abs + 2])[0]
                if ls_abs + 2 + lig_cnt * 2 > len(gsub):
                    continue
                lig_offs = struct.unpack(
                    f">{lig_cnt}H", gsub[ls_abs + 2 : ls_abs + 2 + lig_cnt * 2]
                )
                for lo in lig_offs:
                    l_abs = ls_abs + lo
                    if l_abs + 4 > len(gsub):
                        continue
                    lig_glyph, comp_cnt = struct.unpack(">HH", gsub[l_abs : l_abs + 4])
                    if comp_cnt >= 1 and l_abs + 4 + (comp_cnt - 1) * 2 <= len(gsub):
                        rest = list(
                            struct.unpack(
                                f">{comp_cnt - 1}H",
                                gsub[l_abs + 4 : l_abs + 4 + (comp_cnt - 1) * 2],
                            )
                        )
                        lig_rules.append((lig_glyph, [first_g] + rest))

    return single_rules, multi_rules, lig_rules


def _propagate_binary_gsub(
    gsub: bytes,
    glyph_order: list[str],
    mapping: dict[str, str],
) -> tuple[dict[str, str], int]:
    if len(gsub) < 10:
        return mapping, 0
    lookup_list_off = struct.unpack(">H", gsub[8:10])[0]
    if lookup_list_off + 2 > len(gsub):
        return mapping, 0
    lookup_cnt = struct.unpack(">H", gsub[lookup_list_off : lookup_list_off + 2])[0]
    if lookup_list_off + 2 + lookup_cnt * 2 > len(gsub):
        return mapping, 0
    lookup_offs = struct.unpack(
        f">{lookup_cnt}H", gsub[lookup_list_off + 2 : lookup_list_off + 2 + lookup_cnt * 2]
    )

    all_single: list[tuple[str, str]] = []
    all_multi: list[tuple[str, list[str]]] = []
    all_lig: list[tuple[str, list[str]]] = []

    def gname(gid: int) -> str | None:
        return glyph_order[gid] if 0 <= gid < len(glyph_order) else None

    for lo in lookup_offs:
        l_abs = lookup_list_off + lo
        if l_abs + 6 > len(gsub):
            continue
        l_type, _l_flag, sub_cnt = struct.unpack(">HHH", gsub[l_abs : l_abs + 6])
        if l_abs + 6 + sub_cnt * 2 > len(gsub):
            continue
        sub_offs = struct.unpack(f">{sub_cnt}H", gsub[l_abs + 6 : l_abs + 6 + sub_cnt * 2])
        for so in sub_offs:
            s_rules, m_rules, l_rules = _parse_gsub_subtable(gsub, l_abs + so, l_type)
            for a, b in s_rules:
                na, nb = gname(a), gname(b)
                if na and nb:
                    all_single.append((na, nb))
            for a, comps in m_rules:
                na = gname(a)
                ncomps = [gname(c) for c in comps]
                if na and all(ncomps):
                    all_multi.append((na, [c for c in ncomps if c]))
            for lig_g, comps in l_rules:
                nlig = gname(lig_g)
                ncomps = [gname(c) for c in comps]
                if nlig and all(ncomps):
                    all_lig.append((nlig, [c for c in ncomps if c]))

    out_map = dict(mapping)
    total_added = 0
    for _ in range(8):
        new_added = 0
        for inp, out in all_single:
            if inp in out_map and out not in out_map:
                out_map[out] = out_map[inp]
                new_added += 1
            elif out in out_map and inp not in out_map:
                out_map[inp] = out_map[out]
                new_added += 1
        for lig_glyph, all_comp in all_lig:
            if lig_glyph not in out_map and all(c in out_map for c in all_comp):
                out_map[lig_glyph] = "".join(out_map[c] for c in all_comp)
                new_added += 1
        for inp, components in all_multi:
            if inp not in out_map and all(c in out_map for c in components):
                out_map[inp] = "".join(out_map[c] for c in components)
                new_added += 1
        total_added += new_added
        if new_added == 0:
            break
    return out_map, total_added


def _extract_opentype_without_fonttools(
    font_bytes: bytes,
) -> tuple[dict[str, str], list[str], int]:
    """يحلّل بايتات الخط مباشرةً عبر struct دون الحاجة إلى fontTools."""
    tables = _parse_sfnt_tables(font_bytes)
    if not tables:
        raise ValueError("ليست بايتات خط TrueType/OpenType صالحة")
    num_glyphs = _parse_num_glyphs(tables.get("maxp", b""))
    glyph_order = _parse_post_names(tables.get("post", b""), num_glyphs)
    best_cmap = _parse_best_cmap(tables.get("cmap", b""))

    mapping: dict[str, str] = {}
    for cp, gid in best_cmap.items():
        gname = (
            glyph_order[gid]
            if 0 <= gid < len(glyph_order)
            else f"glyph{gid:05d}"
        )
        ch = _safe_cp(cp)
        if not ch:
            continue
        existing = mapping.get(gname)
        if existing is not None and len(existing) == 1 and is_arabic(existing):
            continue
        mapping[gname] = PF_TO_BASE.get(ch, ch)

    for gname in glyph_order:
        if gname in mapping:
            continue
        decoded = decode_glyph_name(gname)
        if decoded:
            mapping[gname] = "".join(PF_TO_BASE.get(c, c) for c in decoded)

    gsub_added = 0
    if "GSUB" in tables:
        mapping, gsub_added = _propagate_binary_gsub(
            tables["GSUB"], glyph_order, mapping
        )

    return mapping, glyph_order, gsub_added


# ---------------------------------------------------------------------------
# عكس جدول cmap وشجرة GSUB داخل الخط (عبر fontTools أو المحلّل المدمج)
# ---------------------------------------------------------------------------

def _propagate_gsub_mappings(font: Any, mapping: dict[str, str]) -> tuple[dict[str, str], int]:
    """
    ينشر المعنى اليونيكودي عبر شجرة جدول GSUB (Glyph Substitution).
    """
    try:
        gsub = font.get("GSUB")
        if not gsub or not hasattr(gsub, "table") or not gsub.table:
            return mapping, 0
        table = gsub.table
        if not hasattr(table, "LookupList") or not table.LookupList:
            return mapping, 0
        lookups = getattr(table.LookupList, "Lookup", None) or []
    except Exception:
        return mapping, 0

    out_map = dict(mapping)
    total_added = 0

    for _ in range(8):
        new_added = 0
        for lookup in lookups:
            l_type = getattr(lookup, "LookupType", None)
            subtables = getattr(lookup, "SubTable", None) or []
            for st in subtables:
                real_st = getattr(st, "ExtSubTable", st)
                st_type = getattr(real_st, "LookupType", l_type)

                if st_type == 1 and hasattr(real_st, "mapping"):
                    for inp, out in real_st.mapping.items():
                        if inp in out_map and out not in out_map:
                            out_map[out] = out_map[inp]
                            new_added += 1
                        elif out in out_map and inp not in out_map:
                            out_map[inp] = out_map[out]
                            new_added += 1

                elif st_type == 4 and hasattr(real_st, "ligatures"):
                    for first, lig_list in real_st.ligatures.items():
                        for lig in lig_list:
                            all_comp = [first] + list(getattr(lig, "Component", []))
                            lig_glyph = getattr(lig, "LigGlyph", None)
                            if (
                                lig_glyph
                                and lig_glyph not in out_map
                                and all(c in out_map for c in all_comp)
                            ):
                                out_map[lig_glyph] = "".join(out_map[c] for c in all_comp)
                                new_added += 1

                elif st_type == 2 and hasattr(real_st, "mapping"):
                    for inp, components in real_st.mapping.items():
                        if inp not in out_map and all(c in out_map for c in components):
                            out_map[inp] = "".join(out_map[c] for c in components)
                            new_added += 1

        total_added += new_added
        if new_added == 0:
            break

    return out_map, total_added


def reverse_font_cmap(font_bytes: bytes) -> dict[str, str]:
    """
    يستخرج من خطٍّ مضمَّن خريطة: اسم الجليف ← النص اليونيكودي.

    يجمع بين ثلاثة مصادر مرتبة:
      ١. جدول cmap داخل الخط (الأوثق).
      ٢. أسماء الجليفات القياسية لسدّ الثغرات (AGL).
      ٣. عكس شجرة جدول GSUB لربط الأشكال السياقية والرباطات حتمياً.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        ot_mapping, _, _ = _extract_opentype_without_fonttools(font_bytes)
        return ot_mapping

    import io

    mapping: dict[str, str] = {}
    font = TTFont(io.BytesIO(font_bytes), fontNumber=0, lazy=True)

    try:
        best = font.getBestCmap()
        for cp, gname in best.items():
            ch = chr(cp)
            existing = mapping.get(gname)
            if existing is not None and len(existing) == 1 and is_arabic(existing):
                continue
            mapping[gname] = PF_TO_BASE.get(ch, ch)
    except Exception:
        pass

    with contextlib.suppress(Exception):
        for gname in font.getGlyphOrder():
            if gname in mapping:
                continue
            decoded = decode_glyph_name(gname)
            if decoded:
                mapping[gname] = "".join(PF_TO_BASE.get(c, c) for c in decoded)

    with contextlib.suppress(Exception):
        mapping, _ = _propagate_gsub_mappings(font, mapping)

    font.close()
    return mapping


# ---------------------------------------------------------------------------
# نموذج الخريطة
# ---------------------------------------------------------------------------

@dataclass
class GlyphMap:
    """خريطة جليفات خطٍّ واحد، ومعها مصدرُ كل مدخلة وثقتُها."""

    font_name: str
    by_name: dict[str, str] = field(default_factory=dict)
    #: رقم glyph داخل الخط ← Unicode.
    by_id: dict[int, str] = field(default_factory=dict)
    source: str = "unknown"
    coverage: float = 0.0
    notes: list[str] = field(default_factory=list)

    def lookup(self, glyph_name: str) -> str | None:
        return self.by_name.get(glyph_name)

    def lookup_id(self, glyph_id: int) -> str | None:
        return self.by_id.get(glyph_id)

    @property
    def confidence(self) -> float:
        """ثقة الخريطة = تغطيتها مضروبةً في وثاقة مصدرها."""
        weight = {"font_cmap": 1.0, "gsub": 1.0, "glyph_names": 0.85, "shape_match": 0.6}.get(
            self.source, 0.3
        )
        return round(self.coverage * weight, 3)


def build_glyph_map(font_bytes: bytes, font_name: str = "") -> GlyphMap:
    """
    يبني `GlyphMap` من بايتات خطٍّ مضمَّن، مع تقدير التغطية والمصدر.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        ot_mapping, ot_order, ot_gsub = _extract_opentype_without_fonttools(font_bytes)
        ot_total = len(ot_order) if ot_order else len(ot_mapping)
        ot_by_id = {
            gid: ot_mapping[gname]
            for gid, gname in enumerate(ot_order)
            if gname in ot_mapping
        }
        ot_cov = len(ot_mapping) / ot_total if ot_total else 0.0
        if ot_gsub > 0:
            ot_source = "gsub"
        elif ot_cov > 0.5:
            ot_source = "font_cmap"
        else:
            ot_source = "glyph_names"
        gm = GlyphMap(
            font_name=font_name,
            by_name=ot_mapping,
            by_id=ot_by_id,
            source=ot_source,
            coverage=round(ot_cov, 3),
        )
        if ot_gsub > 0:
            gm.notes.append(
                f"أُضيف {ot_gsub} جليفاً سياقياً ورباطاً عبر عكس شجرة GSUB"
            )
        if ot_cov < 0.5:
            gm.notes.append(
                "تغطية منخفضة — الخط غالباً مرمَّز CID بأسماء بلا دلالة قياسية."
            )
        return gm

    import io

    font = TTFont(io.BytesIO(font_bytes), fontNumber=0, lazy=True)
    mapping: dict[str, str] = {}
    try:
        best = font.getBestCmap()
        for cp, gname in best.items():
            ch = chr(cp)
            existing = mapping.get(gname)
            if existing is not None and len(existing) == 1 and is_arabic(existing):
                continue
            mapping[gname] = PF_TO_BASE.get(ch, ch)
    except Exception:
        pass

    with contextlib.suppress(Exception):
        for gname in font.getGlyphOrder():
            if gname in mapping:
                continue
            decoded = decode_glyph_name(gname)
            if decoded:
                mapping[gname] = "".join(PF_TO_BASE.get(c, c) for c in decoded)

    gsub_added = 0
    with contextlib.suppress(Exception):
        mapping, gsub_added = _propagate_gsub_mappings(font, mapping)

    try:
        total = len(font.getGlyphOrder())
    except Exception:
        total = len(mapping)

    by_id: dict[int, str] = {}
    try:
        by_id = {
            glyph_id: mapping[glyph_name]
            for glyph_id, glyph_name in enumerate(font.getGlyphOrder())
            if glyph_name in mapping
        }
    except Exception:
        by_id = {}

    font.close()

    coverage = len(mapping) / total if total else 0.0
    if gsub_added > 0:
        source = "gsub"
    elif coverage > 0.5:
        source = "font_cmap"
    else:
        source = "glyph_names"

    gm = GlyphMap(
        font_name=font_name,
        by_name=mapping,
        by_id=by_id,
        source=source,
        coverage=round(coverage, 3),
    )
    if gsub_added > 0:
        gm.notes.append(
            f"أُضيف {gsub_added} جليفاً سياقياً ورباطاً عبر عكس شجرة GSUB"
        )
    if coverage < 0.5:
        gm.notes.append(
            "تغطية منخفضة — الخط غالباً مرمَّز CID بأسماء بلا دلالة قياسية."
        )
    return gm
