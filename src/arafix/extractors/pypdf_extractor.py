"""
محرّك pypdf الهندسي — استخراج بإحداثيات الجليفات والخطوط المضمَّنة عبر pypdf.

يوفّر بديلاً متكاملاً ومستقلاً عند عدم توفّر PyMuPDF (`fitz`):
  ١. يحلّل تيار الرسم (`ContentStream`) ومعاملات التحويل
     (`cm`, `Tm`, `Td`, `TD`, `T*`, `Tf`, `TL`, `Tc`, `Tw`, `Tz`, `Tj`, `TJ`, `'`, `"`).
  ٢. يفكّ جداول `/ToUnicode` (شاملةً `beginbfchar` و`beginbfrange` والرباطات).
  ٣. يحسب عرض كل جليف بدقّة من مصفوفات `/W` أو `/Widths` أو جدول `hmtx`.
  ٤. يطبّق نفس خوارزمية ربط الحركات الهندسي وتحليل البنية (`analyze_layout`).
  ٥. يستخرج بايتات الخطوط المضمَّنة لدعم الدرجة ٣ (`cmap`/`GSUB`).
"""

from __future__ import annotations

import contextlib
import math
import re
import struct
from collections.abc import Iterator
from functools import cache
from typing import TYPE_CHECKING, Any

from ..noise import GeometricNoiseConfig, GeometricNoiseFilter
from .base import Extractor, RawPage
from .pymupdf_extractor import PyMuPDFExtractor

if TYPE_CHECKING:
    from ..layout import LayoutConfig

__all__ = ["PyPDFExtractor"]


_BFCHAR_BLOCK_RE = re.compile(rb"beginbfchar\s*(.*?)\s*endbfchar", re.DOTALL)
_BFRANGE_BLOCK_RE = re.compile(rb"beginbfrange\s*(.*?)\s*endbfrange", re.DOTALL)
_BFCHAR_PAIR_RE = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>")
_BFRANGE_LINE_RE = re.compile(
    rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<([0-9A-Fa-f]+)>|\[([^\]]*)\])"
)
_HEX_TOKEN_RE = re.compile(rb"<([0-9A-Fa-f]+)>")


def _decode_utf16be_hex(hex_bytes: bytes) -> str:
    s = hex_bytes.decode("ascii", errors="ignore").strip()
    if not s:
        return ""
    if len(s) in (5, 6):
        try:
            cp = int(s, 16)
            if 0 <= cp <= 0x10FFFF:
                return chr(cp)
        except Exception:
            return ""
    if len(s) % 2 == 1:
        s = "0" + s
    try:
        raw = bytes.fromhex(s)
    except Exception:
        return ""
    if not raw:
        return ""
    if len(raw) == 1:
        return chr(raw[0])
    if len(raw) % 2 == 0:
        try:
            return raw.decode("utf-16-be", errors="surrogatepass")
        except Exception:
            pass
    return "".join(chr(b) for b in raw)


