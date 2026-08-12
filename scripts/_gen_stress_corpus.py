"""Generate ultra-complex stress corpus (50 packages) for arafix 0.9.3."""
from __future__ import annotations

import json
from pathlib import Path

# Helpers for known visual/mojibake forms
MOJ_SALAM = "Ø§Ù„Ø³Ù„Ø§Ù…"  # السلام
MOJ_ALM = "Ø§Ù„Ù…"  # الم
MOJ_MUTAWASIT = "Ø§Ù„Ù…ØªÙˆØ³Ø·"  # المتوسط
MOJ_HYBRID = "Ø§Ù„Ù…ÙCustomer"  # الم + orphan Ù + Customer

# Presentation forms: الحمد لله (tatweel) — known FLAW_07
PF_HAMD = "ـﻪـﻠـﻟ ﺪﻤﺤﻟا"
# مرحبا PF
PF_MARHABA = "\ufee3\ufeae\ufea3\ufe92\ufe8e"

cases: list[dict] = []

def add(cid, axis, title, kind, inp, expected=None, must_not_change=False, tags=None, notes=""):
    cases.append({
        "id": cid,
        "axis": axis,
        "title": title,
        "kind": kind,  # repair_text | reverse_visual | safe | perf
        "input": inp,
        "expected": expected if expected is not None else inp,
        "must_not_change": must_not_change,
        "tags": tags or [],
        "notes": notes,
    })

# ═══════════════════════════════════════════════════════════════════════
# Axis 1 — Complex Mojibake & Encoding Interleaving (9)
# ═══════════════════════════════════════════════════════════════════════
add("A1-01", 1, "FLAW_04 hybrid mojibake + English + status",
    "repair_text",
    f"{MOJ_HYBRID} Report for project_v2.py (Status: 200 OK) - دراسة مقارنة",
    "المCustomer Report for project_v2.py (Status: 200 OK) - دراسة مقارنة",
    tags=["mojibake", "hybrid"])

add("A1-02", 1, "Pure classic mojibake word",
    "repair_text", MOJ_SALAM, "السلام", tags=["mojibake"])

add("A1-03", 1, "Arabic healthy + mojibake island + Arabic",
    "repair_text",
    f"دراسة {MOJ_MUTAWASIT} مقارنة في البحث",
    "دراسة المتوسط مقارنة في البحث",
    tags=["mojibake", "hybrid"])

add("A1-04", 1, "English prefix then mojibake",
    "repair_text",
    f"Customer Report {MOJ_ALM}",
    "Customer Report الم",
    tags=["mojibake"])

add("A1-05", 1, "Code path + mojibake + OK status",
    "repair_text",
    f"ERROR: {MOJ_SALAM} at line 42 in app.py [OK]",
    "ERROR: السلام at line 42 in app.py [OK]",
    tags=["mojibake", "code"])

add("A1-06", 1, "JSON-like keys with mojibake value fragment",
    "repair_text",
    f'{{"title": "{MOJ_ALM}", "code": 200}}',
    '{"title": "الم", "code": 200}',
    tags=["mojibake", "json"])

add("A1-07", 1, "CP1256 misread full Arabic phrase",
    "repair_text",
    "مرحبا بالعالم".encode("cp1256").decode("latin-1"),
    "مرحبا بالعالم",
    tags=["cp1256", "legacy"])

add("A1-08", 1, "Mojibake then URL and digits untouched",
    "repair_text",
    f"{MOJ_SALAM} https://example.com/v2?id=99",
    "السلام https://example.com/v2?id=99",
    tags=["mojibake", "url"])

add("A1-09", 1, "Hybrid FLAW_04 style inside longer academic line",
    "repair_text",
    f"الملخص: {MOJ_HYBRID} Report (Status: 200 OK) — نتائج الدراسة",
    "الملخص: المCustomer Report (Status: 200 OK) — نتائج الدراسة",
    tags=["mojibake", "hybrid"])

# ═══════════════════════════════════════════════════════════════════════
# Axis 2 — BiDi, page ranges, currencies (9)
# ═══════════════════════════════════════════════════════════════════════
add("A2-01", 2, "Page range visual geometric",
    "reverse_visual",
    "(140-125 .ص) ثحبلا عجرم",
    "مرجع البحث (ص. 125-140)",
    tags=["page-range", "bidi"])

add("A2-02", 2, "Currency accounting visual",
    "reverse_visual",
    ")00.052,1 DSU-( يفاصلا",
    "الصافي (-USD 1,250.00)",
    tags=["currency", "bidi"])

add("A2-03", 2, "Year LTR protection",
    "reverse_visual",
    "2024 ماع",
    "عام 2024",
    tags=["year", "bidi"])

add("A2-04", 2, "Percent edge",
    "reverse_visual",
    "3.5% ماع",
    "عام 3.5%",
    tags=["percent", "bidi"])

