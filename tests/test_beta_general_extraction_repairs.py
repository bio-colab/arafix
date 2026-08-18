from arafix import repair_text
from arafix.hygiene import collapse_midword_spaces
from arafix.pdf_confusions import repair_pdf_confusions


def test_pdf_confusion_does_not_corrupt_valid_ghareeb():
    assert repair_pdf_confusions("القسم: الغريب والمعاجم").text == "القسم: الغريب والمعاجم"


def test_article_repair_does_not_join_valid_kamil_boundary():
    assert repair_pdf_confusions("كامل السراج").text == "كامل السراج"


def test_final_ta_marbuta_space_is_collapsed_only_inside_long_word():
    assert collapse_midword_spaces("مقدم ة") == "مقدمة"
    assert collapse_midword_spaces("في ة") == "في ة"


def test_lillah_keeps_real_word_boundary():
    assert collapse_midword_spaces("الحمد لله رب العالمين") == "الحمد لله رب العالمين"


def test_visual_stream_repairs_general_word_shape():
    repaired = repair_text("مجاعملاو بيرغلا :مسقلا\nة مدقم").text
    assert "مقدمة" in repaired
    assert "الغريب" in repaired
