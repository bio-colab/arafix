# -*- coding: utf-8 -*-
"""تشريح أول حالة فاشلة في بذرة 11 — كاملة حتى النهاية."""
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
sys.path.insert(0, "../..")
sys.path.insert(0, r"D:\1\arafix\tests\hardening")

from arafix import fix_order  # noqa: E402
from test_h5_bidi_fuzz import SEGMENTS_COVERED, build_cases, skeleton  # noqa: E402

rng = random.Random(11)
cases = build_cases(rng, 80, wrap=False)

fails = []
for case in cases:
    out = fix_order(case[::-1])
    if skeleton(out) != skeleton(case):
        fails.append((case, out))

print(f"فشل: {len(fails)} من {len(cases)}")
c, o = fails[0]
print("IN :", repr(c))
print("OUT:", repr(o))
# موقع أول انحراف
g, h = skeleton(c), skeleton(o)
i = next((k for k, (a, b) in enumerate(zip(g, h)) if a != b), min(len(g), len(h)))
print("أول انحراف عند", i, ": ذهب", repr(g[max(0,i-10):i+10]), "| خرج", repr(h[max(0,i-10):i+10]))
