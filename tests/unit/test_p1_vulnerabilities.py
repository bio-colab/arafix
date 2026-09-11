"""
وحدة اختبارات التحقق من معالجة ثغرات الفئة P1:
1. P1.1: تشخيص وإنقاذ الكتل والعناوين وترويسات الجداول القصيرة (< 8 أحرف).
2. P1.2: كشف الأعمدة غير المتناظرة والقصيرة في layout.py ومنع تشابك السطور أفقياً.
"""

from __future__ import annotations

import pytest

from arafix import (
    Defect,
    PipelineConfig,
    TextBlock,
    diagnose,
    repair_blocks,
    repair_text,
)
from arafix.layout import Glyph, LayoutConfig, analyze_layout


class TestP1ShortBlocksAndTableCells:
    """اختبارات P1.1: العناوين القصيرة وترويسات الجداول تحت عتبة العينة."""

    @pytest.mark.parametrize(
        ("word", "expected_repaired"),
        [
            ("فدهلا", "الهدف"),
            ("خيراتلا", "التاريخ"),
            ("ةنسلا", "السنة"),
            ("مسلا", "السم"),
        ],
    )
    def test_short_cell_decisive_reversal_diagnosis(self, word: str, expected_repaired: str):
        """الكلمات القصيرة ذات البراهين القاطعة يجب أن تُشخَّص وتُصلَح بدقة."""
        d = diagnose(word)
        assert d.has(Defect.VISUAL_ORDER), f"فشل تشخيص {word} كترتيب بصري معكوس"
        assert d.metrics.get("order_score", 0.0) >= 0.8

        rep = repair_text(word)
        assert rep.text == expected_repaired
        assert rep.diagnosis.has(Defect.VISUAL_ORDER)

    @pytest.mark.parametrize("ambiguous_word", ["مر", "في", "من"])
    def test_small_ambiguous_sample_refusal_preserved(self, ambiguous_word: str):
        """الكلمات الملتبسة ثنائية الأحرف يجب أن تظل محمية وترفض الحكم بالانعكاس."""
        d = diagnose(ambiguous_word)
        assert not d.has(Defect.VISUAL_ORDER)
        assert d.has(Defect.NONE)
        assert d.metrics.get("order_score", 0.0) == 0.0

        rep = repair_text(ambiguous_word)
        assert rep.text == ambiguous_word

    def test_repair_blocks_short_table_cells(self):
        """اختبار repair_blocks على خلايا جدول قصيرة في ترويسة تقرير."""
        cells = [
            TextBlock(text="خيراتلا", id="c1", role="cell"),
            TextBlock(text="مسلا", id="c2", role="cell"),
            TextBlock(text="فدهلا", id="c3", role="cell"),
        ]
        res = repair_blocks(cells)
        assert res.texts == ["التاريخ", "السم", "الهدف"]
        for block_res in res.blocks:
            assert block_res.repair.diagnosis.has(Defect.VISUAL_ORDER)

    def test_mixed_page_with_short_header_rescued(self):
        """وراثة السياق: إنقاذ العنوان القصير المعكوس داخل صفحة تحتوي أسطراً معكوسة."""
        healthy_lines = [
            "تتناول هذه الدراسة أهم جوانب النظرية البنيوية في النقد الأدبي الحديث",
            "حيث يرصد الكاتب تطور المدرسة منذ نشأتها في عشرينيات القرن الماضي",
        ]
        reversed_line = "ةماعلاو ةغللا نم راداهإ هتاجرد لضفت ناوك يذلا باتكلا"
        short_header = "فدهلا"

        page = f"{healthy_lines[0]}\n{reversed_line}\n{short_header}\n{healthy_lines[1]}"
        cfg = PipelineConfig(rescue_mixed_lines=True)
        r = repair_text(page, cfg)

        assert reversed_line not in r.text
        assert short_header not in r.text
        assert "الهدف" in r.text
        assert healthy_lines[0] in r.text
        assert healthy_lines[1] in r.text

    def test_isolated_short_line_safety_preserved(self):
        """حماية السطر المنفرد: السطر القصير المعزول في صفحة سليمة تماماً لا يُنقذ بدون برهان."""
        healthy_lines = [
            "تتناول هذه الدراسة أهم جوانب النظرية البنيوية في النقد الأدبي الحديث",
            "حيث يرصد الكاتب تطور المدرسة منذ نشأتها في عشرينيات القرن الماضي",
        ]
        tiny_reversed = "ةماعلاو"
        page = f"{healthy_lines[0]}\n{tiny_reversed}\n{healthy_lines[1]}"

        cfg = PipelineConfig(rescue_mixed_lines=True)
        r = repair_text(page, cfg)
        assert tiny_reversed in r.text


