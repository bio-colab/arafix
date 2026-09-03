# مرجع مقاييس الجودة في arafix

هذه الصفحة هي المرجع الموحّد لكل مقياس يستخدمه المشروع في الاختبارات والبوابات
والتقارير. كل رقم هنا إما **قابل لإعادة الإنتاج بأمر موثّق** أو **مربوط باختبار
CI** — ولا يوجد مقياس «تسويقي» بلا أداة قياس.

> **القاعدة:** المقاييس موجودة **للقياس لا للتسويق**. كل مقياس أدناه يجيب عن
> عطبٍ يعجز CER وحده عن تمييزه، وكلها بلا تبعيات خارجية (`stdlib` فقط).

- المصدر: `src/arafix/evaluate.py` و`src/arafix/scientific.py`
- البوابات: `tests/test_scientific_floors.py` و`tests/test_regression_real_pdf.py`
  و`tests/test_regression_iraq_constitution.py` و`scripts/stress_test_report.py`
  و`scripts/audit_corpus.py`

---

## 0. الخريطة السريعة

| # | المقياس | الاسم الكامل | ماذا يقيس؟ | الاتجاه | البوابة المثبتة |
|---|---|---|---|---|---|
| 1 | **CER** | Character Error Rate | خطأ المحارف مقابل المرجع | أقل أفضل | سقوف حسب corpus (أدناه) |
| 2 | **WER** | Word Error Rate | خطأ الكلمات مقابل المرجع | أقل أفضل | content WER < 2% (narrative) |
| 3 | **LE** | Normalized Levenshtein Distance | مسافة التحرير مقسومة على طول المرجع | أقل أفضل | ≡ CER بالبناء |
| 4 | **MCS** | Morphological Continuity Score | استمرارية الهيكل الحرفي (المورفولوجيا) | أعلى أفضل | ≥ 0.99 |
| 5 | **DBR** | Diacritic-to-Base Ratio | مخزون التشكيل + دقة التصاقه بالقواعد | أعلى أفضل | ≥ 0.99 (attach ≥ 0.99) |
| 6 | **BFE** | Bidi Flow Entropy | فوضى تدفّق الاتجاهات (R/L/EN/…) | Δref أقل أفضل | Δref ≤ 0.02 |
| 7 | **SHDR** | Semantic Homoglyph Drift Rate | انجراف الهجائن (ی/ھ/ک بدل ي/ه/ك) | أقل أفضل | == 0 |
| 8 | **FPR** | False Positive Rate («False Repair Rate» في الخطة) | إصلاح كاذب لنص سليم | أقل أفضل | == 0 (بوابة صارمة) |
| 9 | **RAR** | Recovery Accuracy Rate | الاسترجاع التام المطابق للحقيقة | أعلى أفضل | ≥ 98% |
| 10 | **BIDI/RTL Order** | ترتيب الاتجاه والقراءة | سلامة ترتيب RTL/LTR والأعمدة | Δref + اجتياز fuzz | H5 fuzz + corpus الألف حالة |

الأدوات التي تُخرج هذه المقاييس:

```bash
# CER / WER / LE + الطبقة العلمية كاملة (MCS/DBR/BFE/SHDR) على PDF مقابل مرجع
python scripts/eval_unified.py --pdf file.pdf --truth gold.txt --scientific -v

# بوابات السلامة والإصدار
python scripts/stress_test_report.py               # التشغيلة الكاملة: safe = 18
python scripts/stress_test_report.py --skip-perf   # safe = 17 (تُستبعد حالات perf)

# تدقيق السلامة والعكس (نطاق repair_text فقط)
python scripts/audit_corpus.py --json-out reports/audit.json

# البوابات العلمية كبوابات CI
pytest tests/test_scientific_floors.py -v

# corpus الاتجاهات الخصمي (1000 حالة)
pytest tests/test_hardening.py -k adversarial -v
```

---

## 1. طبقة الخطأ النصي: CER / WER / LE

### 1.1 التعريف

ثلاثتها تعيش في `src/arafix/evaluate.py` وتُبنى على تنفيذ **ليفنشتاين الدقيق**
(مايرز البِتّي، O(n·⌈m/w⌉)) محكوم بتنفيذٍ مرجعيّ بطيء (`levenshtein_reference` —
مصفوفة كاملة) عبر اختبارات عشوائية. لا تقريبات ولا `rapidfuzz`.