def _parse_tounicode_cmap(cmap_bytes: bytes) -> tuple[dict[int, str], int]:
    """يحلّل جدول ToUnicode CMap ويُرجع (خريطة الكود ← النص، عرض الكود بالبايتات)."""
    mapping: dict[int, str] = {}
    max_hex_len = 2

    for block in _BFCHAR_BLOCK_RE.findall(cmap_bytes):
        for src_hex, dst_hex in _BFCHAR_PAIR_RE.findall(block):
            if len(src_hex) > max_hex_len:
                max_hex_len = len(src_hex)
            code = int(src_hex, 16)
            val = _decode_utf16be_hex(dst_hex)
            if val:
                mapping[code] = val

    for block in _BFRANGE_BLOCK_RE.findall(cmap_bytes):
        for m in _BFRANGE_LINE_RE.finditer(block):
            start_hex, end_hex, _full_dst, single_dst, array_dst = m.groups()
            if len(start_hex) > max_hex_len:
                max_hex_len = len(start_hex)
            start_code = int(start_hex, 16)
            end_code = int(end_hex, 16)
            if end_code < start_code or end_code - start_code > 0xFFFF:
                continue
            if single_dst is not None:
                base_str = _decode_utf16be_hex(single_dst)
                if len(base_str) == 1:
                    base_cp = ord(base_str)
                    for offset in range(end_code - start_code + 1):
                        mapping[start_code + offset] = chr(base_cp + offset)
                elif base_str:
                    prefix, last_ch = base_str[:-1], ord(base_str[-1])
                    for offset in range(end_code - start_code + 1):
                        mapping[start_code + offset] = prefix + chr(last_ch + offset)
            elif array_dst is not None:
                items = _HEX_TOKEN_RE.findall(array_dst)
                for offset, item_hex in enumerate(items):
                    if start_code + offset > end_code:
                        break
                    val = _decode_utf16be_hex(item_hex)
                    if val:
                        mapping[start_code + offset] = val

    code_bytes = 2 if max_hex_len > 2 else 1
    return mapping, code_bytes


def _parse_ttf_hmtx_widths(font_bytes: bytes) -> tuple[dict[int, float], float]:
    """يقرأ عرض كل جليف (advanceWidth) من جدول hmtx ووحدات الـ em من جدول head."""
    from ..cmap import _parse_sfnt_tables

    tables = _parse_sfnt_tables(font_bytes)
    if not tables or "head" not in tables or "hhea" not in tables or "hmtx" not in tables:
        return {}, 1000.0
    head = tables["head"]
    hhea = tables["hhea"]
    hmtx = tables["hmtx"]
    if len(head) < 20 or len(hhea) < 36:
        return {}, 1000.0
    units_per_em = float(struct.unpack(">H", head[18:20])[0] or 1000)
    num_hmetrics = struct.unpack(">H", hhea[34:36])[0]
    widths: dict[int, float] = {}
    pos = 0
    last_adv = 1000.0
    for gid in range(num_hmetrics):
        if pos + 4 > len(hmtx):
            break
        adv, _lsb = struct.unpack(">Hh", hmtx[pos : pos + 4])
        pos += 4
        last_adv = (adv * 1000.0) / units_per_em
        widths[gid] = last_adv
    if "maxp" in tables and len(tables["maxp"]) >= 6:
        num_glyphs = struct.unpack(">H", tables["maxp"][4:6])[0]
        for gid in range(num_hmetrics, num_glyphs):
            widths[gid] = last_adv
    return widths, units_per_em


def _parse_cid_widths(w_array: list[Any]) -> dict[int, float]:
    """يفكّ مصفوفة `/W` في خطوط CIDFont إلى خريطة `cid -> width`."""
    widths: dict[int, float] = {}
    i = 0
    n = len(w_array)
    while i < n:
        try:
            first_cid = int(w_array[i])
        except Exception:
            i += 1
            continue
        if i + 1 >= n:
            break
        second = w_array[i + 1]
        is_seq = isinstance(second, list) or (
            hasattr(second, "__iter__") and not isinstance(second, (str, bytes))
        )
        if is_seq:
            arr = list(second)
            for idx, w in enumerate(arr):
                with contextlib.suppress(Exception):
                    widths[first_cid + idx] = float(w)
            i += 2
        elif i + 2 < n:
            with contextlib.suppress(Exception):
                end_cid = int(second)
                w_val = float(w_array[i + 2])
                if 0 <= end_cid - first_cid <= 0xFFFF:
                    for cid in range(first_cid, end_cid + 1):
                        widths[cid] = w_val
            i += 3
        else:
            break
    return widths


def _mat_mul(a: list[float], b: list[float]) -> list[float]:
    """ضرب مصفوفتَي تحويل 3x3 ممثَّلتَين بـ 6 معاملات `[a, b, c, d, e, f]`."""
    return [
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    ]


