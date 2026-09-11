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
      يعرفها fontTools عبر قوائم AGL القياسية.

الترتيب مقصود: من اليقينيّ إلى الاحتماليّ، ولا ننزل درجةً إلا بعد
سقوط ما فوقها. وكل نتيجة تحمل ثقتها معها.

يتطلّب: fontTools (اختياري)، PyMuPDF (اختياري).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .unicode_tables import PF_TO_BASE, is_arabic

__all__ = ["GlyphMap", "decode_glyph_name", "reverse_font_cmap", "build_glyph_map"]


# ---------------------------------------------------------------------------
# فكّ أسماء الجليفات
# ---------------------------------------------------------------------------

_UNI_NAME = re.compile(r"^uni([0-9A-Fa-f]{4})((?:[0-9A-Fa-f]{4})*)$")
_U_NAME = re.compile(r"^u([0-9A-Fa-f]{4,6})$")
_CID_NAME = re.compile(r"^(?:cid|g|glyph|index)(\d+)$", re.IGNORECASE)


def _safe_cp(value: int) -> str | None:
    """يرفض النقاط المستحيلة قبل تحويلها إلى محرف.

    البدائل المعزولة (U+D800–U+DFFF) وما بعد سقف يونيكود (U+10FFFF) تكسر
    ترميز UTF-8 لاحقاً (`UnicodeEncodeError: surrogates not allowed`) —
    نرجع None فتُسقَط المدخلة بدل أن تُخرِّب المخرَج كله.
    """
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

    ملاحظة: أسماء `cidNNN` و`gNNN` **بلا معنى دلالي** عمداً — هي أرقام
    داخلية للخط لا أكثر. من يفكّها إلى محارف يخترع من عنده.
    """
    if not name:
        return None

    # OpenType stores positional variants as ``uni0645.init`` / ``u0631.fina``.
    # The suffix describes shaping, not Unicode identity; stripping only the
    # dotted suffix preserves the explicit codepoint evidence in the stem.
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

    # الاسم رمزيّ (`alef`, `lam-ar`, `afii57415`): نسأل قوائم AGL القياسية.
    try:
        from fontTools.agl import toUnicode
    except ImportError:
        return None
    try:
        value = toUnicode(stem)
    except Exception:  # pragma: no cover - دفاعيّ
        return None
    return value or None


# ---------------------------------------------------------------------------
# عكس جدول cmap وشجرة GSUB داخل الخط
# ---------------------------------------------------------------------------

def _propagate_gsub_mappings(font: any, mapping: dict[str, str]) -> tuple[dict[str, str], int]:
    """
    ينشر المعنى اليونيكودي عبر شجرة جدول GSUB (Glyph Substitution).

    في الخطوط العربية، يربط GSUB الحرف الاسمي بأشكاله السياقية (init, medi, fina)
    ورباطاته المركبة (liga, rlig). إذا عُرف أي طرف، يُستنتج الطرف الآخر حتمياً:
      - الاستبدال المفرد (LookupType 1): A <-> B
      - استبدال الرباطات (LookupType 4): [A, B] -> AB
      - الاستبدال المتعدد (LookupType 2): [A, B] <- AB
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

    # تكرار الانتشار حتى ثبات الخريطة (Fixed-Point Convergence)
    for _ in range(8):
        new_added = 0
        for lookup in lookups:
            l_type = getattr(lookup, "LookupType", None)
            subtables = getattr(lookup, "SubTable", None) or []
            for st in subtables:
                # دعم ExtensionSubst (Type 7) حيث توجد الجداول الحقيقية في ExtSubTable
                real_st = getattr(st, "ExtSubTable", st)
                st_type = getattr(real_st, "LookupType", l_type)

                # 1. الاستبدال المفرد (Single Substitution)
                if st_type == 1 and hasattr(real_st, "mapping"):
                    for inp, out in real_st.mapping.items():
                        if inp in out_map and out not in out_map:
                            out_map[out] = out_map[inp]
                            new_added += 1
                        elif out in out_map and inp not in out_map:
                            out_map[inp] = out_map[out]
                            new_added += 1

                # 2. استبدال الرباطات (Ligature Substitution)
                elif st_type == 4 and hasattr(real_st, "ligatures"):
                    for first, lig_list in real_st.ligatures.items():
                        for lig in lig_list:
                            all_comp = [first] + list(getattr(lig, "Component", []))
                            lig_glyph = getattr(lig, "LigGlyph", None)
                            if lig_glyph and lig_glyph not in out_map:
                                if all(c in out_map for c in all_comp):
                                    out_map[lig_glyph] = "".join(out_map[c] for c in all_comp)
                                    new_added += 1

                # 3. الاستبدال المتعدد (Multiple Substitution)
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
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("الدرجة ٣ تتطلّب fontTools: pip install arafix[cmap]") from exc

    import io

    mapping: dict[str, str] = {}
    font = TTFont(io.BytesIO(font_bytes), fontNumber=0, lazy=True)

    # --- المصدر ١: جدول cmap معكوساً -------------------------------------
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

    # --- المصدر ٢: أسماء الجليفات لسدّ الثغرات ---------------------------
    try:
        for gname in font.getGlyphOrder():
            if gname in mapping:
                continue
            decoded = decode_glyph_name(gname)
            if decoded:
                mapping[gname] = "".join(PF_TO_BASE.get(c, c) for c in decoded)
    except Exception:
        pass

    # --- المصدر ٣: عكس شجرة جدول GSUB لربط الأشكال السياقية والرباطات -----
    try:
        mapping, _ = _propagate_gsub_mappings(font, mapping)
    except Exception:
        pass

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
    #: رقم glyph داخل الخط ← Unicode. PyMuPDF يوفّر هذا الرقم في texttrace
    #: حتى عندما تكون ToUnicode تالفة ولا يوفّر اسم glyph.
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

    التغطية = نسبة الجليفات التي أمكن تفسيرها إلى مجموع الجليفات.
    نُصرّح بها لأن خريطةً تغطي ٤٠٪ ليست خريطةً يُبنى عليها قرار.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise RuntimeError("الدرجة ٣ تتطلّب fontTools: pip install arafix[cmap]") from exc

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

    try:
        for gname in font.getGlyphOrder():
            if gname in mapping:
                continue
            decoded = decode_glyph_name(gname)
            if decoded:
                mapping[gname] = "".join(PF_TO_BASE.get(c, c) for c in decoded)
    except Exception:
        pass

    base_count = len(mapping)
    gsub_added = 0
    try:
        mapping, gsub_added = _propagate_gsub_mappings(font, mapping)
    except Exception:
        pass

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