add("A2-05", 2, "Date island 13-7",
    "reverse_visual",
    "13-7 ماع",
    "عام 13-7",
    tags=["date", "bidi"])

add("A2-06", 2, "Ship name LTR multi-token",
    "reverse_visual",
    "M/V Ever ماع",
    "عام M/V Ever",
    tags=["ltr-island", "bidi"])

add("A2-07", 2, "Arabic brackets visual",
    "reverse_visual",
    "(ةمدقم)",
    "(مقدمة)",
    tags=["brackets", "bidi"])

add("A2-08", 2, "Dollar amount LTR",
    "reverse_visual",
    "$100 ماع",
    "عام $100",
    tags=["currency", "bidi"])

add("A2-09", 2, "Page range pp. normalize via reverse path",
    "reverse_visual",
    # visual of: انظر pp. 10-40 — use already post-mirror style by feeding
    # descending after a synthetic reverse scenario: normalize helper path
    # Use input that reverse_visual produces then we check expected includes ascending
    "(40-10 .ص) رظنأ",
    "أنظر (ص. 10-40)",
    tags=["page-range"])

# ═══════════════════════════════════════════════════════════════════════
# Axis 3 — Diacritics, PF, tatweel, lexicon (8)
# ═══════════════════════════════════════════════════════════════════════
add("A3-01", 3, "PF tatweel الحمد لله",
    "repair_text", PF_HAMD, "الحمد لله", tags=["pf", "tatweel"])

add("A3-02", 3, "PF مرحبا",
    "repair_text", PF_MARHABA, "مرحبا", tags=["pf"])

add("A3-03", 3, "Ambiguous lam-alef via core lexicon",
    "repair_text", "صدرت المجالت العلمية", "صدرت المجلات العلمية",
    tags=["lam-alef", "lexicon"])

add("A3-04", 3, "Decisive lam-alef double alef",
    "repair_text", "االنترنيت في البحث", "الانترنيت في البحث",
    tags=["lam-alef"])

add("A3-05", 3, "Vocalized healthy Arabic must stay",
    "repair_text",
    "صَدَرَتِ الدِّرَاسَةُ الْعِلْمِيَّةُ عَامَ 2024",
    "صَدَرَتِ الدِّرَاسَةُ الْعِلْمِيَّةُ عَامَ 2024",
    must_not_change=True,
    tags=["tashkeel", "safe"])

add("A3-06", 3, "Lam-alef ambiguous + year + path",
    "repair_text",
    "صدرت المجالت العلمية بتاريخ 2024/05/01",
    "صدرت المجلات العلمية بتاريخ 2024/05/01",
    tags=["lam-alef", "date"])

add("A3-07", 3, "PF phrase with Latin year after repair",
    "repair_text",
    f"{PF_MARHABA} 2024",
    "مرحبا 2024",
    tags=["pf", "year"])

add("A3-08", 3, "Decisive + ambiguous mixed sentence",
    "repair_text",
    "األطاريح و المجالت في الجامعة",
    "الأطاريح و المجلات في الجامعة",
    tags=["lam-alef"])

# ═══════════════════════════════════════════════════════════════════════
# Axis 4 — False-positive safeguards (12) — ZERO changes allowed
# ═══════════════════════════════════════════════════════════════════════
safe_samples = [
    (
        "A4-01",
        "Python function café",
        'def process_data(user_id="usr_99", format="json"): '
        'return {"status": "café", "rate": "15%"} # لا تمسني!',
    ),
    ("A4-02", "Latin accents set",
     "café résumé naïve über Österreich"),
    ("A4-03", "JSON config",
     '{"status": "ok", "path": "C:\\\\Users\\\\data", "rate": 0.15}'),
    ("A4-04", "HTML snippet",
     '<div class="card" dir="rtl">Hello <b>world</b> &amp; friends</div>'),
    ("A4-05", "Math-like expression",
     "E = m*c**2 ; sigma = sum(x_i)/n for i in range(N)"),
    ("A4-06", "Healthy Arabic prose",
     "هذه دراسة مقارنة في السياسة العامة ولا تحتاج أي إصلاح."),
    ("A4-07", "Mixed healthy AR+EN",
     "The paper بعنوان دراسة مقارنة was published in 2024."),
    ("A4-08", "SQL fragment",
     "SELECT id, name FROM users WHERE status = 'active' AND rate > 0.5;"),
    ("A4-09", "Shell/path",
     "export PATH=/usr/local/bin:$PATH && python3 app.py --env=prod"),
    ("A4-10", "Regex pattern string",
     r"pattern = r'^[A-Za-z0-9_\-]+@example\.com$'  # email"),
    ("A4-11", "Version and semver",
     "arafix==0.9.3 ; npm i lodash@4.17.21 ; v1.0.0-rc.1"),
    ("A4-12", "French/German snippet",
     "Le résumé de la naïveté über die Größe des Cafés."),
]
for cid, title, text in safe_samples:
    add(cid, 4, title, "safe", text, text, must_not_change=True, tags=["safe", "fpr"])

