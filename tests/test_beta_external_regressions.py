from arafix import repair_text


def test_presentation_punctuation_is_folded_with_letters():
    assert repair_text("ﺕﻭﺽﺡ ﹒").text == "توضح."


def test_mojibake_soft_hyphen_byte_is_recovered_before_hygiene():
    broken = "ØªÙ\x88Ø¶Ø­ Ù\x87Ø°Ù\x87"
    assert repair_text(broken).text == "توضح هذه"


def test_reversed_time_prefers_valid_clock_value():
    assert repair_text(".03:90 ةعاسلا دنع").text == "عند الساعة 09:30."


def test_reversed_page_range_is_not_misclassified_as_phone():
    text = ".ةعوبطملا ةخسنلا يف ةحفص 041-521 نيب لاجملا حوارتي"
    assert repair_text(text).text == "يتراوح المجال بين 125-140 صفحة في النسخة المطبوعة."


def test_reversed_percent_is_not_left_backwards():
    text = ".4.2v رادصإلا يف %5.79 يه ةعقوتملا ةجيتنلا"
    assert repair_text(text).text == "النتيجة المتوقعة هي 97.5% في الإصدار v2.4."