```
rate     = distance / len(reference)      ← EditDistance.rate
accuracy = max(0, 1 − rate)               ← EditDistance.accuracy
```

- **CER**: المسافة على مستوى المحارف (تشمل الحروف، المسافات، الأرقام، والترقيم).
- **CER (حروف فقط `cer_letters_only`)**: المسافة على تيار الحروف العربية الأصيلة فقط، بمعزل تام عن المسافات والترقيم والحركات. هذا المقياس يفصل جودة استرجاع الحروف والربائط عن عيوب التباعد في PDF (ويحقق في `arafix` نسبة خطأ **0.82% فقط**).
- **WER**: المسافة على مستوى الكلمات (بعد `split()`). أقسى من CER وأصدق لهذه
  المكتبة: كلمةٌ انقلب فيها حرفان («المجالت») تكلّف ٢/٧ في CER وتكلّف كلمةً
  كاملة في WER. ودقة الكلمات `word_accuracy = 1 - WER`.
- **LE (Normalized Levenshtein)**: هي *نفس* صيغة CER بالبناء — المسافة نفسها
  والمقام نفسه. عندما تقرأ `report.cer.rate` فأنت تقرأ LE المنطبقة على المحارف،
  وعندما تقرأ `report.cer.accuracy` تقرأ «Levenshtein Similarity» الشائعة في
  الأدبيات. الدالة الخام متاحة أيضاً: `levenshtein(list(a), list(b))`.

### 1.2 ما الذي يُطبَّع قبل القياس؟ (`EvalConfig`)

كل خيار هنا **يُخفي** فرقاً وهو مطفأ إلا `collapse_whitespace` (لا غنى عنه:
تباعد PDF ليس معنى):

| الخيار | الافتراضي | الأثر |
|---|---|---|
| `collapse_whitespace` | `True` | توحيد المسافات المتتالية |
| `ignore_diacritics` | `False` | تجاهل الحركات (يرفع الدرجة كذباً إن كان مرجعك مشكولاً) |
| `ignore_orthographic_variants` | `False` | توحيد صور الألف والتاء المربوطة |
| `ignore_punctuation` | `False` | تجاهل الترقيم — **لا تفعّله لتقييم arafix** |

### 1.3 البوابات وقيم اليوم (v1.0.1+)

على fixtures حقيقية: `tests/fixtures/real_pdf_narrative/` —
(`file.pdf` مقابل `original.txt`، و`iraq_constitution.pdf` مقابل
`iraq_constitution_original.txt`).

| المقياس | رواية حقيقية (`file.pdf`) | البوابة | دستور العراق (`iraq_constitution.pdf`) | البوابة |
|---|---:|---|---:|---|
| CER كامل | **1.35%** | < 3% | **2.13%** | < 5%¹ |
| CER حروف فقط (`cer_letters_only`) | **0.02%** | < 2% | **0.82%** | < 2%¹ |
| WER كامل | **1.55%** | < 3% | **13.24%** | < 16%³ |
| دقة الكلمات (Word Accuracy) | **98.45%** | — | **86.76%** | — |
| Accuracy (= 1 − CER) | **98.65%** | — | **97.87%** | — |

¹ تم تضييق سقف خطأ محارف دستور العراق إلى < 5% بعد إغلاق فجوة التباعد والترقيم وعكس السلاسل الرقمية.
³ تم إدخال بوابة WER جديدة لدستور العراق عند < 16% بعد أن هبط الخطأ من 17.21% إلى 13.24% (وإلى 7.58% بعد تسوية فروق الكتابة الإملائية للمؤلف).

### 1.4 المقارنة المعيارية متعددة المحركات (Cross-Engine)

لإجراء مقارنة موضوعية موثقة بين `arafix` والمحركات الخام الأخرى (PyMuPDF, pdfplumber, pdfminer):

```bash
python scripts/bench_cross_engine.py \
    --pdf tests/fixtures/real_pdf_narrative/iraq_constitution.pdf \
    --truth tests/fixtures/real_pdf_narrative/iraq_constitution_original.txt
```

### 1.5 الإعادة النصية الموحدة

```bash
python scripts/eval_unified.py --pdf tests/fixtures/real_pdf_narrative/file.pdf \
    --truth tests/fixtures/real_pdf_narrative/original.txt --scientific -v
```

---

## 2. الطبقة العلمية: MCS / DBR / BFE / SHDR

