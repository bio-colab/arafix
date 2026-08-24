# TODO — خريطة طريق arafix التنفيذية

هذا الملف متتبعٌ حيّ للمهام المعتمدة. كل بند يحمل حالته ومعيار قبوله.
المبادئ الحاكمة مثبتة في `tests/hardening/test_h15_mission_boundary.py`
وخلاصتها: **استرجاع الترميز ≠ تصحيح لغوي**.

---

## 1) Producer Corpus — الأولوية القادمة

> 📣 **نقاش الجمهور ومساهمات العينات**: <https://github.com/bio-colab/arafix/issues/12>

### المفهوم

لا يكفي أن نقول «PDF». سلوك الاستخراج والإصلاح يتغير جذرياً بحسب
**مَن أنتج الملف وبماذا**. أي قياسٍ أو بوابةٍ لا تسجل هوية المنتج تقيس
شيئاً آخر — وقد ثبت ذلك داخلياً: الـPDF الواحد يعطي نصاً مختلفاً بين
`fitz.get_text()` والمسار الهندسي (`get_texttrace`) — موثق في
`benchmarks/wiki_eval/README.md`.

### الأدلة من مدونتنا المحلية نفسها (فحص 2026-08-24)

| العينة | producer | نسخة | الخطوط | ToUnicode |
|---|---|---|---|---|
| wiki_eval (مولّد) | `ReportLab PDF Library` | 1.3 | Type1 + TrueType مقصوص | جزئي |
| glyph fixture (PyMuPDF) | *(فارغ)* | 1.7 | Type0/Identity-H كامل | نعم |
| دستور العراق (واقعي) | `doPDF Ver 8.3` (**طابعة!**) | 1.5 | Type0 مقصوص SimplifiedArabic | نعم |
| file.pdf (واقعي) | `Skia/PDF m152 Google Docs` | 1.4 | Type0 مقصوص | نعم |

أربعُ عيناتٍ فقط → أربع بيئات إنتاج مختلفة. والحقول كلها قابلة للقراءة
آلياً اليوم عبر PyMuPDF (+ fontTools لجدول `name` عند وجوده).

### الفئات المستهدفة من المنتجين

Adobe InDesign · Microsoft Word · LaTeX/XeLaTeX · LibreOffice · ماسح
ضوئي (OCR-layer) · برامج النشر العربية القديمة · أرشيف حكومي ·
برامج تشغيل الطابعات (doPDF وأشباهها) · مصدّرات ويب (Google Docs/Skia).

### الحقول المعيارية لكل عينة (مسودة عقد `arafix.producer-sample.v1`)

```jsonc
{
  "sample_id": "sha256-prefix",
  "producer": "doPDF Ver 8.3 Build 931",
  "creator": "",
  "pdf_version": "1.5",
  "source_software_class": "print-driver | word | indesign | latex |
                            libreoffice | scanner-ocr | legacy-arabic |
                            gov-archive | web-export | unknown",
  "fonts": [
    {"name": "FNTSBS+SimplifiedArabic", "type": "Type0",
     "encoding": "Identity-H", "has_ToUnicode": true,
     "is_subset": true, "vendor": null}
  ],
  "extractor": {"name": "pymupdf", "version": "1.28.0",
                "path": "geometric-texttrace"},
  "symptoms_observed": ["reversed", "pf-forms", "empty", "..."],
  "license_note": "عينة عامة/مجرّدة — بلا وثائق سرية"
}
```

### المراحل

* **P0 — أداة الحصاد**: `scripts/harvest_producer_metadata.py` تفرغ كل
  الحقول أعلاه آلياً لأي PDF إلى JSON (نصف يوم؛ كل القراءات متاحة).
* **P1 — مصنّف المصادر**: قواعد على producer/creator strings →
  `source_software_class` (قابل للتحديث؛ المجهول يبقى unknown ولا
  يُخمَّن).
* **P2 — بناء المدونة**: استقبال مساهمات الجمهور (#12)
  + توليد داخلية لكل فئة نقدر نحاكيها (Word/LibreOffice/LaTeX متاحة
  محلياً للتوليد).
* **P3 — بوابات لكل فئة**: مصفوفة «سلوك متوقع» لكل منتج تُربط بمقاييس
  `docs/metrics.md` — انحراف فئةٍ عن صفّها = اختبار جديد.
* **P4 — الربط بالقياس**: `arafix eval --scientific` يسجل حقول المنتج
  في التقارير حتى لا يعود أي رقمٍ بلا هوية منتجه.

### معايير القبول

1. أداة الحصاد تفرغ الحقول كاملة لعيناتنا الأربع الحالية.
2. عقد JSON موثق ومثبت باختبار مخطط.
3. ≥3 عينات مجتمعية حقيقية مصنفة قبل إغلاق P2.
4. صفر اعتماد جديد على المكتبة الأساسية (كلها أدوات benchmarks).

---

## 2) قائمة متابعة عامة

| البند | المصدر/الدليل | الحالة |
|---|---|---|
| `shape_match.py`: مطابقة أشكال الجليفات للخطوط المقصوصة (لا cmap ولا أسماء بعدها — قيس تجريبياً) | glyph_fixtures README §حدود | تصميم مشار إليه في cmap.py، غير منفذ |
| كلمات متعددة مواضع الزوج («جديد»←«جذيذ») خارج نطاق الدمج العام | glyph_fixtures README §حدود | حد موثق؛ يحتاج قرار تصميم |
| عمى نمط «رقم:» في بوابة إنقاذ الأسطر | H13 + optin_field | مثبت محافظاً؛ الإصلاح بقرار موثق |
| ترقية `confidence_mode=density` للافتراضي | قرار optin_field الموثق | مجدول لإصدار minor (1.1) بإعلان |
| ترقية `rescue_mixed_lines` بعد إغلاق عمى «رقم:» وتوثيق اقتران `forward_flank_marks` | قرار optin_field الموثق | محجوب حتى استيفاء الشرطين |
| توصيل GlyphEvidence داخل `context.repair()` | glyph_fixtures (بوابات خضراء 13 حالة) | القرار المصيري القادم؛ شرطه المسبق تحقق |
| توسعة glyph fixtures: كذبات بأشكال عرض + خط OFL ثانٍ (Noto Naskh) | glyph_fixtures README §حدود | مسار مباشر عبر CASES |

---

## غير الأهداف (تثبيتاً للمسار)

OCR · تصحيح إملائي/نحوي عام (H15) · شبكات عصبية أو تبعيات تشغيلية
إضافية على النواة · تخمين بلا شاهد.