# ═══════════════════════════════════════════════════════════════════════
# Axis 5 — Punctuation & parentheses (8)
# ═══════════════════════════════════════════════════════════════════════
add("A5-01", 5, "Leading year period after reverse",
    "reverse_visual",
    ".2024 ماع يف متي :ًلاوا",
    "اوالً: يتم في عام 2024.",
    tags=["punct", "year"])

add("A5-02", 5, "Inverted currency parens repair",
    "reverse_visual",
    ")00.052,1 DSU-( يفاصلا",
    "الصافي (-USD 1,250.00)",
    tags=["parens", "currency"])

add("A5-03", 5, "Healthy question mark Arabic",
    "repair_text",
    "هل هذا صحيح؟ نعم، الأمر واضح.",
    "هل هذا صحيح؟ نعم، الأمر واضح.",
    must_not_change=True,
    tags=["punct", "safe"])

add("A5-04", 5, "English brackets healthy",
    "repair_text",
    "See figure [1-A] and table (2) for details.",
    "See figure [1-A] and table (2) for details.",
    must_not_change=True,
    tags=["punct", "safe"])

add("A5-05", 5, "Nested Arabic brackets visual",
    "reverse_visual",
    "[(ةمدقم)]",
    "[(مقدمة)]",
    tags=["brackets"])

add("A5-06", 5, "relocate helper year after Arabic word",
    "repair_text",
    # already logical; relocate only runs inside reverse_visual — so use reverse
    "دراسة مقارنة",
    "دراسة مقارنة",
    must_not_change=True,
    tags=["safe"])

add("A5-07", 5, "Visual mixed question line",
    "reverse_visual",
    # visual reverse of: عام 2024؟
    "؟4202 ماع",
    # smart LTR may yield 2024
    "عام 2024؟",
    tags=["punct", "year"])

add("A5-08", 5, "Percent and range healthy logical",
    "repair_text",
    "النسبة 3.5% بين 500.00 و 750.00 دينار.",
    "النسبة 3.5% بين 500.00 و 750.00 دينار.",
    must_not_change=True,
    tags=["percent", "safe"])

# ═══════════════════════════════════════════════════════════════════════
# Axis 6 — Performance (4 packages; measured separately)
# ═══════════════════════════════════════════════════════════════════════
# Line templates mixed for throughput
line_templates = [
    "هذه جملة عربية سليمة للاختبار رقم {i} في 2024.",
    'def f_{i}(x): return x + {i}  # café',
    "{MOJ} line {i} status OK".replace("{MOJ}", MOJ_ALM),
    "صدرت المجالت العلمية رقم {i}",
    "JSON {{\"id\": {i}, \"ok\": true}}",
]
# Build large blocks as inputs; expected for perf is N/A for exact match on whole block
# We still define small unit expected patterns via kind=perf

perf_block_small = "\n".join(
    line_templates[i % len(line_templates)].format(i=i) for i in range(100)
)
perf_block_med = "\n".join(
    line_templates[i % len(line_templates)].format(i=i) for i in range(1000)
)
# 10000 lines for ultra stress
perf_block_large = "\n".join(
    line_templates[i % len(line_templates)].format(i=i) for i in range(10000)
)
# Pure safe 5000 lines for FPR-on-volume
perf_safe = "\n".join(
    f'row_{i} = {{"status": "café", "n": {i}}}' for i in range(2000)
)

add("A6-01", 6, "Perf 100 hybrid lines",
    "perf", perf_block_small, notes="throughput", tags=["perf"])
add("A6-02", 6, "Perf 1000 hybrid lines",
    "perf", perf_block_med, notes="throughput", tags=["perf"])
add("A6-03", 6, "Perf 10000 hybrid lines",
    "perf", perf_block_large, notes="throughput-ultra", tags=["perf"])
add("A6-04", 6, "Perf 2000 pure-safe lines FPR volume",
    "perf_safe", perf_safe, expected=perf_safe, must_not_change=True,
    notes="volume-fpr", tags=["perf", "fpr", "safe"])

assert len(cases) == 50, len(cases)

out = {
    "version": 1,
    "target_library": "arafix",
    "target_version": "0.9.3",
    "description": "Ultra-Complex Stress Corpus — 50 packages / 6 axes",
    "axes": {
        "1": "Complex Mojibake & Encoding Interleaving",
        "2": "BiDi, Page Ranges & Currencies",
        "3": "Diacritics, Presentation Forms & Tatweel",
        "4": "False-Positive Safe Guards",
        "5": "Punctuation & Parentheses Isolation",
        "6": "Performance & Latency Benchmark",
    },
    "cases": cases,
}
path = Path("tests/fixtures/stress/ultra_complex_corpus.json")
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", path, "cases", len(cases))
print("by axis", {a: sum(1 for c in cases if c["axis"]==a) for a in range(1,7)})
