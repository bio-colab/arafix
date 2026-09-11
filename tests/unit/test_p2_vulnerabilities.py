"""
وحدة اختبارات التحقق من معالجة الثغرة البنيوية الاستراتيجية P2:
تفعيل عكس شجرة جدول GSUB في الخطوط المدمجة لحل خطوط Subset والرموز الصماء CID رياضياً.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from arafix.cmap import build_glyph_map, reverse_font_cmap, _propagate_gsub_mappings
from arafix.unicode_tables import is_arabic

AMIRI_FONT_PATH = Path("benchmarks/glyph_fixtures/fonts/Amiri-Regular.ttf")


class TestP2GSUBInversion:
    """اختبارات P2: عكس شجرة GSUB في الخطوط المدمجة."""

    @pytest.mark.skipif(not AMIRI_FONT_PATH.is_file(), reason="خط أميري المرجعي غير متوفر")
    def test_amiri_gsub_expansion_count(self):
        """التحقق من أن عكس شجرة GSUB يضيف أكثر من 1,000 جليف إضافي في خط أميري."""
        data = AMIRI_FONT_PATH.read_bytes()
        gm = build_glyph_map(data, "Amiri-Regular")

        assert gm.source == "gsub"
        assert len(gm.by_name) >= 2600, f"تغطية غير متوقعة: {len(gm.by_name)}"
        assert any("GSUB" in note for note in gm.notes)
        assert gm.confidence >= 0.35

    @pytest.mark.skipif(not AMIRI_FONT_PATH.is_file(), reason="خط أميري المرجعي غير متوفر")
    def test_amiri_ligatures_and_contextual_forms_resolved(self):
        """التحقق من حل أشكال الوصل والرباطات التي لا يحويها جدول cmap المباشر."""
        data = AMIRI_FONT_PATH.read_bytes()
        mapping = reverse_font_cmap(data)

        # التحقق من أن الرباطات والأشكال السياقية تحمل نصوصاً عربية صحيحة
        arabic_resolved = [v for v in mapping.values() if any(is_arabic(c) or ("\u0600" <= c <= "\u06ff") for c in v)]
        assert len(arabic_resolved) >= 1800

        # رباط اللام-ألف ومشتقاته
        lam_alef_forms = [v for v in mapping.values() if "لا" in v or "لأ" in v or "لإ" in v or "لآ" in v]
        assert len(lam_alef_forms) >= 8

    def test_synthetic_gsub_propagation_bidirectional(self):
        """اختبار الانتشار ثنائي الاتجاه عبر كائن خط صوري (Mock TTFont)."""
        class MockSingleSubst:
            def __init__(self, mapping_dict):
                self.LookupType = 1
                self.mapping = mapping_dict

        class MockLigature:
            def __init__(self, component, lig_glyph):
                self.Component = component
                self.LigGlyph = lig_glyph

        class MockLigatureSubst:
            def __init__(self, lig_dict):
                self.LookupType = 4
                self.ligatures = lig_dict

        class MockLookup:
            def __init__(self, l_type, subtables):
                self.LookupType = l_type
                self.SubTable = subtables

        class MockGSUBTable:
            def __init__(self, lookups):
                class LookupList:
                    Lookup = lookups
                self.LookupList = LookupList()

        class MockGSUB:
            def __init__(self, lookups):
                self.table = MockGSUBTable(lookups)

        class MockFont:
            def __init__(self, lookups):
                self.tables = {"GSUB": MockGSUB(lookups)}
            def get(self, tag):
                return self.tables.get(tag)

        # سيناريو اختبار:
        # 1. الاستبدال المفرد للأشكال السياقية: cid001 ("ب") -> cid002 (شكل ابتدائي غير معروف)
        # 2. العكس: cid004 ("ج") <- cid003 (معروف في الأصل فقط كشكل نهائي)
        # 3. رباط مركب: cid010 ("ل") + cid011 ("ا") -> cid050 (رباط "لا")
        sub1 = MockSingleSubst({"cid001": "cid002", "cid003": "cid004"})
        lig1 = MockLigatureSubst({"cid010": [MockLigature(["cid011"], "cid050")]})

        lookups = [
            MockLookup(1, [sub1]),
            MockLookup(4, [lig1]),
        ]
        font = MockFont(lookups)

        initial_map = {
            "cid001": "ب",      # معروف اسماً
            "cid004": "ج",      # معروف كناتج استبدال
            "cid010": "ل",
            "cid011": "ا",
        }

        expanded_map, added = _propagate_gsub_mappings(font, initial_map)

        # التحقق من استنباط cid002 ("ب")
        assert expanded_map.get("cid002") == "ب"
        # التحقق من العكس: استنباط cid003 ("ج")
        assert expanded_map.get("cid003") == "ج"
        # التحقق من استنباط الرباط المركب cid050 ("لا")
        assert expanded_map.get("cid050") == "لا"
        assert added == 3

    def test_graceful_fallback_without_gsub(self):
        """التحقق من عدم حدوث أي استثناء عند خلو الخط من جدول GSUB."""
        class MockFontEmpty:
            def get(self, tag):
                return None

        initial_map = {"g1": "أ", "g2": "ب"}
        res_map, added = _propagate_gsub_mappings(MockFontEmpty(), initial_map)
        assert res_map == initial_map
        assert added == 0