class _FontInfo:
    def __init__(
        self,
        base_font: str,
        is_two_byte: bool,
        to_unicode: dict[int, str],
        widths: dict[int, float],
        default_width: float = 500.0,
        embedded_map: dict[int, str] | None = None,
    ) -> None:
        self.base_font = base_font
        self.is_two_byte = is_two_byte
        self.to_unicode = to_unicode
        self.widths = widths
        self.default_width = default_width
        self.embedded_map = embedded_map or {}


class PyPDFExtractor(Extractor):
    name = "pypdf"

    def __init__(
        self,
        sort: bool = False,
        bidi: str = "geometry",
        *,
        layout_mode: str = "auto",
        geometric_noise: GeometricNoiseConfig | None = None,
        preserve_spatial_bboxes: bool = False,
        layout_config: LayoutConfig | None = None,
    ) -> None:
        self.sort = sort
        self.bidi = bidi
        self.layout_mode = layout_mode
        self.preserve_spatial_bboxes = preserve_spatial_bboxes
        self.layout_config = layout_config
        self.noise_filter = (
            GeometricNoiseFilter(geometric_noise)
            if geometric_noise is not None
            else None
        )

    @classmethod
    @cache
    def available(cls) -> bool:
        try:
            import pypdf  # noqa: F401
            return True
        except ImportError:
            return False

    def _open(self, path: str):
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("محرّك pypdf غير مثبَّت: pip install pypdf") from exc
        return PdfReader(path)

    def metadata(self, path: str) -> dict[str, str]:
        reader = self._open(path)
        meta = reader.metadata or {}
        return {
            "producer": str(meta.get("/Producer") or ""),
            "creator": str(meta.get("/Creator") or ""),
        }

    @staticmethod
    def _deref(obj: Any) -> Any:
        while hasattr(obj, "get_object"):
            try:
                nxt = obj.get_object()
                if nxt is obj:
                    break
                obj = nxt
            except Exception:
                break
        return obj

    def _extract_embedded_font_bytes(self, font_dict: Any) -> bytes | None:
        font_dict = self._deref(font_dict)
        if not isinstance(font_dict, dict):
            return None
        descriptors = [font_dict.get("/FontDescriptor")]
        if "/DescendantFonts" in font_dict:
            desc = self._deref(font_dict["/DescendantFonts"])
            if isinstance(desc, list):
                for df in desc:
                    df_obj = self._deref(df)
                    if isinstance(df_obj, dict) and "/FontDescriptor" in df_obj:
                        descriptors.append(df_obj["/FontDescriptor"])
        for fd_ref in descriptors:
            fd = self._deref(fd_ref)
            if not isinstance(fd, dict):
                continue
            for key in ("/FontFile2", "/FontFile3", "/FontFile"):
                if key in fd:
                    with contextlib.suppress(Exception):
                        stream = self._deref(fd[key])
                        data = stream.get_data()
                        if data:
                            return bytes(data)
        return None

    def _build_font_info(
        self,
        font_ref: Any,
        fallback_cmaps: dict[str, dict[int, str]],
    ) -> _FontInfo:
        fdict = self._deref(font_ref)
        if not isinstance(fdict, dict):
            return _FontInfo("Unknown", False, {}, {})

        base_font = str(fdict.get("/BaseFont") or "/Unknown").lstrip("/")
        subtype = str(fdict.get("/Subtype") or "")
        encoding = fdict.get("/Encoding")
        is_two_byte = subtype == "/Type0" or (
            isinstance(encoding, str) and "Identity" in encoding
        )

        to_unicode: dict[int, str] = {}
        if "/ToUnicode" in fdict:
            with contextlib.suppress(Exception):
                tu_stream = self._deref(fdict["/ToUnicode"])
                tu_data = tu_stream.get_data()
                parsed_map, code_bytes = _parse_tounicode_cmap(tu_data)
                to_unicode.update(parsed_map)
                if code_bytes == 2:
                    is_two_byte = True

        # مشاركة ToUnicode التراكمية لنفس عائلة الخط عبر الصفحات (لإنقاذ الخطوط الفرعية الناقصة)
        canon_key = re.sub(r"^[A-Z]{6}\+", "", base_font)
        if to_unicode:
            shared = fallback_cmaps.setdefault(canon_key, {})
            for k, v in to_unicode.items():
                if k not in shared:
                    shared[k] = v

        widths: dict[int, float] = {}
        default_width = 500.0

        if "/DescendantFonts" in fdict:
            desc = self._deref(fdict["/DescendantFonts"])
            if isinstance(desc, list) and desc:
                cid_font = self._deref(desc[0])
                if isinstance(cid_font, dict):
                    if "/DW" in cid_font:
                        with contextlib.suppress(Exception):
                            default_width = float(self._deref(cid_font["/DW"]))
                    if "/W" in cid_font:
                        with contextlib.suppress(Exception):
                            w_arr = [self._deref(x) for x in self._deref(cid_font["/W"])]
                            widths.update(_parse_cid_widths(w_arr))
        elif "/Widths" in fdict:
            with contextlib.suppress(Exception):
                first_char = int(self._deref(fdict.get("/FirstChar", 0)))
                w_arr = self._deref(fdict["/Widths"])
                for idx, w in enumerate(w_arr):
                    widths[first_char + idx] = float(self._deref(w))

        embedded_map: dict[int, str] = {}
        font_bytes = self._extract_embedded_font_bytes(fdict)
        if font_bytes:
            if not widths:
                with contextlib.suppress(Exception):
                    hmtx_w, _ = _parse_ttf_hmtx_widths(font_bytes)
                    widths.update(hmtx_w)
            if not to_unicode:
                with contextlib.suppress(Exception):
                    from ..cmap import build_glyph_map

                    gm = build_glyph_map(font_bytes, base_font)
                    embedded_map = gm.by_id

        # تعويض المحارف المفقودة من خريطة نفس الخط في صفحات سابقة إن لم تتوفر في الجداول
        if canon_key in fallback_cmaps:
            for k, v in fallback_cmaps[canon_key].items():
                if k not in to_unicode:
                    to_unicode[k] = v

        return _FontInfo(
            base_font=base_font,
            is_two_byte=is_two_byte,
            to_unicode=to_unicode,
            widths=widths,
            default_width=default_width,
            embedded_map=embedded_map,
        )

    def _collect_page_fonts(
        self,
        resources: Any,
        fallback_cmaps: dict[str, dict[int, str]],
    ) -> dict[str, _FontInfo]:
        res = self._deref(resources)
        if not isinstance(res, dict):
            return {}
        font_res = self._deref(res.get("/Font"))
        if not isinstance(font_res, dict):
            return {}
        fonts: dict[str, _FontInfo] = {}
        for k, v in font_res.items():
            fonts[str(k)] = self._build_font_info(v, fallback_cmaps)
        return fonts

    def _page_has_images(self, resources: Any) -> bool:
        res = self._deref(resources)
        if not isinstance(res, dict):
            return False
        xobj = self._deref(res.get("/XObject"))
        if not isinstance(xobj, dict):
            return False
        for v in xobj.values():
            obj = self._deref(v)
            if isinstance(obj, dict) and str(obj.get("/Subtype") or "") == "/Image":
                return True
        return False

    @staticmethod
    def _decode_operand_bytes(raw_op: Any, is_two_byte: bool) -> list[int]:
        from pypdf.generic import ByteStringObject

        if hasattr(raw_op, "original_bytes"):
            b = bytes(raw_op.original_bytes)
        elif isinstance(raw_op, (bytes, bytearray, ByteStringObject)):
            b = bytes(raw_op)
        elif isinstance(raw_op, str):
            b = raw_op.encode("latin1", errors="replace")
        else:
            return []

        if is_two_byte and len(b) >= 2:
            if len(b) % 2 == 1:
                b = b + b"\x00"
            return [
                (b[i] << 8) | b[i + 1]
                for i in range(0, len(b), 2)
            ]
        return list(b)

    def _build_page_traces(
        self,
        page: Any,
        reader: Any,
        page_height: float,
        fallback_cmaps: dict[str, dict[int, str]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        from pypdf.generic import ContentStream

        fonts = self._collect_page_fonts(page.get("/Resources"), fallback_cmaps)
        font_names = sorted({f.base_font for f in fonts.values() if f.base_font})

        try:
            content = ContentStream(page.get_contents(), reader)
        except Exception:
            return [], font_names

        traces: list[dict[str, Any]] = []
        seqno = 0

        def walk_operations(
            ops: list[tuple[list[Any], bytes]],
            local_fonts: dict[str, _FontInfo],
            initial_ctm: list[float],
        ) -> None:
            nonlocal seqno
            ctm = list(initial_ctm)
            ctm_stack: list[list[float]] = []
            tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
            tlm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
            current_font: _FontInfo | None = (
                next(iter(local_fonts.values())) if local_fonts else None
            )
            font_size = 10.0
            char_space = 0.0
            word_space = 0.0
            horiz_scale = 1.0
            leading = 0.0
            text_rise = 0.0

            def emit_string_operand(op_item: Any) -> None:
                nonlocal tm, seqno
                finfo = current_font or _FontInfo("Unknown", False, {}, {})
                codes = self._decode_operand_bytes(op_item, finfo.is_two_byte)
                if not codes:
                    return
                chars_list: list[
                    tuple[int, int, tuple[float, float], tuple[float, float, float, float]]
                ] = []
                # حجم الخط الفعلي على الصفحة بعد ضرب مصفوفة النص ومصفوفة التحويل
                m = _mat_mul(tm, ctm)
                eff_size = max(
                    1.0,
                    abs(font_size)
                    * math.hypot(m[0], m[1] if m[0] == 0 else 0.0)
                    if (m[0] or m[1])
                    else abs(font_size),
                )
                for cid in codes:
                    # 1. تحويل الكود إلى محرف يونيكود (أو PUA عند غياب ToUnicode لدعم الدرجة 3)
                    mapped = finfo.to_unicode.get(cid)
                    if mapped is None:
                        if finfo.embedded_map and cid in finfo.embedded_map:
                            # ليقوم _recover_broken_cmap_page بفكّه وتسجيله في الإحصاءات
                            mapped = "\ue000"
                        elif not finfo.to_unicode and not finfo.is_two_byte and 32 <= cid <= 126:
                            mapped = chr(cid)
                        elif not finfo.to_unicode and finfo.embedded_map:
                            mapped = "\ue000"
                        else:
                            mapped = ""

                    cur_m = _mat_mul(tm, ctm)
                    px = cur_m[4]
                    py = page_height - (cur_m[5] + text_rise)

                    w_thousandths = finfo.widths.get(cid, finfo.default_width)
                    adv_user = (
                        (w_thousandths / 1000.0) * font_size
                        + char_space
                        + (word_space if cid == 32 or mapped == " " else 0.0)
                    ) * horiz_scale
                    adv_page = abs(adv_user * cur_m[0]) if cur_m[0] else abs(adv_user)
                    bbox = (
                        px,
                        py - eff_size,
                        px + max(adv_page, eff_size * 0.25),
                        py + eff_size * 0.25,
                    )

                    # تصفية الكشيدة الزخرفية الطويلة والمحارف الفارغة غير المربوطة
                    if mapped and mapped != "\u0640":
                        if len(mapped) == 1:
                            chars_list.append((ord(mapped), cid, (px, py), bbox))
                        else:
                            # إذا كان الحرف رباطاً في ToUnicode (أو حرفاً مع حركته)، نصدر كل نقطة
                            # بنفس الأصل الهندسي ليقوم _extract_glyphs بفصل الحركات وربطها
                            step = adv_page / max(1, len(mapped))
                            for ci, ch in enumerate(mapped):
                                if ch == "\u0640":
                                    continue
                                cx = px + ci * step
                                chars_list.append(
                                    (
                                        ord(ch),
                                        cid,
                                        (cx, py),
                                        (
                                            cx,
                                            py - eff_size,
                                            cx + max(step, 1.0),
                                            py + eff_size * 0.25,
                                        ),
                                    )
                                )

                    # تحديث موضع القلم النصي
                    tm = _mat_mul([1.0, 0.0, 0.0, 1.0, adv_user, 0.0], tm)

                if chars_list:
                    seqno += 1
                    traces.append(
                        {
                            "seqno": seqno,
                            "type": 0,
                            "font": finfo.base_font,
                            "size": eff_size,
                            "chars": chars_list,
                        }
                    )

            for operands, op in ops:
                if op == b"q":
                    ctm_stack.append(list(ctm))
                elif op == b"Q":
                    if ctm_stack:
                        ctm = ctm_stack.pop()
                elif op == b"cm" and len(operands) == 6:
                    with contextlib.suppress(Exception):
                        m6 = [float(x) for x in operands]
                        ctm = _mat_mul(m6, ctm)
                elif op == b"BT":
                    tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
                    tlm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
                elif op == b"Tf" and len(operands) >= 2:
                    fname = str(operands[0])
                    if fname in local_fonts:
                        current_font = local_fonts[fname]
                    with contextlib.suppress(Exception):
                        font_size = float(operands[1])
                elif op == b"Tc" and operands:
                    with contextlib.suppress(Exception):
                        char_space = float(operands[0])
                elif op == b"Tw" and operands:
                    with contextlib.suppress(Exception):
                        word_space = float(operands[0])
                elif op == b"Tz" and operands:
                    with contextlib.suppress(Exception):
                        horiz_scale = float(operands[0]) / 100.0
                elif op == b"TL" and operands:
                    with contextlib.suppress(Exception):
                        leading = float(operands[0])
                elif op == b"Ts" and operands:
                    with contextlib.suppress(Exception):
                        text_rise = float(operands[0])
                elif op == b"Tm" and len(operands) == 6:
                    with contextlib.suppress(Exception):
                        tm = [float(x) for x in operands]
                        tlm = list(tm)
                elif op == b"Td" and len(operands) == 2:
                    with contextlib.suppress(Exception):
                        tx, ty = float(operands[0]), float(operands[1])
                        tlm = _mat_mul([1.0, 0.0, 0.0, 1.0, tx, ty], tlm)
                        tm = list(tlm)
                elif op == b"TD" and len(operands) == 2:
                    with contextlib.suppress(Exception):
                        tx, ty = float(operands[0]), float(operands[1])
                        leading = -ty
                        tlm = _mat_mul([1.0, 0.0, 0.0, 1.0, tx, ty], tlm)
                        tm = list(tlm)
                elif op == b"T*":
                    tlm = _mat_mul([1.0, 0.0, 0.0, 1.0, 0.0, -leading], tlm)
                    tm = list(tlm)
                elif op == b"Tj" and operands:
                    emit_string_operand(operands[0])
                elif op == b"'" and operands:
                    tlm = _mat_mul([1.0, 0.0, 0.0, 1.0, 0.0, -leading], tlm)
                    tm = list(tlm)
                    emit_string_operand(operands[0])
                elif op == b'"' and len(operands) >= 3:
                    with contextlib.suppress(Exception):
                        word_space = float(operands[0])
                        char_space = float(operands[1])
                    tlm = _mat_mul([1.0, 0.0, 0.0, 1.0, 0.0, -leading], tlm)
                    tm = list(tlm)
                    emit_string_operand(operands[2])
                elif op == b"TJ" and operands:
                    arr = operands[0]
                    if hasattr(arr, "__iter__") and not isinstance(arr, (bytes, str)):
                        for item in arr:
                            if isinstance(item, (int, float)) or (
                                hasattr(item, "__float__") and not isinstance(item, (bytes, str))
                            ):
                                with contextlib.suppress(Exception):
                                    shift = (-float(item) / 1000.0) * font_size * horiz_scale
                                    tm = _mat_mul([1.0, 0.0, 0.0, 1.0, shift, 0.0], tm)
                            else:
                                emit_string_operand(item)

        walk_operations(content.operations, fonts, [1.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        return traces, font_names

    def pages(self, path: str) -> Iterator[RawPage]:
        reader = self._open(path)
        helper = PyMuPDFExtractor(
            sort=self.sort,
            bidi=self.bidi,
            layout_mode=self.layout_mode,
            geometric_noise=self.noise_filter.config if self.noise_filter else None,
            preserve_spatial_bboxes=self.preserve_spatial_bboxes,
            layout_config=self.layout_config,
        )

        fallback_cmaps: dict[str, dict[int, str]] = {}
        all_page_traces: list[tuple[int, float, float, list[str], bool, list[dict[str, Any]]]] = []

        for idx, page in enumerate(reader.pages):
            number = idx + 1
            box = page.mediabox
            width = float(box.width) if box else 595.0
            height = float(box.height) if box else 842.0
            has_images = self._page_has_images(page.get("/Resources"))
            traces, fonts = self._build_page_traces(page, reader, height, fallback_cmaps)
            all_page_traces.append((number, width, height, fonts, has_images, traces))

        repeated_keys: set[tuple] = set()
        if (
            self.noise_filter is not None
            and self.bidi == "geometry"
            and self.noise_filter.config.remove_repeated_short_spans
        ):
            repeated_keys = self.noise_filter.repeated_keys(
                item[5] for item in all_page_traces
            )

        for number, width, height, fonts, has_images, traces in all_page_traces:
            if self.bidi == "geometry":
                noise_removed = 0
                noise_reasons: dict[str, int] = {}
                effective_traces: Any = traces
                if self.noise_filter is not None:
                    effective_traces, noise_removed, noise_reasons = self.noise_filter.filter_spans(
                        traces, repeated_keys
                    )
                glyphs = helper._extract_glyphs(None, effective_traces)
                layout = helper._build_layout(glyphs, width, height)
                text = (
                    layout.plain_text
                    if layout
                    else helper._geometric_text_from_glyphs(glyphs)
                )
                yield RawPage(
                    number=number,
                    text=text,
                    fonts=fonts,
                    has_images=has_images,
                    width=width,
                    height=height,
                    glyphs=glyphs,
                    layout=layout,
                    noise_spans_removed=noise_removed,
                    noise_reasons=noise_reasons,
                )
            else:
                raw_text = reader.pages[number - 1].extract_text() or ""
                yield RawPage(
                    number=number,
                    text=raw_text,
                    fonts=fonts,
                    has_images=has_images,
                    width=width,
                    height=height,
                )

    def font_bytes(self, path: str) -> dict[str, bytes]:
        reader = self._open(path)
        out: dict[str, bytes] = {}
        for page in reader.pages:
            res = self._deref(page.get("/Resources"))
            if not isinstance(res, dict):
                continue
            font_res = self._deref(res.get("/Font"))
            if not isinstance(font_res, dict):
                continue
            for fref in font_res.values():
                fdict = self._deref(fref)
                if not isinstance(fdict, dict):
                    continue
                base_font = str(fdict.get("/BaseFont") or "").lstrip("/")
                if not base_font or base_font in out:
                    continue
                data = self._extract_embedded_font_bytes(fdict)
                if data:
                    out[base_font] = data
        return out
