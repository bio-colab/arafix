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

  المصدر ٣: مطابقة الشكل (glyph-shape matching) — انظر `shape_match.py`
      إن سقط المصدران، نرسم الجليف ونقارنه بمرجع.

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

    m = _UNI_NAME.match(name)
    if m:
        hexes = [m.group(1)] + re.findall(r"[0-9A-Fa-f]{4}", m.group(2) or "")
        return "".join(chr(int(h, 16)) for h in hexes)

    m = _U_NAME.match(name)
    if m:
        return chr(int(m.group(1), 16))

    if _CID_NAME.match(name):
        return None  # لا معنى فيه — لا تخترع

    # الاسم رمزيّ (`alef`, `lam-ar`, `afii57415`): نسأل قوائم AGL القياسية.
    try:
        from fontTools.agl import toUnicode  # type: ignore
    except ImportError:
        return None
    try:
        value = toUnicode(name)
    except Exception:  # pragma: no cover - دفاعيّ
        return None
    return value or None


# ---------------------------------------------------------------------------
# عكس جدول cmap داخل الخط
# ---------------------------------------------------------------------------

def reverse_font_cmap(font_bytes: bytes) -> dict[str, str]:
    """
    يستخرج من خطٍّ مضمَّن خريطة: اسم الجليف ← النص اليونيكودي.

    يجمع بين المصدرين ١ و٢: يعكس جدول cmap أولاً (وهو الأوثق)، ثم
    يسدّ ثغراته بأسماء الجليفات.
    """
    try:
        from fontTools.ttLib import TTFont  # type: ignore
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
            # نفضّل الحرف الاسمي على شكله الرسومي إن تعارضا على جليف واحد.
            if gname in mapping and is_arabic(mapping[gname]):
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
    source: str = "unknown"
    coverage: float = 0.0
    notes: list[str] = field(default_factory=list)

    def lookup(self, glyph_name: str) -> str | None:
        return self.by_name.get(glyph_name)

    @property
    def confidence(self) -> float:
        """ثقة الخريطة = تغطيتها مضروبةً في وثاقة مصدرها."""
        weight = {"font_cmap": 1.0, "glyph_names": 0.85, "shape_match": 0.6}.get(
            self.source, 0.3
        )
        return round(self.coverage * weight, 3)


def build_glyph_map(font_bytes: bytes, font_name: str = "") -> GlyphMap:
    """
    يبني `GlyphMap` من بايتات خطٍّ مضمَّن، مع تقدير التغطية والمصدر.

    التغطية = نسبة الجليفات التي أمكن تفسيرها إلى مجموع الجليفات.
    نُصرّح بها لأن خريطةً تغطي ٤٠٪ ليست خريطةً يُبنى عليها قرار.
    """
    mapping = reverse_font_cmap(font_bytes)

    total = 0
    try:
        import io

        from fontTools.ttLib import TTFont  # type: ignore

        f = TTFont(io.BytesIO(font_bytes), fontNumber=0, lazy=True)
        total = len(f.getGlyphOrder())
        f.close()
    except Exception:
        total = len(mapping)

    coverage = len(mapping) / total if total else 0.0
    source = "font_cmap" if coverage > 0.5 else "glyph_names"

    gm = GlyphMap(font_name=font_name, by_name=mapping, source=source, coverage=round(coverage, 3))
    if coverage < 0.5:
        gm.notes.append(
            "تغطية منخفضة — الخط غالباً مرمَّز CID بأسماء بلا دلالة؛ "
            "الحلّ عندئذٍ مطابقة الشكل (shape_match) لا التخمين."
        )
    return gm