أربعة مقاييس في `src/arafix/scientific.py`. جميعها تُستدعى دفعةً واحدة عبر
`scientific_audit(reference, hypothesis)`، أو من CLI بعلم `--scientific`.

> **تنبيه منهجي مهم:** بوابات هذه الطبقة مثبتة على fixture الرواية المشكولة
> (`real_pdf_narrative`) حصراً، لأنها الوحيدة ذات التشكيل الوافر. أما
> `iraq_constitution` فشبه مجرّد من التشكيل (٩ علامات في ~٥٠٠٠ محرف في المرجع)،
> فعيّنة العلامات ضئيلة وأي خلاف واحد يُسقط النسبة (~11% للعلامة). انخفاض DBR
> عليه **ليس عطباً** بل طبيعة العينة — وهذا سبب تحديد نطاق البوابات مقصوداً
> في `test_scientific_floors.py`.

### 2.1 MCS — Morphological Continuity Score ∈ [0,1]

مورفولوجيا العربية تركب **تيار الحروف الأساس** لا أشكال العرض ولا الحركات.
MCS يسأل: هل يبقى ذلك التيار متصلاً بالمرجع؟ وهل هوية الاتصال الجوهرية سليمة؟

```
score = 0.50·letter_fidelity + 0.35·token_continuity + 0.15·joining_integrity
```

- `letter_fidelity`: 1 − CER على تيار الحروف العربي المُكنَن (بلا علامات).
- `token_continuity`: نسبة SequenceMatcher على رموز الحروف فقط.
- `joining_integrity`: معدّل صيانة هوية الاتصال بين أشكال العرض المتجاورة
  (يعادل 1.0 تلقائياً إذا لم يبقَ شكل عرض في النص).

| القيمة | رواية حقيقية | دستور العراق |
|---|---:|---:|
| score | **0.9956** ✓ (≥ 0.99) | 0.9762 |
| letter_fidelity | 0.9990 | 0.9918 |
| token_continuity | 0.9887 | 0.9437 |
| joining_integrity | 1.0 | 1.0 |

### 2.2 DBR — Diacritic-to-Base Ratio ∈ [0,1]

هل الحركات موجودة بالكمية الصحيحة **ومتصلة بالقواعد الصحيحة**؟ يمكن أن يكون
المخزون تاماً والالتصاق مكسوراً — لذلك يقيس الاثنين.

```
score = 0.55·attachment_accuracy + 0.30·inventory_match
        + 0.15·(1 − min(1, leading_mark_rate·5))
```

- `inventory_match`: تشابه جيب التمام (cosine) بين histograms أنواع العلامات.
- `attachment_accuracy`: بين القواعد المتطابقة التي تحمل علامات في المرجع،
  نسبة من مجموعتها متعددة العلامات مطابقة (مقارنة غير حساسة للترتيب بعد
  `order_combining_marks`).
- `leading_mark_rate`: كلمات تبدأ بحركة (يجب أن تكون ~0).

| القيمة | رواية حقيقية | دستور العراق |
|---|---:|---:|
| score | **1.0000** ✓ (≥ 0.99) | 0.5846⁴ |
| inventory_match | 1.0000 | 0.4300 |
| attachment_accuracy | **1.0000** ✓ (≥ 0.99) | 0.5556⁴ |
| leading_mark_rate | 0.0 ✓ | 0.0 ✓ |
| علامات ref ↔ hyp | 443 ↔ 443 | 9 ↔ 33 |
| كثافة علام/قاعدة | 0.0856 ↔ 0.0857 | 0.0023 ↔ 0.0085 |

⁴ راجع التنبيه المنهجي أعلاه: مرجع بلا تشكيل تقريباً (٩ علامات).

**هذا هو عملياً مقياس «دقة التشكيل» (FAR-D في بعض الأدبيات):**
`attachment_accuracy` + `inventory_match` هما دقة الحركة نوعاً وموضعاً والتصاقاً.

### 2.3 BFE — Bidi Flow Entropy

إنتروبيا شانون (بِتّات) على **جولات الاتجاه** بعد طيّ أصناف Unicode bidi إلى
دلاء `{R, L, EN, AN, M, N, W}`.

- `normalized = H / log2(|الدلاء الفعّالة|)` ∈ [0, 1].
- **الإشارة هي `delta_to_ref` لا الصفر**: نص إنجليزي خالص له إنتروبيا منخفضة
  أيضاً. المطلوب أن يقترب مخرَج arafix من BFE المرجع، لا من الصفر.
