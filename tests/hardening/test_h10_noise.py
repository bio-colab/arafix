
from __future__ import annotations

from arafix.noise import GeometricNoiseConfig, GeometricNoiseFilter


def span(text, color=(0.0, 0.0, 0.0), direction=(1.0, 0.0), size=12.0,
         bbox=(100.0, 700.0, 400.0, 720.0)):
    chars = [(ord(c), 0, (0.0, 0.0), bbox) for c in text]
    s = {"chars": chars, "size": size, "bbox": bbox}
    if color is not None:
        s["color"] = color
    if direction is not None:
        s["dir"] = direction
    return s


CFG = GeometricNoiseConfig()
F = GeometricNoiseFilter(CFG)


def dropped(spans, repeated_keys=None):
    kept, n, reasons = F.filter_spans(spans, repeated_keys)
    return n, reasons


def test_dark_horizontal_body_kept():
    n, _ = dropped([span("نص حقيقي طويل في متن الصفحة")])
    assert n == 0


def test_dark_rotated_heading_kept():
    """عنوان داكن مائل: الدوران وحده لا يكفي للحذف."""
    n, _ = dropped([span("فصل أول", direction=(0.7, -0.7), size=20.0)])
    assert n == 0


def test_gray_horizontal_kept():
    """رمادي فاتح لكن أفقي: الدوران شرط إلزامي."""
    n, _ = dropped([span("اقتباس رمادي كبير", color=(0.85, 0.85, 0.85), size=24.0)])
    assert n == 0


def test_light_big_horizontal_resembling_watermark_kept():
    """نص فاتح كبير أفقي يشبه العلامة المائية - يبقى لعدم الدوران."""
    n, _ = dropped([span(
        "مسودة غير نهائية للمسودة",
        color=(0.8, 0.8, 0.8), size=40.0)])
    assert n == 0


def test_classic_gray_rotated_big_dropped():
    n, r = dropped([span(
        "WATERMARK مسودة",
        color=(0.8, 0.82, 0.78),
        direction=(0.9, -0.43),
        size=30.0)])
    assert n == 1
    assert "light-gray-rotated" in r


def test_gray_rotated_small_but_repeated_dropped():
    s = span("ت", color=(0.75, 0.75, 0.75), direction=(0.95, -0.3), size=10.0)
    key = F._repeat_key(s)
    assert key is not None  # العينة يجب أن تحمل مفتاح تكرارٍ صالحاً
    keys = set()
    keys.add(key)
    n, _ = dropped([s], repeated_keys=keys)
    assert n == 1


def test_rotation_boundary_7_9_degrees():
    import math
    results = {}
    for deg in (7.9, 8.1):
        rad = math.radians(deg)
        d = (math.cos(rad), -math.sin(rad))
        n, _ = dropped([span(
            "علامة مائية كبيرة",
            color=(0.8, 0.8, 0.8), direction=d, size=30.0)])
        results[deg] = n
    assert results[7.9] == 0
    assert results[8.1] == 1


def test_gray_boundary_059_061():
    d = (0.9, -0.43)
    results = {}
    for mean in (0.59, 0.61):
        n, _ = dropped([span(
            "علامة مائية كبيرة", color=(mean, mean, mean),
            direction=d, size=30.0)])
        results[mean] = n
    assert results[0.59] == 0
    assert results[0.61] == 1


def test_zero_false_deletions_on_ambiguous_corpus():
    corpus = [
        span("متن أساسي داكن أفقي"),
        span("عنوان داكن مائل", direction=(0.7, -0.7), size=18.0),
        span("حاشية داكنة صغيرة", size=8.0),
        span("ختم أحمر", color=(0.7, 0.1, 0.1)),
        span("نص ملون أزرق", color=(0.1, 0.2, 0.8)),
        span("رمادي أفقي واسع", color=(0.9, 0.9, 0.9), size=28.0),
        span("فاتح مائل صغير جداً", color=(0.85, 0.85, 0.85),
             direction=(0.8, -0.6), size=9.0),
    ]
    n, reasons = dropped(corpus)
    assert n == 0


def test_dark_rotated_watermark_conservatively_kept():
    """علامة داكنة مائلة تشبه المتن: الفلتر متحفظ يبقيها - توثيق سلوك."""
    n, _ = dropped([span(
        "شعار داكن مائل", color=(0.1, 0.1, 0.1),
        direction=(0.9, -0.43), size=30.0)])
    assert n == 0
