# عينة الفحص المستقلة (Safahat)

كتب عربية **موجودة مسبقاً** من [صفحات — safahat.org](https://www.safahat.org/)  
(لم يُنشئها مطوّرو arafix، وليست مولَّدة بالذكاء الاصطناعي).

## الكتاب الذهبي (canonical) — للاختبارات القادمة

**`docs/thumb_red/` — بصمة الإبهام الحمراء**

بوابة القياس التكرارية:

```bash
python benchmarks/independent_eval/eval_thumb_red.py --refresh
```

التفاصيل والمنهج: [`docs/thumb_red/README.md`](docs/thumb_red/README.md) · التقرير: `thumb_red_eval.json`

## الكتب الثلاثة

| المعرّف | العنوان | صفحات | مجلد العمل | الدور |
|---------|---------|------:|------------|--------|
| **`thumb_red`** | بصمة الإبهام الحمراء | 204 | `docs/thumb_red/` | **canonical / regression** |
| `deconstruction` | مداخل إلى التفكيك | 440 | `docs/deconstruction/` | تنوع (فكر/هوامش) |
| `bilhaqq` | وبالحق نزل | 182 | `docs/bilhaqq/` | تنوع (آيات/نقاش) |

نسخ PDF الأصلية أيضاً في `docs/*.pdf` (مسطّحة).

## ما أُنجز (الخطوة التالية)

| الخطوة | الحالة |
|--------|--------|
| تشخيص عيوب (`diagnose.json`) | ✅ |
| استخراج خام MuPDF (`raw_mupdf.txt`) | ✅ |
| استخراج arafix كامل (`arafix_out.txt`) | ✅ **أُعيد بـ 1.0.1** |
| اختيار 5 صفحات/كتاب للـ gold | ✅ ثابت (`sample_pages.json`) |
| عيّنات `sample/page_*_arafix.txt` | ✅ **أُعيدت بـ 1.0.1** (الـ gold المراجع لم يُمسّ) |
| **Gold مراجع يدوياً** | ✅ **15/15** صفحات العيّنة (5×3 كتب) |
| تقييم pilot CER | ✅ `pilot_eval.json` — متوسط 15 صفحة |

## هيكل كل كتاب

```text
docs/<doc_id>/
  source.pdf
  meta.json
  diagnose.json
  raw_mupdf.txt
  arafix_out.txt
  sample_pages.json
  sample/
    page_NNN_raw.txt
    page_NNN_arafix.txt
    page_NNN_gold.txt      # DRAFT إلا الصفحات المعلَّمة أدناه
```

### صفحات gold المراجعة (15/15)

| كتاب | الصفحات |
|------|---------|
| thumb_red | 47, 87, 149, 176, 188 |
| deconstruction | 45, 152, 199, 298, 380 |
| bilhaqq | 28, 63, 110, 133, 162 |

كل ملف: `docs/<doc_id>/sample/page_NNN_gold.txt`  
**منهج الـ gold:** تصحيح يدوي لمخرج النظام (مسافات، إملاء ظاهر، آيات حيث أمكن) — **لا** تأليف نص جديد؛ المصدر PDF منشور من Safahat.

## نتائج pilot (15 صفحة gold)

**شفافية:** التحسينات في arafix **1.0.1** بُنيت على هذه الكتب المنشورة (Safahat)،
**ليست** على نصوص مولَّدة بالذكاء الاصطناعي.  
التفاصيل: `CHANGELOG.md` §1.0.1 و`src/arafix/pdf_confusions.py` و`pilot_eval.json`.

### متوسطات (15 صفحة)

| المقياس | raw | arafix 1.0.1 |
|---------|----:|-------------:|
| **CER** | 0.784 | **0.175** |
| **CER حروف فقط** | ~0.75 | **0.035** |
| **WER** | — | **2.56** |

تحسّن CER تقريبًا **×4.5** مقابل الخام؛ استرجاع الحروف (بدون مسافات) ~**3.5٪** خطأ.

\* `cer_letters_only`: بعد حذف المسافات/الترقيم.  
† WER ما زال مرتفعًا نسبيًا بسبب تقطيع كلمات ناقص (مسافات هندسية جزئية).

### ملاحظات نوعية

1. **نجاح:** طيّ PF، اتجاه، `امل→الم` / `كبري→كثير`… على كتب حقيقية.
2. **فجوة متبقية:** مسافات داخل/بين الكلمات؛ بعض بقايا ترميز الخط.
3. **Held-out:** لا تُستخدم هذه الصفحات لتوسيع المعجم النواة.

## إعادة التشغيل

```bash
pip install "arafix[pdf]"
python benchmarks/independent_eval/run_extract.py
```

(لا يOverwrite ملفات `*_gold.txt` الموجودة.)

## تقييم صفحة مقابل gold

```bash
arafix eval docs/thumb_red/source.pdf --truth docs/thumb_red/sample/page_047_gold.txt
# أو برمجياً: evaluate_text(hypothesis, gold)
```

للصفحات الجزئية قارن ملفات `sample/page_NNN_*.txt` مباشرة.

## ما يُرفع إلى GitHub / ما يبقى محليًا

| يُرفع | لا يُرفع (gitignore) |
|--------|----------------------|
| `README.md`, `manifest.json`, `pilot_eval.json`, `run_extract.py` | `*.pdf` (الكتب الكاملة) |
| `sample/page_*_{raw,arafix,gold}.txt` (15 صفحة) | `raw_mupdf.txt`, `arafix_out.txt` (استخراج كامل) |
| `meta.json`, `diagnose.json`, `sample_pages.json` | |

لإعادة الاستخراج محليًا: نزّل الكتب من safahat.org → `docs/<doc_id>/source.pdf` → `python run_extract.py`.

## الترخيص

الكتب من safahat.org وحقوق الناشرين/المؤلفين. **تقييم بحثي محلي فقط** — لا تُشحن كتب PDF مع PyPI/GitHub.

## ماذا بعد؟

1. مراجعة بقية `sample/page_*_gold.txt` (4 صفحات × 3 كتب).
2. توسيع gold إن لزم (صفحات غلاف، فهارس، آيات، أرقام إنجليزية).
3. استخدام المجموعة **held-out** عند تحسين تقطيع الكلمات/المسافات.