- بوابة: **Δref ≤ 0.02**.

| القيمة | رواية حقيقية | دستور العراق |
|---|---:|---:|
| normalized (hyp) | 0.6722 | 0.6444 |
| normalized (ref) | 0.6747 | — |
| **Δref** | **0.0025** ✓ | **0.0085** ✓ |
| entropy_bits | 1.7376 | 1.6657 |
| n_runs | 3285 | 1966 |

### 2.4 SHDR — Semantic Homoglyph Drift Rate

ما نسبة الحروف العربية في المخرَج وهي «توائم PDF» (ی/ھ/ک/…): تُقرأ كما هي لكنها
تكسر المساواة والبحث وNLP.

- `drift_rate = homoglyphs / arabic_letters` في المخرَج.
- `true_letter_error_rate`: خطأ حروف بعد طيّ التوائم (خطأ المحتوى الحقيقي).
- `raw_letter_error_rate`: قبل الطي (يشمل الانجراف).
- بوابة: **drift == 0** و`n_homoglyphs == 0` (الطيّ افتراضي في الإخراج عبر
  `fold_pdf_homoglyphs=True`).

| القيمة | رواية حقيقية | دستور العراق |
|---|---:|---:|
| drift_rate | **0.0** ✓ (0 من 5172) | **0.0** ✓ (0 من 3893) |
| true/raw letter error | 0.0010 / 0.0010 | 0.0082 / 0.0082 |

---

## 3. بوابات السلامة والإصدار: FPR / RAR

تعيش في `scripts/stress_test_report.py` و`scripts/audit_corpus.py` فوق
`tests/fixtures/stress/ultra_complex_corpus.json` — ٥٠ حزمة على ٦ محاور:

| نوع الحالة | العدد | ماذا تفعل؟ |
|---|---:|---|
| `repair_text` | 21 | إصلاح نص معطوب مقابل expected |
| `reverse_visual` | 13 | سطر بصري معكوس → منطقي عبر `reverse_visual_line` |
| `safe` | 12 | نص سليم يجب ألا يتغير |
| `perf` | 3 | كتل حجمية (10k سطر) للسرعة فقط |
| `perf_safe` | 1 | حجمية + يجب ألا تتغير (A6-04) |

إجمالي حالات must-not-change = **18** (تشمل A6-04).

### 3.1 التعريفات التشغيلية (من الكود)

- **FPR** = إصلاحات كاذبة ÷ حالات السلامة. حالة السلامة تفشل إذا تغيّر النص
  أو لم يطابق expected. **البوابة: FPR == 0.00%** (صارمة، أي مخالفة تمنع
  الإصدار).
- **RAR** = استرجاعات تامة (output == expected حرفياً) ÷ حالات الاسترجاع
  الوظيفية. **البوابة: RAR ≥ 98%**.
- **متوسط CER** على حالات الاسترجاع: ≤ 5% (بوابة لينة تُبلَّغ ولا تدخل قرار
  الإصدار).

### 3.2 سياق العدّاد: لماذا ترى 17 أحياناً و18 أحياناً؟

كلا الرقمين صحيح والفرق حالة واحدة:

| الأمر | حالات السلامة المحسوبة |
|---|---|
| `stress_test_report.py` (كاملة) | **18** (تشمل `perf_safe` A6-04) |
| `stress_test_report.py --skip-perf` | **17** (تُستبعد كل حالات perf) |
| `audit_corpus.py` (الافتراضي) | **17** — ونطاقه `repair_text`+`safe` فقط (33 حالة؛ يتخطى reverse_visual وperf) |

### 3.3 قيم اليوم (2026-08-23)

| الأداة | النتيجة |
|---|---|
| `stress_test_report.py --skip-perf` | FPR **0.00%** (0/17) ✓ · RAR **100%** (29/29) ✓ · mean CER **0.00%** · القرار: APPROVED |
| حالة `perf_safe` A6-04 فحصاً مباشراً | changed=False، exact=True ✓ ⇒ 18/18 في التشغيلة الكاملة |
| `audit_corpus.py` | cases=33 · safe=17 · false_repairs=**0** ✓ · recovery 16/16 (RAR 100%) ✓ · revert_failures=**0** ✓ |

### 3.4 خريطة المصطلحات (لتفادي الالتباس)