class TestP1AsymmetricColumnLayout:
    """اختبارات P1.2: الأعمدة غير المتناظرة والقصيرة في layout.py."""

    def test_asymmetric_two_columns_rtl_reading_order(self):
        """كشف عمودين في الصفحة الأخيرة من بحث (15 سطراً يمين، 3 أسطر يسار)."""
        glyphs: list[Glyph] = []
        # عمود أيمن طويل (15 سطراً)
        for row in range(15):
            y = 150 + row * 24
            for j, ch in enumerate(f"عمود يمين سطر {row + 1} تفاصيل"):
                glyphs.append(Glyph(y=y, x=350 + j * 8, text=ch, size=10))

        # عمود أيسر ختامي قصير (3 أسطر فقط)
        for row in range(3):
            y = 150 + row * 24
            for j, ch in enumerate(f"عمود يسار سطر {row + 1} ختام"):
                glyphs.append(Glyph(y=y, x=50 + j * 8, text=ch, size=10))

        lay = analyze_layout(glyphs, page_width=600, page_height=800, mode="auto")

        # يجب كشف عمودين وليس عموداً واحداً مدمجاً
        assert lay.n_columns == 2
        assert lay.mode_used == "columns"
        assert len(lay.columns) == 2

        # منع التداخل الأفقي: لا يوجد سطر يجمع بين يمين ويسار
        for col in lay.columns:
            for ln in col.lines:
                assert not ("يمين" in ln.text and "يسار" in ln.text)

        # التحقق من تسلسل القراءة: قراءة العمود الأيمن كاملاً ثم الأيسر
        plain = lay.plain_text
        assert plain.index("عمود يمين سطر 1") < plain.index("عمود يمين سطر 15")
        assert plain.index("عمود يمين سطر 15") < plain.index("عمود يسار سطر 1")
        assert plain.index("عمود يسار سطر 1") < plain.index("عمود يسار سطر 3")

    def test_asymmetric_two_columns_ltr_reading_order(self):
        """كشف عمودين غير متناظرين بتسلسل قراءة LTR (اليسار طويل، اليمين قصير)."""
        glyphs: list[Glyph] = []
        # عمود أيسر طويل (15 سطراً)
        for row in range(15):
            y = 150 + row * 24
            for j, ch in enumerate(f"Left Col Line {row + 1} details"):
                glyphs.append(Glyph(y=y, x=50 + j * 8, text=ch, size=10))

        # عمود أيمن ختامي قصير (3 أسطر)
        for row in range(3):
            y = 150 + row * 24
            for j, ch in enumerate(f"Right Col Line {row + 1} end"):
                glyphs.append(Glyph(y=y, x=350 + j * 8, text=ch, size=10))

        cfg = LayoutConfig(reading_order="ltr")
        lay = analyze_layout(glyphs, page_width=600, page_height=800, config=cfg, mode="columns")

        assert lay.n_columns == 2
        plain = lay.plain_text
        assert plain.index("Left Col Line 1") < plain.index("Left Col Line 15")
        assert plain.index("Left Col Line 15") < plain.index("Right Col Line 1")
