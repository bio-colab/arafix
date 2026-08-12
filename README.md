# arafix

[![PyPI version](https://img.shields.io/pypi/v/arafix.svg)](https://pypi.org/project/arafix/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/arafix.svg)](https://pypi.org/project/arafix/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Status: Stable](https://img.shields.io/badge/status-stable-brightgreen)
![Typing](https://img.shields.io/badge/typing-py.typed-blue)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21733978.svg)](https://doi.org/10.5281/zenodo.21733978)

**Recover broken Arabic text from PDFs** — diagnose first, then apply a graded repair ladder. Not a single hammer, and not “just run OCR.”

| | |
|---|---|
| **Core** | Zero dependencies (stdlib only) for text stages 0–2 |
| **PDF** | `pip install "arafix[pdf]"` — geometric extract + Arabic repair |
| **Layout** | Multi-column RTL, headers/footers, simple tables (`layout=auto`) |
| **1.0.1** | Glyph word-spacing + closed PDF confusions from **published Arabic books** (not AI fixtures) |
| **1.0** | Core lexicon, smart BiDi/LTR, hybrid mojibake, stress-gated (FPR=0, RAR=100%) |
| **Quality** | Cluster-aware diacritics, PDF homoglyph fold, scientific metrics (MCS/DBR/BFE/SHDR) |
| **Hardening** | Conservative embedded-font CMap fallback, geometric-noise filtering, and solid-block Latin/Bidi protection |
| **Spacing** | Explicit PDF-space preservation and context-aware Arabic punctuation spacing |
| **Eval** | Independent Safahat book samples + manual gold, plus a 1,000-case adversarial Bidi corpus (`benchmarks/`) |
| **Status** | **Stable 1.0.1** — production-ready for native Arabic PDF recovery |

### Install

```bash
pip install arafix              # text repair only
pip install "arafix[pdf]"       # recommended — PDF extract
pip install "arafix[all]"       # + fonttools (CMap / stage 3)
pip install "arafix[markitdown]"  # MarkItDown plugin
```

> **Dependency guarantee:** the core package declares no runtime dependencies. PDF, CMap, and MarkItDown support remain opt-in extras; the hardening and spacing improvements listed below do not add Torch, Transformers, OCR, or any other mandatory dependency.

### 30-second start

```python
from arafix import repair_text, extract_pdf, PipelineConfig

# Presentation-form garbage → readable Arabic
print(repair_text("\ufee3\ufeae\ufea3\ufe92\ufe8e").text)  # مرحبا

# Ambiguous lam-alef via embedded core lexicon
print(repair_text("صدرت المجالت العلمية").text)  # صدرت المجلات العلمية

# Hybrid mojibake (windowed) — Latin/code left intact
print(repair_text("Ø§Ù„Ù…ÙCustomer Report (Status: 200 OK)").text)
# → المCustomer Report (Status: 200 OK)

# Native (not scanned) Arabic PDF
doc = extract_pdf("thesis.pdf")
print(doc.text)
print(doc.confidence, doc.pages[0].n_columns)
```

```python
from arafix import reverse_visual_line, ReorderConfig

# Smart LTR: page ranges, currency parens, sentence period
print(reverse_visual_line("(140-125 .ص) ثحبلا عجرم"))
# → مرجع البحث (ص. 125-140)

print(reverse_visual_line(")00.052,1 DSU-( يفاصلا"))
# → الصافي (-USD 1,250.00)
```

```bash
arafix diagnose thesis.pdf -v
arafix extract  thesis.pdf -o out.txt
arafix extract  paper.pdf --layout full -v --tables
arafix eval     thesis.pdf --truth thesis.txt --scientific
python scripts/eval_unified.py --pdf thesis.pdf --truth thesis.txt -v
python scripts/stress_test_report.py --skip-ultra
```

### Verified improvements in `main`

The current `main` branch includes the following measured improvements. Detailed methodology, limitations, and rollback decisions are recorded in [CHANGELOG.md](CHANGELOG.md).

| Area | What is shipped | Evidence |
|---|---|---|
| Embedded-font recovery | Conservative `glyph_id → Unicode` CMap fallback for PUA and `U+FFFD` only when font and glyph evidence agree | Avoids broad text substitutions and preserves ambiguous mappings |
| Arabic spacing | Explicit PDF spaces take precedence over geometric gaps; punctuation spacing is context-aware and leaves Latin and decimal contexts alone | Constitution CER/WER improved from **3.486% / 20.939%** to **3.092% / 17.208%** |
| Latin/Bidi islands | Solid-block protection for dates, versions, phone numbers, email, hybrid terms, and page ranges | **1000/1000** adversarial cases pass: dates, versions, hybrid terms, and phones |
| Geometric noise | Conservative light-gray rotated watermark filtering from text-trace metadata | Three watermark spans removed while table count stayed 3/3; repeated multi-page filtering remains opt-in |
| Hot-path work | Batch joining of glyph tokens and removal of redundant diagnosis work | 2000-page extraction improved by **3.35%** with byte-for-byte output identity |

No speculative layout cache is shipped: its measured profiler result was slower than the uncached path. No C/Rust extension or OCR dependency was added because the measured evidence did not justify either.

### What it fixes (and what it doesn’t)

| Symptom | Cause | Stage / tool |
|---|---|---|
| Reversed letter order | Visual storage order | 2 + smart LTR |
| Isolated Arabic glyphs (`ﻣﺮﺣﺒﺎ`) | Presentation forms | 1 |
| `Ø§Ù„…` / hybrid mojibake | UTF-8 (or CP1256) misread | 0 windowed |
| `المجالت` / `االنترنيت` | Lam-alef broken before reorder | 1a→2→1b + core lexicon |
| `(ص. 140-125)` page ranges | LTR island + academic order | `normalize_page_ranges` |
| `(-USD 1,250.00)` / `3.5%` | Accounting / percent islands | smart LTR + paren repair |
| `.2024` sentence glue | Period stuck to year island | `relocate_sentence_punctuation` |
| `()مقدمة` | Engine bidi vs neutrals | geometric extract |
| Misplaced harakat / `َحرب` | Mn glued to wrong base | extract + clusters |
| `ی`/`ھ` vs `ي`/`ه` | PDF ToUnicode lookalikes | `fold_pdf_homoglyphs` |
| Two columns mixed | Line-joined gutters | layout (0.8+) |
| Empty / PUA soup | Broken ToUnicode / scan | 3 / 4 (OCR not shipped) |

### Configuration highlights (1.0)

```python
from arafix import PipelineConfig, NormalizeConfig, ReorderConfig, repair_text

cfg = PipelineConfig(
    use_core_lexicon=True,          # embedded micro-lexicon for ambiguous لا/ال
    enable_lam_alef_repair=True,
    normalize=NormalizeConfig(
        strip_tatweel_in_pf_runs=True,
        fold_pdf_homoglyphs=True,   # set False for intentional Farsi Yeh
    ),
    reorder=ReorderConfig(
        smart_ltr_restore=True,
        normalize_page_ranges=True,
        repair_ltr_parens=True,
        relocate_sentence_punct=True,
    ),
)
repair_text(broken, cfg)
```

**Philosophy:** never invent characters; never “fix just in case”; every decision carries evidence and confidence. Release gated by **FPR = 0** and **RAR ≥ 98%** on the 50-pack stress corpus.

Further reading: [INTEGRATING.md](INTEGRATING.md) · [DEPLOY.md](DEPLOY.md) · [CHANGELOG.md](CHANGELOG.md) · [RELEASING.md](RELEASING.md) · [CITATION.cff](CITATION.cff) · [PR #3](https://github.com/bio-colab/arafix/pull/3) · [PR #5](https://github.com/bio-colab/arafix/pull/5) · [PR #7](https://github.com/bio-colab/arafix/pull/7)



---

<div dir="rtl">

# arafix — التوثيق العربي

**استرجاع النص العربي من ملفات PDF المعطوبة.**
سلّمٌ من خمس درجات، لا مطرقةٌ واحدة.

---

## المسألة

عندك ملف PDF عربي أصليّ — لا صورة ممسوحة، بل نصٌّ حقيقيّ مُصدَّر من Word.
تفتحه فتقرؤه بلا عناء. تستخرجه ببايثون فيخرج:

| ما ترى | العلّة | الدرجة العلاجية |
|---|---|---|
| `ا ب ح ر م` | ترتيب بصريّ مخزَّن معكوساً | ٢ |
| `م ر ح ب ا` متفرقة | أشكال رسومية مطبوخة (U+FB50–FEFF) | ١ |
| `Ø§Ù„Ù…ØªÙˆØ³Ø·` | موجيبيك — **علّة أنبوبك لا علّة الملف** | ٠ |
| `المجالت` بدل `المجلات` | رباط «ﻻ» فُكّ قبل إصلاح الاتجاه | ١أ+٢+١ب |
| `()مقدمة` بدل `(مقدمة)` | بِدي المحرّك يبعثر المحايدات | القراءة الهندسية |
| `نشُرت` بدل `نُشرت` | العَكس على المحارف لا على العناقيد | ٢ |
| `` أو `?????` | خريطة ToUnicode تالفة | ٣ |
| لا شيء | لا طبقة نصية (ممسوح ضوئياً) | ٤ |

**العلل خمس، والعلاجات خمسة، ولكلٍّ دواؤه.** أكثر ما يُتداول من حلول
يخلط بينها، فيطبّق دواء الثانية على الرابعة، ثم يستنتج أن «العربية
مستحيلة في PDF».

### تصحيحان لخرافتين شائعتين

> ❌ «الـ OCR هو الحل الأسرع والأدق للعربية.»

خطأ. OCR العربي **آخر الدواء لا أوّله**: أبطأ بمراتب، ويخطئ في الهمزة
والتشكيل والأرقام، ويهدم بنية الجداول. لا تنزل إليه إلا حين تنعدم طبقة
النص أصلاً (الدرجة ٤). ما دون ذلك يُحلّ بسطرٍ إلى عشرين.

> ❌ «الرباط ﻻ حرفان مثل ﬁ في اللاتينية.»

خطأ، والفرق ليس تفصيلاً. رباط لام-ألف في العربية **إلزاميّ** لا اختياريّ:
لا يوجد خطٌّ يرسم لاماً ثم ألفاً منفصلتين. فهو في ملف الـ PDF **جليفٌ
واحد**. ومن فكّه إلى حرفين ثم عكس السطر، عكس الحرفين معه فصارت «لا» ←
«ال». وهذا مصدر أشهر عطبٍ في استخراج العربية:

```
الانترنيت → االنترنيت     المجلات → المجالت
الأطاريح  → األطاريح      الإجراء → اإلجراء
```

> ❌ «المشكلة في الحروف؛ فإن خرجت العربية سليمةً فقد نجوت.»

خطأ، وهو أخبث ما في الباب. **الحروف أمتنُ ما في السطر، والترقيم أهشُّه.**
المحايدات (`( ) [ ] . ! ,`) لا اتجاه لها في يونيكود، فيتنازعها ما حولها،
فتُخرج المحرّكاتُ عربيةً سليمةً وترقيماً مبعثراً:

```
(مقدمة الدراسة)   →  ()مقدمة الدراسة
الفقرة [أ-ج] هنا  →  ج[ هنا-الفقرة ]أ
```

ولاحظ أن `؟` و`؛` تنجوان دائماً حيث تعطب `!` و`.` — لأنهما **عربيّتان**
(صنف `AL` قويّ الاتجاه) لا محايدتين. من لا يقرأ العربية لا يرى العطب أصلاً.

> ❌ «`Ø§Ù„Ù…` يعني أن الـ CMap تالف.»

خطأ. هذا موجيبيك: بايتات UTF-8 فُكّت بـ Latin-1. الملف سليم، والعطب في
**كودك أنت**. علاجه `.encode('latin-1').decode('utf-8')`. أما الـ CMap
التالف فعلامته رموز PUA (`U+E000–F8FF`) أو خانات فارغة، وعلاجه شيء آخر
تماماً (الدرجة ٣).

---

## التثبيت

</div>

```bash
# النواة (الدرجات ٠–٢): بلا أيّ تبعيّة — بايثون قياسيّ خالص
pip install arafix

# مع دعم PDF (مستحسن)
pip install "arafix[pdf]"

# كل شيء بما فيه الدرجة ٣
pip install "arafix[all]"

# جسر MarkItDown (إضافة PDF عربية + post-process)
pip install "arafix[markitdown]"

# من المصدر
git clone https://github.com/bio-colab/arafix
cd arafix && pip install -e ".[dev]" && pytest
```

<div dir="rtl">

الـ sdist يحمل الاختبارات والأمثلة عمداً: مَن حمّل المصدر يجب أن يستطيع
تشغيل `pytest` عليه فيتحقق بنفسه، لا أن يصدّق شهادتنا. وللنشر انظر
[RELEASING.md](RELEASING.md).

</div>

<div dir="rtl">

قرارٌ مقصود: **النواة بلا تبعيّات**. الدرجات ٠–٢ تعمل في أيّ بيئة —
Colab مقيّد، خادم بلا إنترنت، Lambda. التبعيّات كلها اختيارية.

في `main` الحالية أضيف استرداد CMap محافظ من الخطوط المضمّنة، وحماية
للجزر اللاتينية مثل التواريخ والإصدارات وأرقام الهواتف، وفلتر هندسي محافظ
للعلامات المائية، وقواعد سياقية للفراغات حول الترقيم العربي. لم تُضف تبعية
إجبارية أو OCR، ولم يُعتمد cache للتخطيط لأن القياس أثبت أنه أبطأ.

---

## جرّبها الآن (٣٠ ثانية، بلا ملفٍّ منك)

</div>

```bash
# ١) ولّد ملفاً معطوباً عمداً — يحاكي مُصدِّراً رديئاً حقيقياً
python examples/make_broken_pdf.py broken.pdf

# ٢) شخّص. لاحظ: هذا الأمر لا يكتب شيئاً، يريك فقط
arafix diagnose broken.pdf -v

# ٣) عالِج
arafix extract broken.pdf
```

<div dir="rtl">

المخرَج قبل وبعد:

</div>

```
─ ما تراه أدوات بايثون:
ﺩﺭﺍﺳﺔ ﻤﻘﺎﺭﻧﺔ ﻔﻲ ﺎﻟﺴﻴﺎﺳﺔ ﺎﻟﻌﺎﻣﺔ
 ﻔﻲ ﻤﺠﻠﺔ ﻤﺤﻜﻤﺔ2024 ﻧﹹﺸﺮﺕ ﻬﺬﻩ ﺎﻟﺪﺭﺍﺳﺔ ﻌﺎﻡ

─ بعد arafix:
دراسة مقارنة في السياسة العامة
 في مجلة محكمة2024 نُشرت هذه الدراسة عام
```

<div dir="rtl">

---

## الاستعمال

### نصّاً

</div>

```python
from arafix import repair_text

r = repair_text(broken_text)

r.text                          # النص بعد العلاج
r.diagnosis.summary()           # 'presentation_forms، visual_order'
r.confidence                    # 0.94
[s.value for s in r.stages_applied]   # ['hygiene', 'diagnose', 'normalize', 'reorder']
r.notes                         # لماذا فُعل كل شيء
```

<div dir="rtl">

### كتلًا / جدولاً (كل خلية مستقلة)

</div>

```python
from arafix import repair_blocks, fix_table, TextBlock

fix_table([["خلية معطوبة", "سليمة"], ["…", "…"]])

out = repair_blocks([
    TextBlock(cell, id=f"r{i}c{j}", role="cell")
    for i, row in enumerate(grid)
    for j, cell in enumerate(row)
])
out.by_id()["r0c1"].text
```

<div dir="rtl">

### بعد MarkItDown أو أيّ مستخرج

انظر [INTEGRATING.md](INTEGRATING.md).

</div>

```python
from arafix import fix_markitdown, fix_any
from markitdown import MarkItDown  # اختياري

fixed = fix_markitdown(MarkItDown().convert("thesis.pdf"))
# أو: fix_any(open("paste.txt", encoding="utf-8").read())
```

<div dir="rtl">

### ملفاً

</div>

```python
from arafix import extract_pdf

doc = extract_pdf("thesis.pdf")
print(doc.text)
print(doc.confidence)           # أدنى ثقة عبر الصفحات

for page in doc.pages:          # كل صفحة تُشخَّص وحدها — عمداً
    if page.repair.confidence < 0.7:
        print(page.page_number, page.repair.diagnosis.summary())
```

<div dir="rtl">

### التشخيص وحده (بلا علاج)

</div>

```python
from arafix import diagnose

d = diagnose(text)
d.defects                                    # [PRESENTATION_FORMS, VISUAL_ORDER]
d.confidence_in(Defect.PRESENTATION_FORMS)   # 1.0   ← شاهدٌ قاطع
d.confidence_in(Defect.VISUAL_ORDER)         # 0.93  ← شاهدٌ ظنّيّ
d.confidence                                 # 0.93  ← أضعف حلقة
for e in d.evidence:
    print(e)     # final_only_letters=+0.940 :: ة/ى في أول 47 كلمة مقابل آخر 3
```

<div dir="rtl">

**ولاحظ أن الثقة مفصولة لكل علّة.** الرقم الواحد يُخفي أن بعض شواهدنا
قاطعة وبعضها ظنّيّ، فيظلم الأولى ويجمّل الثانية:

| نوع الشاهد | الثقة | لماذا |
|---|---|---|
| قاطع (نطاقٌ أو اختبارٌ جبريّ) | **١٫٠ دائماً** | فحصُ نطاقٍ على ٥ محارف قاطعٌ كفحصه على ٥٠٠٠. حجمُ العيّنة لا دخل له. |
| ظنّيّ (الاتجاه) | بدرجة شاهده | |
| «سليم» — شهادةُ نفي | ٠٫٣ ← ٠٫٩ بحجم العيّنة | وحدَها يحكمها الحجم، إذ هي استدلالٌ بغياب الدليل. **وسقفُها ٠٫٩ عمداً: غيابُ العلّة ليس برهانَ سلامة.** |

**لاحظ الشواهد.** الفرق بين أداةٍ تقول «النص معكوس» وأداةٍ تقول «معكوس
لأن ٩٤٪ من التاءات المربوطة وقعت أوّل الكلمة» هو الفرق بين أداةٍ تُصدَّق
وأداةٍ تُستعمل على عمى.

### الضبط

</div>

```python
from arafix import PipelineConfig, NormalizeConfig, repair_text

cfg = PipelineConfig(
    normalize=NormalizeConfig(
        strip_diacritics=False,   # افتراضيّ: الاسترجاع لا التعديل
        unify_alef=True,          # للبحث والفهرسة فقط
    ),
    thresholds={"visual_order": 0.45},   # عتبة أشدّ
    force_reorder=False,
)
r = repair_text(text, cfg)
```

<div dir="rtl">

### ترقيع نصٍّ أعطبته أداةٌ أخرى

إن كان نصّك مُستخرَجاً بأداةٍ غير هذه وفيه `المجالت` و`االنترنيت`:

</div>

```python
from arafix import repair_lam_alef_transposition

r = repair_lam_alef_transposition("االنترنيت والمجالت")
r.text              # 'الانترنيت والمجالت'  ← القاطع أُصلح
r.fixed_decisive    # 1
r.suspects_left     # 1
r.suspect_words     # ['المجالت'] ← مُبلَّغٌ عنه، غير مُخمَّن

# ومع معجم، يُحسم المُبهَم أيضاً:
repair_lam_alef_transposition("المجالت", lexicon=my_words).text   # 'المجلات'
```

<div dir="rtl">

يمرّ هذا تلقائياً داخل `repair_text` / `extract_pdf`؛ ومرِّر
`PipelineConfig(lexicon=...)` لتزويده بالمعجم.

---

## المعمار

</div>

```
النص الخام  ◄── extractors/: القراءة الهندسية من تيار الرسم لا من بِدي المحرّك
    │
    ├─ ٠ diagnose.py   ◄── لا تعالج قبل أن تعرف. لا يكتب شيئاً.
    │      ├── detect_mojibake            اختبار جبريّ قاطع
    │      ├── detect_presentation_forms  عدّ نطاقيّ
    │      ├── detect_pua                 عدّ نطاقيّ
    │      └── detect_visual_order        ٣ شواهد لغوية، تصويت مرجَّح
    │
    ├─ ١أ normalize.py ◄── المفردات وحدها. ما يغيّر العنقود يُؤجَّل.
    ├─ ٢ order.py      ◄── بصريّ ← منطقيّ، بحماية الأرقام واللاتينية
    ├─ ١ب normalize.py ◄── الرباطات والتشكيل الفاصل — بعد استقرار الترتيب
    ├─ ⚕ lamalef.py    ◄── ترقيع عطبٍ وَرِثناه من أداةٍ أخرى
    ├─ ٣ cmap.py       ◄── إعادة بناء الخريطة من الخط المضمَّن
    └─ ٤ OCR           ◄── آخر الدواء (لم يُنفَّذ بعد)
```

<div dir="rtl">

### القرارات المعمارية، ولماذا اتُّخذت

**١. كل جدول يونيكود مُولَّد، لا مكتوب بيد.**
٧٣١ مدخلةً مشتقّةً من `unicodedata` — لا خطأ مطبعياً ممكناً، وتتحدّث مع
نسخة يونيكود تلقائياً. الاستثناءات وحدها يدوية، وكلٌّ منها مُبرَّرٌ في
تعليقٍ إلى جانبه.

**٢. تطبيعٌ مُوجَّه لا `NFKC`.**
`NFKC` يحلّ المشكلة ويحلّ معها عشرين لم تطلبها: يقلب `R²` إلى `R2`،
و`ﬁle` إلى `file`، و`①` إلى `1`. في بحثٍ أكاديميّ فيه رموز رياضية، هذا
تخريبٌ صامت. فنحن نطبّع نطاق الأشكال العربية وحده.

**٣. لا مرحلة تُرجع نصاً عارياً.**
كلٌّ تُرجع كائناً يحمل النص ومعه سببَ ما فعلت ودرجةَ ثقتها. القرار
للمستعمل، والمكتبة قابلة للتدقيق.

**٤. لا درجةَ تُطبَّق بلا شاهد.**
المكتبة **لا تعالج «احتياطاً»**. عكسُ نصٍّ سليمٍ تخريبٌ بأيدينا. وأهمّ
اختبارٍ في الحزمة اسمه `test_does_not_touch_healthy_text`.

**٥. التطبيع مُشطَّرٌ حول الاتجاه: ١أ ← ٢ ← ١ب.**
هذا القرار كُتب أوّلاً «التطبيع قبل الاتجاه»، وكان نصفَ صواب. فالتطبيع
الكامل قبل الاتجاه يفكّ «ﻻ» إلى حرفين، ثم يعكسهما العكسُ إلى «ال». فصار:
تُطبَّع المفردات (فتنكشف التاء المربوطة لكاشف الاتجاه)، **ويبقى الرباط
ذرّةً**، ثم يُعكس، ثم يُفكّ الرباط. الدرجة ١ تفتح عين الدرجة ٢ **ولا
تسلّمها سكيناً**.

**٥ب. معيارُ التأجيل تغيُّرُ بنية العنقود، لا طولُ التفكيك.**
يُؤجَّل صنفان: الرباطات (محرفٌ يصير محرفين)، وأشكال التشكيل الفاصلة
`U+FE70–FE7F` (محرفٌ فئتُه `Lo` يصير علامةً لاصقة `Mn`). كلاهما يغيّر
وحدةَ العكس، فتطبيعُهما المبكر يهدم ما بعده. ومعيارُ الطول وحده يُعمي عن
الثاني: تفكيك `U+FE79` هو [كشيدة + ضمّة]، ونحن نطرح الكشيدة فيعود الطول
واحداً فيبدو بريئاً. فالفئةُ تفضح ما لا يفضحه الطول.

**٥ج. الكاشف يقرأ طبقتين، لأن التطبيع يفقأ عيناً وهو يفتح أخرى.**
التاء المربوطة لا تُرى إلا بعد التطبيع، وصيغُ الوصل لا تُرى إلا قبله.
فيأخذ `detect_visual_order` النصّ المطبَّع **ومعه** الأصل الرسوميّ
(`shaped_source`)، فيشهد كلٌّ من طبقته.

**٥د. هويّة الوصل برهانٌ لا أمارة.**
في العربية: `joins_forward(a) == joins_backward(b)` لكل حرفين متجاورين —
لا تتخلّف أبداً في نصٍّ منطقيّ. فخرقُها **مرّةً واحدة** يُثبت الانعكاس.
شاهدٌ لا تماثليّ: يدحض ولا يُزكّي. (كان الفحص أوّلاً على طرفَي الكلمة
وحدهما، فأفلتت منه كلماتٌ كـ«الإجراء» طرفاها منفصلان.)

**٦. `text[::-1]` خطأ، لا اختصار — لثلاثة أسباب لا سبب.**
(أ) الأرقام واللاتينية LTR في الحالين، فالعكس يفسد `2024` فتصير `4202`
و`GDP_2024` تصير `2024_GDP`. (ب) الأقواس **مِرآتية**: جليفُ أقصى اليسار
في سطرٍ عربيّ هو `(` وإن كان المحرف المنطقيّ هناك `)`، فبلا مرآةٍ تخرج
`)مقدمة(`. (ج) **وحدةُ العكس العنقودُ لا المحرف**: التشكيل عرضُه صفر
ويشترك في موضع حرفه، فعكسُ المحارف يُلصقه بالجار (`أولاً` ← `أوًلا`).

**٧. القراءة من تيار الرسم، لا من بِدي المحرّك.**
قياسٌ لا رأي: على ١٢ سطراً فيها ترقيم، أخفق مسار `get_text()` في ٩
وأخفق المسار الهندسيّ في صفر. ونقرأ بـ `get_texttrace` لا `rawdict`،
وهذا **شرط**: `rawdict` يعيد ترتيب محارفه ببِدي MuPDF قبل تسليمها، فيهدم
الربط الذي جئنا نستشهد به.

**٨. ولكلٍّ من ربط العنقود وترتيبه شاهدٌ مختلف — والخلطُ بينهما فخّ.**
*الربط* (أيّ علامةٍ لأيّ حرف؟) **من التيار**: الهندسة تكذب هنا، إذ
العلامة عرضُها صفر فتُرسَم عند القلم بعد أن تجاوز حرفَها، فـ `x` عندها
يساوي `x` للحرف **التالي**. *الترتيب* (أيّ عنقودٍ قبل أيّ؟) **من
الهندسة**: التيار قد يكون بصرياً، و`x` وحده يقول أين وقع كلُّ شيء.

**٩. لا نكتب قارئ PDF.**
كتابته عملُ سنين، وموجودٌ منه ما يكفي. كل محرّك يُغلَّف خلف `Extractor`
واحد، فتبديله سطرٌ وإضافةُ جديدٍ ملفٌّ واحد.

**١٠. `cid1234` لا يُفكّ.**
رقمٌ داخليّ للخط بلا دلالة. من يفكّه يخترع من عنده — وهذا خطٌّ أحمر:
المكتبة تعجز صراحةً ولا تخترع أبداً.

---

## التوسيع

### محرّك استخراج جديد

</div>

```python
from arafix.extractors import Extractor, RawPage, register

@register
class PdfMinerExtractor(Extractor):
    name = "pdfminer"

    @classmethod
    def available(cls) -> bool:
        try:
            import pdfminer; return True
        except ImportError:
            return False

    def pages(self, path):
        from pdfminer.high_level import extract_pages
        ...
        yield RawPage(number=i, text=text)

    def font_bytes(self, path):
        return {}
```

<div dir="rtl">

سطرٌ واحد (`@register`)، ولا يُمسّ شيءٌ آخر في المكتبة. ثم:
`extract_pdf(path, PipelineConfig(extractor="pdfminer"))`.

### كاشف علّة جديد

١. أضف عضواً إلى `Defect` في `types.py`.
٢. اكتب دالةً في `diagnose.py` تُرجع `(score, Evidence)`.
٣. نادها داخل `diagnose()` مع عتبةٍ في `DEFAULT_THRESHOLDS`.
٤. اكتب اختباراً يوثّق **القرار** لا السطر.

### شاهد اتجاه جديد

أضف دالة `_signal_*` تُرجع `(score, detail)` في `[-1, 1]`، وسجّل وزنها في
`_ORDER_WEIGHTS`. التصويت يُعاد تطبيعه على الشواهد الحاضرة وحدها، فغياب
شاهدٍ لا يُميّع النتيجة.

---

## خارطة الطريق

- [x] الدرجة ٠ — التشخيص بشواهد
- [x] الدرجة ١ — التطبيع المُوجَّه
- [x] الدرجة ٢ — الاتجاه بحماية LTR
- [x] الدرجة ٣ — الخريطة من `cmap` وأسماء الجليفات
- [x] الرباطات — تشطير التطبيع حول الاتجاه + ترقيع رجعيّ (0.2.0)
- [x] المحايدات — قراءة هندسية، مرآة الأقواس، عكسٌ عنقوديّ (0.3.0)
- [x] معجم عربيّ مدمج خفيف (`arafix.lexicon.core`) + `use_core_lexicon` (1.0.0)
- [ ] الدرجة ٣+ — مطابقة الشكل (perceptual hash للجليف)
- [ ] الدرجة ٤ — غلاف OCR
- [x] استخراج بنيويّ (جداول، حواشٍ، أعمدة) — layout 0.8.0
- [ ] محرّكات: pdfminer، pypdf، pdftotext
- [x] القياس — CER/WER ومقارنةُ المسارات على ملفك (0.4.0)
- [x] نظافة الاستخراج — NBSP / soft-hyphen (0.7.0)
- [x] `repair_blocks` / جداول — إصلاحٌ مستقلّ لكل خلية (0.7.0)
- [x] معجم الوثيقة الداخليّ يحسم «المجالت» عبر الصفحات (0.7.0)
- [x] جسر MarkItDown — plugin + `fix_markitdown` (0.7.0)
- [x] أعمدة RTL + ترويسة/تذييل + جداول بنيوية (0.8.0)
- [x] حماية التشكيل العنقودية + طيّ هجائن PDF + جزر LTR (0.9.0)
- [x] طبقة علمية MCS/DBR/BFE/SHDR + corpus انحدار حقيقي (0.9.0)
- [x] LTR ذكي: نطاقات صفحات، عملات، ترقيم جملة (0.9.2)
- [x] موجيبيك هجين + CP1256 (0.9.3) + stress corpus 50 (1.0.0)
- [ ] حزمة ملفات مرجعية أوسع (أكثر من corpus واحد)
- [ ] حسمُ «المجالت» بنموذج n-gram على مستوى المحرف (اقتباساً من CAMeL)
- [ ] إخراج PDF قابل للبحث بالنصّ المصحَّح

**الدرجة ٣+ فكرتها:** ارسم كل جليفٍ من الخط المضمَّن، وقارنه بصرياً
بمرجعٍ لكل حرفٍ عربيّ. هذا OCR على مستوى **الجليف** لا الصفحة: مساحة
البحث ٣٦ حرفاً × ٤ أشكال، لا لغةٌ كاملة. أدقّ بمراتب وأسرع.

---

## الاختبارات

</div>

```bash
pytest                      # unit + integration + real-PDF floors
pytest tests/test_scientific_floors.py -v
pytest --doctest-modules src/arafix
ruff check src tests
```

<div dir="rtl">

كل اختبارٍ يوثّق **قراراً** لا سطر كود. فإن كسرته يوماً، عرفت من اسمه
أيّ قرارٍ كسرت ولماذا اتُّخذ أوّلاً. ومن 0.9.0: corpus حقيقي + بوابات
MCS/DBR/BFE/SHDR في `test_scientific_floors`.

---

## حدودٌ مُعلَنة

بصراحةٍ تسبق الاستعمال:

- **الدرجة ٤ (OCR) غير منفَّذة، ولا حزمةَ `arafix[ocr]`.** المكتبة تكشف
  الحاجة وتقولها ولا تدّعي. وكان هناك `extra` باسم `ocr` يجرّ `pytesseract`
  بلا كودٍ يستعمله — وعدٌ بلا سند، فحُذف. لا نبيع تبعيّةً مقابل نيّة.
- **الدرجة ٣ تعجز عن الخطوط CID** ذات الأسماء العديمة الدلالة. تُصرّح
  بالعجز (تغطية منخفضة) ولا تخترع.
- **كاشف الاتجاه احتماليّ** لا حتميّ — ولذلك يُرجع درجةً وشواهد لا حكماً.
- **ترقيع لام-ألف الموروث:** يُصلح القاطع (ألفان متجاورتان) يقيناً. المُبهَم
  (`المجالت`) يُحسَم بمعجم النواة المضمَّن (`use_core_lexicon=True`) أو
  `lexicon=` من المستعمل أو حصاد الوثيقة — بلا تخمين إملائي أعمى. **والوقاية
  من الاستخراج** ما زالت أتمّ: ما تعالجه المكتبة من أوّله يخرج سليماً.
- **الأعمدة والجداول** مدعومة منذ 0.8.0 عبر `layout="auto"|"columns"|"full"`
  (ميزاب أفقي + RTL). الكشف إحصائيّ: صفحات بثلاثة أعمدة متداخلة أو
  جداول بلا فجوات واضحة قد تحتاج ضبط `LayoutConfig`.
- **طيّ الهجائن افتراضيّ** يستهدف العربية الفصحى؛ عطّله للفارسية/الأوردية
  إن احتجتَ الإبقاء على `ی/ھ`.
- **لا نخترع تشكيلاً غائباً من طبقة PDF.** إن رسم الملف شدّةً بلا تنوين،
  لا تُضاف. القياس (`DBR`) يقارن الالتصاق لا اختراع العلامات.
- **Corpus انحدار حقيقي** في `tests/fixtures/real_pdf_narrative/` +
  FLAW fixtures + stress 50-pack (`scripts/stress_test_report.py`).
  `arafix eval --compare --scientific` على ملفاتك يبقى الحجّة الميدانية.

---

## المساهمة

الأنفع بالترتيب: (١) ملفات تكسرها، (٢) محرّكات جديدة، (٣) شواهد اتجاه
أقوى، (٤) الدرجة ٣+.

## Citation / الاستشهاد

If you use `arafix` in academic work, please cite it as:

**APA:**

Sharar, E. (2026). *arafix: Evidence-Based Repair of Broken Arabic Text in Native PDFs* (Version 1.0.1) [Computer software]. https://doi.org/10.5281/zenodo.21733978

**BibTeX:**

```bibtex
@software{sharar_arafix_2026,
  author  = {Sharar, Elias},
  title   = {{arafix: Evidence-Based Repair of Broken Arabic Text in Native PDFs}},
  year    = {2026},
  version = {1.0.1},
  doi     = {10.5281/zenodo.21733978},
  url     = {https://github.com/bio-colab/arafix},
  license = {MIT}
}
```

See [CITATION.cff](./CITATION.cff) for machine-readable citation metadata
(GitHub «Cite this repository», Zotero, EndNote, Zenodo).

## الترخيص

MIT — انظر [LICENSE](LICENSE).

</div>