| اسم في `docs/recovery-audit-and-evaluation-plan.md` §7 | اسم البوابة/الأداة | العلاقة |
|---|---|---|
| False Repair Rate | **FPR** | نفس الشيء عملياً |
| Fix Accuracy Rate (تسمية شائعة FAR) | 1 − FPR | صياغة بديلة للمفهوم ذاته |
| Exact page recovery | **RAR** / exact_recoveries | نفس الشيء |
| Auto-repair precision | — (لكل قاعدة لاحقاً) | مخطط، لا يُقبل رقم عام قبل corpus معنونة |
| Repair coverage | — | لا تُرفع على حساب precision |
| Revert success | revert_failures=0 في `audit_corpus.py` | 100% للرقع reversible |

---

## 4. دقة التشكيل على مستوى العناقيد (H11)

فضلاً عن DBR الوثائقي (§2.2)، توجد طبقة أدق لاختبارات التحوير في
`tests/hardening/harness.py::mark_attachment_metrics(gold, out)`:

- `cluster_accuracy`: تطابق عناقيد (قاعدة ← مجموعتها) كلياً.
- `marked_cluster_accuracy`: التطابق على العناقيد الحاملة لعلامات فقط.
- تعيد `None` إذا اختلفت تسلسلات القواعد (لا معنى لقياس الالتصاق بعد فقد حروف).

هذه مقاييس طبقة الاختبار (H11 mark mutations) وليست مقياساً وثائقياً؛ تظهر في
`pytest tests/hardening/test_h11_mark_mutations.py`.

---

## 5. مقياس الاتجاه والترتيب: BIDI / RTL Order

سلامة الاتجاه تقاس بثلاث طبقات متكاملة:

1. **BFE Δref** (§2.3) — المقياس الوثيقي: هل تدفّق الاتجاهات في المخرَج يطابق
   المرجع؟ بوابة ≤ 0.02.
2. **أدوات الترتيب** في `src/arafix/order.py`: `reverse_visual_line`,
   `fix_order`, `order_combining_marks`، وترتيب قراءة الأعمدة
   `reading_order="rtl"` في `layout.py`.
3. **corpus الاتجاهات الخصمي**: ١٠٠٠ حالة
   (`benchmarks/adversarial_bidi_corpus.json`) تُختبر استرجاعها التام في
   `tests/test_hardening.py::test_adversarial_bidi_corpus_is_exactly_recovered`
   — **1000/1000** ✓ — إضافة إلى fuzzing عشوائي بذرية ثابتة
   (`tests/hardening/test_h5_bidi_fuzz.py`).

---

## 6. ملخص بوابات CI

| الاختبار | البوابة |
|---|---|
| `test_scientific_floors.py` (رواية مشكولة) | MCS ≥ 0.99 · DBR ≥ 0.99 · attach ≥ 0.99 · leading == 0 · BFE Δref ≤ 0.02 · SHDR drift == 0 |
| `test_regression_real_pdf.py` | CER كامل < 3% · بدون تشكيل < 3% · محتوى < 2.5% · WER محتوى < 2% · أفضلية على raw |
| `test_regression_iraq_constitution.py` | CER كامل/محتوى < 18% · letters-only < 2% |
| `stress_test_report.py` | FPR == 0 (صارمة) · RAR ≥ 98% (صارمة) · mean CER ≤ 5% (لينة) |
| `test_hardening.py` (bidi) | استرجاع تام 1000/1000 |
| `harness H11` | cluster/marked-cluster accuracy على تحويرات العلامات |

> **سياسة الحدود:** لا يُخفَّض أي حدّ أعلاه دون قرار موثّق في CHANGELOG —
> إما أن التغيير خاطئ أو أن الحد يحتاج مذكرة تصميم صريحة.

---

## 7. حدود ما تقيسه هذه المقاييس

- قيم اليوم مربوطة بـfixtures المستودع وإصداره (v1.0.1) وتاريخ القياس
  (2026-08-23). لا تعمّمها على ملفاتك؛ شغّل `arafix eval` على ملفاتك مع مرجع.
- DBR/MCS على نصوص شبه مجرّدة من التشكيل ليست مؤشر عطب (انظر §2).
- FPR/RAR تقاس على تحويرات نصية seeded مشتقة من مراجع حقيقية — ليست ادعاء
  أداء على PDF glyph-level معلّم (انظر قسم Glyph Evidence في README).
- الثقة (`confidence`) في المكتبة **درجة قوة دليل** وليست احتمالاً معايراً.
