"""
فحوصات التثبت والتحصين الشاملة لمخرجات تقرير Bintra v1.1.0 المعماري واللغوي.

تغطي هذه الوحدة الحالات الست التي شخصها التقرير:
1. الرسم القرآني والعلامات التراكبية (Quranic / Uthmanic Script & Combining Marks)
2. النصوص الفارسية والإقليمية (Persian / Farsi Script Direction Detection)
3. موازنة محارف التحكم الاتجاهي BiDi لمنع تسميم الطرفيات (BiDi Control Balancing)
4. الحفاظ على أعمدة الجداول النصية وإصلاح العملات (Table Column & Currency Preservation)
5. إعادة تموضع أرقام الهوامش المقذوفة (Footnote Relocation Defect)
6. صون دلالة الكسور الرياضية (Fraction Inversion Prevention)
"""

from arafix.diagnose import detect_visual_order
from arafix.order import balance_bidi_controls, fix_currency, reverse_visual_line
from arafix.pipeline import repair_text


def test_case_1_quranic_uthmanic_script_combining_marks():
    """الحالة 1: استرجاع البسملة القرآنية التراكبية بعكس كامل مع الحفاظ على الحركات ومواضعها."""
    logical = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"
    reversed_input = logical[::-1]

    # التأكد من كشف الانعكاس بثقة تامة
    score, _ = detect_visual_order(reversed_input)
    assert score > 0.8, f"Expected visual order detection score > 0.8, got {score}"

    # الاسترجاع التام للنص الأصلي دون تفكك الحركات أو سقوط المسافات
    restored = reverse_visual_line(reversed_input)
    assert restored == logical, f"Expected {logical!r}, got {restored!r}"


def test_case_2_persian_regional_script_direction_detection():
    """الحالة 2: كشف وإصلاح النصوص الفارسية التي تخلو من التاء المربوطة وألـ التعريف العربية."""
    reversed_persian = "تسا هبرگ كيك نيا"

    # كاشف الاتجاه يتعرف على الأفعال والمفردات الفارسية
    score, _ = detect_visual_order(reversed_persian)
    assert score > 0.8, f"Expected Persian visual order detection score > 0.8, got {score}"

    result = repair_text(reversed_persian)
    assert "است" in result.text
    assert "گربه" in result.text
    assert "كيك" in result.text


def test_case_3_bidi_control_balancing_and_anti_poisoning():
    """الحالة 3: موازنة علامات RLO/PDF لمنع تسميم واجهات الطرفية والمتصفحات."""
    # نص يحوي RLO و PDF معكوسين
    poisoned_input = "\u202eةغللا\u202c"
    restored = reverse_visual_line(poisoned_input)

    # يجب أن تُفتح RLO في البداية وتُغلق بمحرف PDF في النهاية، دون ترك RLO طليقة
    assert restored == "\u202eاللغة\u202c"
    assert not restored.endswith("\u202e"), "Terminal poisoning hazard: trailing open RLO detected!"

    # فحص المحلل المستقل للمكدس: إغلاق أي علامة فتح يتيمة
    dangling_rlo = "\u202eنص بدون إغلاق"
    balanced = balance_bidi_controls(dangling_rlo)
    assert balanced.endswith("\u202c"), "Unclosed RLO must be balanced with trailing PDF"

    # حذف علامة إغلاق يتيمة في الصدارة
    orphan_pdf = "\u202cنص"
    assert balance_bidi_controls(orphan_pdf) == "نص"


def test_case_4_table_column_and_currency_preservation():
    """الحالة 4: معالجة سطور الجداول النصية خليةً بخلية لمنع تبديل الأعمدة مع إصلاح العملات."""
    header = "| مسلا | نمثلا |"
    row = "| حافت | 100 د.ع |"

    restored_header = reverse_visual_line(header)
    restored_row = reverse_visual_line(row)

    # العمود الأول (الاسم/السم) والعمود الثاني (الثمن) يبقيان في ترتيبهما الصحيح
    assert restored_header in ("| الاسم | الثمن |", "| السم | الثمن |")
    assert restored_row == "| تفاح | 100 د.ع |"

    # فحص مباشر لدالة إصلاح العملات
    assert fix_currency("ع.د 250") == "250 د.ع"
    assert fix_currency("س.ر 50.5") == "50.5 ر.س"
    assert fix_currency("م.ج 1000") == "1000 ج.م"


def test_case_5_footnote_relocation():
    """الحالة 5: إعادة أرقام الهوامش المقذوفة بفعل العكس البصري إلى موضعها في نهاية السطر."""
    footnote_line = ".عجرمل اذه رظنا )1("
    restored = reverse_visual_line(footnote_line)

    assert restored in ("انظر هذا لمرجع. (1)", "انظر هذا المرجع. (1)")
    msg = "Footnote marker must not be moved to the beginning of sentence"
    assert not restored.startswith("(1)"), msg


def test_case_6_fraction_inversion_prevention():
    """الحالة 6: صون دلالة الكسور الرياضية (3/4 لا 4/3) مع النسب المئوية."""
    fraction_line = "%52.3 ةبسنب 4/3 لقأ"
    restored = reverse_visual_line(fraction_line)

    assert restored == "أقل 3/4 بنسبة 3.25%"
    assert "4/3" not in restored, "Fraction must be preserved as 3/4, not inverted to 4/3"
