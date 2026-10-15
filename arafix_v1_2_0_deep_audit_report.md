# التقرير الهندسي والتشريحي الشامل لمكتبة arafix (الإصدار 1.2.0)

يمثل هذا التقرير حصيلة تشريح معماري وخوارزمي كامل لمكتبة `arafix` (الإصدار `1.2.0`، البالغ حجم كودها المصدر `11,322` سطراً موزعة على `25` وحدة برمجية تحت `src/arafix/`). أُجري الفحص عبر تشغيل فعلي لترسانة الاختبارات والقياسات داخل بيئة معزولة، متبوعاً بحملة تصيّد هجومية (Adversarial Bug Hunting) وتحليل الأداء التفصيلي (`cProfile`) ومسح الشجرة المجردة (`AST`) لتتبع الزوائد والركام البرمجي، مع الالتزام الصارم بالحدود الدستورية الثلاثة للمشروع: **التدرج المشروط بالشاهد**، **انعدام التبعيات الإلزامية للنواة (`stdlib` فقط)**، و**الخط الفاصل الصارم بين استرجاع الترميز والتصحيح اللغوي (`استرجاع الترميز ≠ تصحيح لغوي`)**.

## 1. التشريح المعماري وتقييم التصميم الجوهري

تنفرد مكتبة `arafix` في فضاء معالجة النصوص العربية المستخرجة من ملفات PDF بهندسة «السلّم المتدرج المحكوم بالشواهد» (Evidence-Gated Graded Ladder) بدلاً من النهج التقليدي المدمر (`arabic_reshaper + python-bidi`) الذي يعيد تشكيل ما شُكِّل سلفاً ويعكس ما لم ينعكس.

### 1.1 البنية الطبقية وتدفق البيانات في الأنبوب

يرتكز الأنبوب (`src/arafix/pipeline.py`) على تقسيم صارم للمسؤوليات يمنع تداخل الطبقات أو تلويث الشواهد قبل قياسها:

| المرحلة | الوحدة البرمجية | الوظيفة الدقيقة | الشاهد الحاكم للبوابة |
| :--- | :--- | :--- | :--- |
| بوابة النظافة (`HYGIENE`) | `src/arafix/hygiene.py` | تطهير مسافات يونيكود (`NBSP`)، الشرطات اللينة (`U+00AD` مع حماية الموجيبيك)، فاصلة الآلاف المنقلبة (`U+066C`)، ومحارف العرض الصفري | وجود فعلي للمحارف الشائبة قبل التشخيص |
| الدرجة 0 (`DIAGNOSE`) | `src/arafix/diagnose.py` | تشخيص جبري للموجيبيك (`UTF-8/CP1256/ISO-8859-6`)، وعدّ نطاقي لأشكال العرض و`PUA` والكشيدة، وتصويت مرجّح ثلاثي الشواهد للاتجاه البصري | عتبات `DEFAULT_THRESHOLDS` أو برهان قطعي (`proof`) |
| الدرجة 1أ (`NORMALIZE`) | `src/arafix/normalize.py` | طيّ أشكال العرض المفردة (`SIMPLE_PF_TO_BASE`) لكشف التاء المربوطة والألف المقصورة مع إبقاء الرباطات (`ﻻ`) والتشكيل الفاصل (`U+FE70–FE7F`) ذرات صلبة | `pf_ratio > 0.02` أو `tatweel > 0.005` |
| الدرجة 2 (`REORDER`) | `src/arafix/order.py` | عكس السطور البصرية على مستوى عناقيد الجرافيم (`grapheme_clusters`) مع حماية واستعادة جزر `LTR` والروابط والتواريخ والأقواس | `order_score > 0.30` أو `rescue_mixed_lines` |
| الدرجة 1ب (`EXPAND_LIGATURES`) | `src/arafix/normalize.py` | تفكيك الرباطات المؤجلة (`ﻻ ← لا`) وأشكال التشكيل الفاصلة بعد استقرار اتجاه السطر | وجود محارف في `DEFERRED_PF_TO_BASE` |
| ترقيع لام-ألف (`REPAIR_LAM_ALEF`) | `src/arafix/lamalef.py` | إصلاح انقلاب «لا ← ال» الموروث من مستخرجات خارجية بشاهد قاطع (`اا/اأ/اإ`) أو بحسم معجمي مزدوج الشرط | تطابق `_DECISIVE` أو غياب الكلمة وحضور المقلوبة في المعجم |
| تباعد والتباسات PDF (`REPAIR_SPACING`) | `src/arafix/hygiene.py` + `pdf_confusions.py` | طيّ الانقسامات الهندسية داخل الكلمة، وفصل الأدوات الملتصقة، وتطبيع مسافات الترقيم العربي، وقائمة التباسات `Safahat` المغلقة | سياق حروف عربية صريحة ومغلقة |
| سياق الوثيقة (`CONTEXT`) | `src/arafix/context.py` + `evidence.py` | توليد المرشحات ودمج الأدلة (`EvidenceFusion`) مع نموذج الأدلة النافية (`NegativeEvidenceModel`) | تفعيل صريح `enable_context_scoring=True` وقرار `SAFE` |
| الدرجة 3 (`REBUILD_CMAP`) | `src/arafix/cmap.py` | استرجاع خرائط الخطوط المضمّنة عبر عكس `cmap`، وفك أسماء `AGL`، ونشر المعنى عبر شجرة `GSUB` (`LookupType 1, 2, 4, 7`) | محارف `PUA` أو `U+FFFD` مع تطابق `glyph_id` |
| التدقيق والعكس (`AUDIT`) | `src/arafix/audit.py` | توثيق كل قرار (`SAFE/UNCERTAIN/UNSAFE`) وبناء رقعة عكسية محروسة ببصمة `SHA-256` (`arafix.recovery-audit.v1`) | `audit_mode` بقيمة `summary` أو `full` |

### 1.2 نتائج التشغيل الفعلي لمنظومة الاختبارات والبوابات

عند تشغيل حزمة الاختبارات الكاملة وأدوات القياس المدمجة على الكود المصدري المستخرج:

| الحزمة المختبرة | أداة التشغيل | النتيجة الفعلية | الملاحظات التشخيصية |
| :--- | :--- | :--- | :--- |
| اختبارات الوحدات والتحصين (`tests/`) | مشغّل بايثون المتوافق مع `pytest` | نجاح `808` اختباراً، تخطي `69` (تتطلب `PyMuPDF`)، فشل `0` | توافق تام في جميع مسارات النواة القياسية |
| بوابة الإطلاق الصارمة (`stress_test_report.py`) | `scripts/stress_test_report.py --skip-perf` | `FPR = 0.00%` (`0/17`)، `RAR = 100.00%` (`29/29`) | اجتياز كامل لمدونة الضغط المعقدة |
| تدقيق العكس والامتناع (`audit_corpus.py`) | `scripts/audit_corpus.py` | `33` حالة، `0` إصلاحات كاذبة، `0` فشل في عكس الرقعة | تطابق `100%` في استرجاع الأصل عبر `Patch.revert` |
| بنشمارك الطفرات النصية (`run_mutation_benchmark.py`) | `scripts/run_mutation_benchmark.py` | `supported_exact = 8/14`، `abstentions = 2/2`، `revert = 16/16` | إخفاق `6` حالات من أصل `14` مدعومة (مفصّلة في القسم 2) |
| كلفة التدقيق الكامل (`benchmark_audit_overhead.py`) | `scripts/benchmark_audit_overhead.py` | كلفة `summary`: `0%–4.5%`، كلفة `full`: `1217%–1495%` | عنق زجاجة خوارزمي حاد في `AuditMode.FULL` (مفصّل في القسم 3) |

## 2. سجل الأخطاء والثغرات المكتشفة بالتجربة الحية (12 ثغرة مؤكدة)

رغم نجاح الاختبارات الـ `808` الحالية، كشف الفحص الهجومي المعمق عن **12 خطأً برمجياً وخوارزمياً حقيقياً**، منها أخطاء حرجة تكسر بوابة `FPR = 0` على النصوص العربية السليمة، أو تعيد نصاً غير مُصلَح على الإطلاق في واجهات `DocumentResult`، أو تمزّق الكلمات العربية في النصوص البصرية.

### 2.1 ملخص الأخطاء المكتشفة حسب الخطورة

| الرمز | الخطورة | الموقع الدقيق | توصيف الخلل | الأثر المباشر |
| :--- | :--- | :--- | :--- | :--- |
| **B-01** | حرجة (`P0`) | `src/arafix/hygiene.py:307-331` | دمج قسري لأي كلمتين عربيتين سليمتين من حرفين (`تم حل ← تمحل`، `له حق ← لهحق`) ورموز البنود المفردة (`المجموعة أ تشمل ← أتشمل`) | **خرق صريح لبوابة `FPR = 0`** وإفساد نصوص عربية سليمة 100% |
| **B-02** | حرجة (`P0`) | `src/arafix/types.py:229-244` و`pipeline.py:1577` | خاصية `page.body_text` و`doc.body_text` تعيد النص الخام المعطوب من `layout.columns` بدلاً من النص المُصلَح في الصفحات أحادية العمود | إرجاع نص معكوس وبأشكال عرض خام (`ﺔﺳﺎﺮﺪ...`) عند طلب `body_text` |
| **B-03** | حرجة (`P0`) | `src/arafix/normalize.py:188-261` | دالة `separate_fused_presentation_forms` تعمل قبل عكس الاتجاه فتفشل في فصل الكلمات البصرية الملتصقة أو تشطر الكلمة الأولى من داخلها | تحول `مرجع القرار` البصري إلى `مرج عالقرار` و`تاريخ العراق` إلى `تاري خالعراق` |
| **B-04** | عالية (`P1`) | `src/arafix/order.py:242, 558, 665` | تعبيرات إصلاح علامات التنصيص `»...«` والأقواس `)...(` تطابق الفجوة الواقعة **بين** زوجين سليمين في نفس السطر فتقلبهما | تحول `قال «الأول» ثم قال «الثاني»` إلى `قال «الأول« ثم قال »الثاني»`، و`(1) USD 500 (2)` إلى `(1( USD 500 )2)` |
| **B-05** | عالية (`P1`) | `src/arafix/lamalef.py:58-68, 163, 215` | عمى كامل عن الحركات في كشف وإصلاح لام-ألف القاطع والمبهم، وعدّ دورات الحلقة بدل عدد الكلمات المُصلحة في `fixed_decisive`، وإهمال نهاية الكلمة | بقاء `اَالنترنيت` و`المُجَالت` و`لئال` معطوبة، وتسجيل `fixed_decisive=1` عند إصلاح `10` كلمات |
| **B-06** | عالية (`P1`) | `src/arafix/pipeline.py:530, 733` و`diagnose.py:688` | تأخير `fold_pdf_homoglyphs` (`ی/ھ/ک`) إلى ما بعد التشخيص وعكس الاتجاه، وغياب `U+06C0` (`ۀ`) و`U+06D5` (`ە`) من جدول الهجائن | فشل كشف الانعكاس في النصوص ذات الياء/الكاف الفارسية (`ریبک باتک لک یف`) ودمج كلماتها خطأً |
| **B-07** | عالية (`P1`) | `src/arafix/pipeline.py:307-395, 475` | إهمال `cfg.reorder` و`cfg.forward_flank_marks` وطيّ أشكال العرض داخل `_rescue_mixed_direction_lines`، وخطأ نطاق `0xFE70..0xFE7F` في السطر 475 | تشوه التشكيل (`إسلاميةَّ`) وبقاء أشكال العرض خاماً (`ﻤﻞﺎﺮﻧﺔ`) في السطور المنقذة داخل الصفحات الطويلة |
| **B-08** | متوسطة (`P2`) | `src/arafix/order.py:247, 627` | التعبير `_DOUBLE_SENTENCE_DOTS = re.compile(r"\.{2,}")` يحذف نقاط الحذف الثلاثية (`...`) في أي سطر معكوس | تحول `تمت هذه الدراسة... في عام 2024` إلى `تمت هذه الدراسة. في عام 2024` |
| **B-09** | متوسطة (`P2`) | `src/arafix/rag.py:160-215` | دالة `_make_paragraph_chunks` لا تفحص تغيّر `column_index` ولا الفجوة السالبة عند الانتقال من أسفل العمود الأيمن لأعلى العمود الأيسر | دمج فقرات من عمودين مختلفين في chunk واحد بصندوق إحاطة يغطي الصفحة كاملة |
| **B-10** | متوسطة (`P2`) | `src/arafix/order.py:256` و`pymupdf_extractor.py:85` | دالة `_is_markable_base` تعتبر الكشيدة `U+0640` (`ـ`، فئة `Lm`) حرفاً أساسياً يقبل حمل الحركات | التصاق الحركات بالكشيدة بدل الحرف الأصلي وانقلاب ترتيب `ّ` و`َ` في `مُـحَمَّدٌ` |
| **B-11** | متوسطة (`P2`) | `src/arafix/hygiene.py:390, 435-441` | تعريف `_ARABIC_BASE = r"\u0621-\u064A"` يغفل علامات التشكيل الطرفية قبل الأقواس والفواصل وعلامات التنصيص | فشل إصلاح التباعد في النصوص المشكولة مثل `المادةِ(١٧)` و`نورٌ »` و`درسٌ ،` |
| **B-12** | متوسطة (`P2`) | `src/arafix/cli.py:166, 243, 384` و`order.py:708` | كسر التوجيه الذكي في CLI عند تمرير خيارات ذات قيم (`-o`, `--format`, `--layout`)، وطباعة الجداول في `stdout`، وتناقض `fix_order_result` | تعطل CLI مع الخيارات المتقدمة، وتلويث المخرج القياسي، وامتناع خاطئ في `fix_order_result` |

### 2.2 التشريح التفصيلي والحلول الهندسية لكل خطأ

#### أولاً: الخطأ الحرج B-01 — دمج الكلمات السليمة الثنائية ورموز البنود في `collapse_midword_spaces`

في `src/arafix/hygiene.py` (الأسطر `297–335`)، تقوم دالة `collapse_midword_spaces` بمسح أي شظية عربية من `1` إلى `3` أحرف متبوعة بمسافة وحرف عربي عبر التعبير `_FRAGMENT_RE`. وعند فحص الشظية اليسرى `left` واليمنى `right`:

```python
        if left in _KEEP_SPACE_AFTER or right in _KEEP_SPACE_AFTER:
            return m.group(0)
        if len(left) == 1 and len(right) <= 1:
            return m.group(0)
        if len(left) == 2 and len(right) > 2:
            return m.group(0)
        if _ARTICLE_PREFIX_RE.match(rest):
            return m.group(0)
        if left in ("الع", "الم", "وال", "بال", "كال", "فال", "لل"):
            return left
        if len(left) >= 3 and len(right) >= 2:
            return m.group(0)
        if len(left) == 3 and len(right) == 1 and right not in "يىة":
            return m.group(0)
        return left_cluster
```

تنشأ هنا ثلاث ثغرات خطيرة تكسر المبدأ الدستوري للمكتبة (`سلامة السليم` و`FPR = 0`):
1. **دمج الكلمات الثنائية المتجاورة (`len(left) == 2` و`len(right) <= 2`):** الشرط `if len(left) == 2 and len(right) > 2:` يحمي الكلمة الثنائية فقط إذا تلتها كلمة من `3` أحرف فأكثر! أما إذا تلتها كلمة ثنائية أخرى غير مدرجة في القائمة المحدودة `_KEEP_SPACE_AFTER` (مثل: `تم حل`، `له حق`، `لك حق`، `تم رد`، `تم سد`، `تم سن`، `تم ضخ`، `تم طي`، `تم فك`، `تم غض`، `تم شن`، `قل لي`، `له يد`، `رب أخ لك`)، فإن الشرط يسقط وتُدمج الكلمتان السليمتان قسراً (`تمحل`، `لهحق`، `لكحق`، `قللي`، `ربأخلك`)!
2. **دمج عناوين البنود الأبجدية المفردة (`len(left) == 1`):** إذا ورد حرف ترقيم أبجدي مفرد مثل `المجموعة أ تشمل` أو `الفئة ب تضم` أو `القسم ج يتضمن` أو `البند د ينص`، فإن `len(left) == 1` و`len(right) >= 2` فيدمجهما الأنبوب فوراً إلى `أتشمل`، `بتضم`، `جيتضمن`، `دينص`! واللافت أن المتغير `_NO_COLLAPSE_SINGLE = frozenset("اأإآةىوويف")` معرّف في السطر `246` من الملف نفسه لكنه متروك ككود ميت لا يُستدعى أبداً!
3. **السبب الجذري لفشل حالة `midword_kerning_split` في `run_mutation_benchmark.py`:** في المقابل، عندما يقع انقسام هندسي حقيقي بعد حرف لا يتصل بما بعده في باقي بادئات «ال» التعريف (مثل `الد ستور` أو `الر واية` أو `الز مان` أو `الذ كاء` أو `الط بيب`)، فإن السطر `323` يقتصر على `("الع", "الم", "وال", "بال", "كال", "فال", "لل")` فيترك `الد ستور` دون إصلاح!

**الحل الهندسي الأمثل (يحقق `FPR = 0` ويرفع دقة `midword_kerning_split`):**
- حماية كل كلمة ثنائية (`if len(left) == 2: return m.group(0)`) إلا إذا كانت شظية بادئة تعريف مقطوعة (`ال` متبوعة بحرف يتصل أو `ول`، `فل`، `بل`، `كل` غير المستقلة).
- بالنسبة للحرف المفرد (`len(left) == 1`): في الإملاء العربي، لا يلتصق الحرف المفرد بالكلمة التالية إلا إذا كان حرفاً قابلاً للاتصال بما بعده (أو حرف عطف `و`/`ف`)، ولا يجوز دمج حروف القطع المعزولة (`أ`، `إ`، `آ`، `ا`، `ة`، `ى`) أو الحرف المفرد المسبوق بكلمة تدل على التعداد (`مجموعة`، `فئة`، `قسم`، `بند`، `فقرة`، `مادة`، `جدول`، `شكل`، `ملحق`، `نموذج`).
- توسيع قاعدة بادئات التعريف المقطوعة (`ال + حرف`) في السطر `323` لتشمل كافة صور `ال` + حرف عربي واحد (`len(left) == 3 and left.startswith("ال")`) شريطة ألا تكون الكلمة اليسرى اسماً ثلاثياً تاماً مبدوءاً بـ `ال` (مثل `الله`، `ألف`، `ألم`، `أمل` — علماً أن الثلاثة الأخيرة تبدأ بـ `أ` المهموزة لا `ا` الوصلية!).

```python
_ENUM_NOUNS_RE = re.compile(
    r"(?:المجموعة|مجموعة|الفئة|فئة|القسم|قسم|البند|بند|الفقرة|فقرة|المادة|مادة|الجدول|جدول|الشكل|شكل|الملحق|ملحق|النموذج|نموذج)\s+$"
)
_ARTICLE_3_PREFIXES = frozenset(
    {"وال", "بال", "كال", "فال", "لل"}
    | {f"ال{ch}" for ch in "بتثجحخدذرزسشصضطظعغفقكلمنهوي"}
) - {"الله", "اللذ", "اللت", "اللا"}
```

#### ثانياً: الخطأ الحرج B-02 — إرجاع نص خام غير مُصلَح في `PageResult.body_text` و`DocumentResult.body_text`

في `src/arafix/pipeline.py` (الأسطر `1495–1605` داخل `_extract_one_page`)، عندما تكون الصفحة أحادية العمود ولا تحتوي على جداول أو ترويسات/تذييلات معزولة، تكون `structural = False`، فينفذ الأنبوب المسار الخطي:

```python
    source = layout.plain_text if layout is not None else raw.text
    result = repair_text(source, cfg)
    ...
    return PageResult(
        page_number=raw.number,
        repair=result,
        fonts=raw.fonts,
        layout=layout,
        n_columns=1,
        width=raw.width,
        height=raw.height,
        tables=_raw_tables(layout),
    )
```

لاحظ أن `blocks` تظل `None`، بينما `layout` يحمل كائن `PageLayout` الذي يحتوي على `layout.columns[0]` وبداخله الجليفات والأسطر الخام **قبل أي إصلاح**!
وعندما يستدعي المستخدم `page.body_text` أو `doc.body_text` (`src/arafix/types.py:229-244`):

```python
    @property
    def body_text(self) -> str:
        if self.blocks is not None:
            parts = [
                b.text
                for b in self.blocks.blocks
                if b.block.role not in ("header", "footer")
            ]
            return "\n".join(p.strip() for p in parts if p.strip())
        if self.layout is not None and getattr(self.layout, "columns", None):
            col_texts = [c.text.strip() for c in self.layout.columns if c.text.strip()]
            return "\n\n".join(col_texts)
        return self.text
```

بما أن `self.blocks is None` و`self.layout.columns` موجود، تدخل الدالة الفرع الثاني وتُرجع `c.text` — وهو النص الخام المعكوس المليء بأشكال العرض (`ﺔﺳﺎﺮﺪ ﺔﻧﺮﺎﻞﻤ ﻲﻓ ﻉﺍﺮﻋﻟﺍ`) متجاهلةً `self.repair.text` بالكامل!
وكذلك في `PageResult.to_markdown` (`types.py:273-282`) و`PageResult.headings` (`types.py:187-195`): عند غياب `self.blocks`، تعيد الدالتان استدعاء `repair_text(ln.text)` سطراً بسطر بإعدادات افتراضية فارغة، مما يهدر:
1. إعدادات `PipelineConfig` الممررة من المستخدم.
2. قرارات عكس الاتجاه على مستوى الصفحة للسطور القصيرة التي لا تتجاوز عتبة الـ `8` أحرف بمفردها.
3. إصلاحات معجم الوثيقة (`harvest_document_lexicon`) ونموذج السياق (`DocumentContext`) التي طُبقت على `self.repair.text`.

**الحل الهندسي الأمثل:**
في `PageResult.body_text`: عندما يكون `self.blocks is None` ولا توجد ترويسات أو تذييلات في `self.layout` (`not self.layout.headers and not self.layout.footers`)، يجب إرجاع `self.text` (`self.repair.text`) مباشرة! وإن وُجدت ترويسات أو تذييلات مع غياب `blocks`، تُستبعد أسطرها من `self.text`. وفي `to_markdown` و`headings`، تُربط الأسطر المصلحة في `self.text.splitlines()` بنظائرها في `layout.columns` عند تساوي عدد الأسطر بدلاً من إعادة تشغيل `repair_text` من الصفر بلا سياق.

#### ثالثاً: الخطأ الحرج B-03 — تمزيق الكلمات البصرية في `separate_fused_presentation_forms`

في `src/arafix/normalize.py` (الأسطر `188–261`)، تحاول دالة `separate_fused_presentation_forms` فصل الكلمات الملتصقة أثناء المرحلة `1أ` (**قبل** عكس الاتجاه في المرحلة `2`). ولحماية الكلمات البصرية المعكوسة من الفصل الخاطئ، وضعت الدالة الحارس التالي في السطر `216`:

```python
        if first_ar_char is not None:
            first_form = PF_JOINING_FORM.get(first_ar_char, JoiningForm.UNKNOWN)
            # إن بدأت الكتلة بشكل ختامي أو تاء مربوطة فهي مقلوبة بصرياً؛ لا نلمسها
            if (
                first_form == JoiningForm.FINAL
                or first_ar_char in _PF_TA_MARBUTA
                or first_ar_char == "ة"
            ):
                out_tokens.append(token)
                continue
```

هذا الحارس يعاني من خللين بنيويين:
1. **تمزيق الكلمات البصرية المنتهية بحرف منفصل:** في الخط العربي، الحروف الستة (`ا د ذ ر ز و`) لا تتصل بما بعدها؛ وبالتالي فإن أي كلمة تنتهي بحرف يقع بعد أحد هذه الحروف الستة (مثل: `القرار`، `العراق`، `الإصلاح`، `الاختبار`، `المشروع`، `القضاء`، `الكتاب`) يكون حرفها الأخير ذا صيغة **`JoiningForm.ISOLATED`** وليس `JoiningForm.FINAL`! وعندما تلتصق كلمتان في سطر بصري معكوس مثل `مرجع القرار` أو `تاريخ العراق`، فإن الحرف الأول في السلسلة البصرية هو `ر` المعزولة أو `ق` المعزولة (`first_form == JoiningForm.ISOLATED`). يفشل الحارس في إدراك أن الكتلة معكوسة بصرياً، فيمسحها من اليسار لليمين، وحين يصادف الحرف الختامي للكلمة الأولى (`ع` النهائية في `مرجع` أو `خ` النهائية في `تاريخ`) متبوعاً بالحرف الابتدائي الذي يسبقه في نفس الكلمة (`ج` الابتدائية أو `ي` الابتدائية)، يظنهما حدّ كلمتين ويدرج مسافة **داخل الكلمة الواحدة**، فتخرج النتيجة بعد العكس: **`مرج عالقرار`** و**`تاري خالعراق`** و**`موض عالعراق`** و**`نتائ جالاختبار`**!
2. **ضياع فصل الكلمات الملتصقة في كافة النصوص البصرية:** حتى حين ينجح الحارس (`first_form == JoiningForm.FINAL` كما في `مجلس القضاء` البصري)، فإن الدالة تتخطى الكتلة ثم تطوي `fold_simple_forms` جميع أشكال العرض إلى حروف أساسية قبل المرحلة `2`، فتضيع معلومات الاتصال إلى الأبد وتخرج الكلمتان ملتصقتين (`مجلسالقضاء`)!

**الحل الهندسي الأمثل:**
تحديد اتجاه الكتلة (`is_visual_token`) ببرهان هوية الوصل ذاته المستخدم في `_signal_joining_forms`:
- في الترتيب المنطقي: حدّ الكلمتين الملتصقتين هو حرف ختامي ثنائي الاتصال (`FINAL` أو تاء مربوطة) يتلوه حرف ابتدائي أو معزول (`INITIAL` أو `ISOLATED`).
- في الترتيب البصري المعكوس: ينعكس الزوج تماماً؛ فحدّ الكلمتين الملتصقتين في التيار البصري هو حرف ابتدائي أو معزول (`INITIAL` أو `ISOLATED` — وهو أول الكلمة اليسرى) يتلوه حرف ختامي ثنائي الاتصال (`FINAL` أو تاء مربوطة — وهو آخر الكلمة اليمنى)!
بإدراج المسافة عند الانتقال `(INITIAL | ISOLATED) → (FINAL | TA_MARBUTA)` عندما تكون الكتلة بصرية، وعند الانتقال `(FINAL | TA_MARBUTA) → (INITIAL | ISOLATED)` عندما تكون الكتلة منطقية، يتحقق الفصل الصحيح 100% في الاتجاهين المنطقي والبصري دون شطر أي كلمة على الإطلاق:

```python
def _is_visual_pf_token(chars: list[str]) -> bool:
    forms = [
        PF_JOINING_FORM.get(c, JoiningForm.UNKNOWN)
        for c in chars
        if PF_JOINING_FORM.get(c, JoiningForm.UNKNOWN) is not JoiningForm.UNKNOWN
        and unicodedata.category(PF_TO_BASE.get(c, c)[:1] or " ") != "Mn"
    ]
    if not forms:
        return False
    if forms[0] is JoiningForm.FINAL or forms[-1] is JoiningForm.INITIAL:
        return True
    fwd_ok = sum(
        (a in (JoiningForm.INITIAL, JoiningForm.MEDIAL))
        == (b in (JoiningForm.MEDIAL, JoiningForm.FINAL))
        for a, b in zip(forms, forms[1:])
    )
    rev_ok = sum(
        (a in (JoiningForm.MEDIAL, JoiningForm.FINAL))
        == (b in (JoiningForm.INITIAL, JoiningForm.MEDIAL))
        for a, b in zip(forms, forms[1:])
    )
    return rev_ok > fwd_ok
```

#### رابعاً: الخطأ العالي B-04 — قلب الأقواس وعلامات التنصيص المتعددة في السطر الواحد (`src/arafix/order.py`)

في `src/arafix/order.py`:
1. في السطر `665`: `out = re.sub(r"»([^«»\n]+)«", r"«\1»", out)`
   إذا احتوى السطر بعد عكسه على اقتباسين سليمين مثل `قال «الأول» ثم قال «الثاني» اليوم`، فإن المقطع الواقع بين نهاية الاقتباس الأول وبداية الاقتباس الثاني هو `» ثم قال «` — وهو لا يحتوي على `«` أو `»` بداخله! فيطابقه التعبير النمطي ويقلبه إلى `« ثم قال »`، مخرّباً السطر إلى: `قال «الأول« ثم قال »الثاني» اليوم`!
2. في السطر `242` و`558`: `_INVERTED_PARENS = re.compile(r"\)([^()\n]{1,48})\(")`
   بالآلية ذاتها تماماً، إذا ورد قوسان سليمان بينهما تاريخ أو رقم أو مبلغ مثل `الفقرة (أ) 2024 - 2025 (ب)` أو `الجدول (1) USD 500 (2)`، فإن المقطع `) 2024 - 2025 (` أو `) USD 500 (` الواقع بين القوسين السليمين يطابق `_INVERTED_PARENS` ويجتاز `_looks_ltr_heavy(inner)`، فينقلب السطر السليم إلى: `الفقرة (أ( 2024 - 2025 )ب)`!

**الحل الهندسي الأمثل:**
لا يجوز استبدال `»...«` أو `)...(` بتعبير نمطي أعمى غير واعٍ بتوازن الأقواس؛ بل يجب التحقق من أن `»` أو `)` ليست مسبوقة بـ `«` أو `(` مفتوحة غير مغلقة قبلها في السطر نفسه (مسمار توازن بسيط `depth == 0` في مرور خطي واحد $O(n)$):

```python
def _fix_unbalanced_pairs(text: str, open_ch: str, close_ch: str, predicate=None) -> str:
    if open_ch not in text or close_ch not in text:
        return text
    chars = list(text)
    n = len(chars)
    i = 0
    while i < n:
        if chars[i] == open_ch:
            # قوس مفتوح سليم: تخطَّ حتى إغلاقه
            j = i + 1
            while j < n and chars[j] not in (open_ch, close_ch, "\n"):
                j += 1
            if j < n and chars[j] == close_ch:
                i = j + 1
                continue
        elif chars[i] == close_ch:
            # قوس إغلاق يتيم في المستوى 0: ابحث عن قوس فتح يتيم يليه
            j = i + 1
            while j < n and chars[j] not in (open_ch, close_ch, "\n"):
                j += 1
            if j < n and chars[j] == open_ch:
                inner = "".join(chars[i + 1 : j])
                if predicate is None or predicate(inner):
                    chars[i], chars[j] = open_ch, close_ch
                    i = j + 1
                    continue
        i += 1
    return "".join(chars)
```

#### خامساً: الخطأ العالي B-05 — عمى الحركات والعدّ الخاطئ في `src/arafix/lamalef.py`

كشف التشريح ثلاث علل مترابطة في `src/arafix/lamalef.py`:
1. **عدّ الدورات بدل الإصلاحات (السطر `163–168`):**
   ```python
   for _ in range(8):
       new = _DECISIVE.sub(lambda m: m.group(1) + m.group(3) + m.group(2), out)
       if new == out:
           break
       report.fixed_decisive += 1
       out = new
   ```
   إذا احتوى النص على `10` كلمات فيها انقلاب قاطع (`االنترنيت`، `األطاريح`...)، فإن `_DECISIVE.sub` يصلحها جميعاً في الدورة الأولى، ويسجّل `report.fixed_decisive = 1` بدلاً من `10`!
2. **عمى الحركات في `_DECISIVE` و`_AMBIGUOUS` و`_apply_lexicon`:**
   التعابير `([{_ALEF}])([{_ALEF}])({LAM})` و`([{_ALEF}])({LAM})` تفترض عدم وجود أي حركة (`\u064B-\u0655\u0670`) بين الألف واللام، كما أن `_apply_lexicon` يبحث عن `word in vocab` و`cand in vocab` بالحركات دون تجريدها للمطابقة المعجمية، ويبادل `word[i]` و`word[i+1]` كمحارف خام بدلاً من مبادلة عنقود الألف بحركته مع عنقود اللام بحركته! لذلك تفشل `اَالنترنيت` و`اأْلَطاريح` و`المُجَالت` و`المجاَلت` بالكامل.
3. **إهمال نهاية الكلمة في `_AMBIGUOUS`:**
   يشترط `_AMBIGUOUS` وجود حرف عربي بعد `ال` (`(?=[\u0600-\u06FF])`)، مما يمنع المعجم من إصلاح انقلاب لام-ألف في آخر الكلمة مثل `لئال ← لئلا` و`أفال ← أفلا`.

**الحل الهندسي الأمثل:**
استخدام `_DECISIVE.subn` لجمع العدد الحقيقي للإصلاحات، وتضمين الحركات الاختيارية `[\u064B-\u0655\u0670]*` ضمن عنقود الألف وعنقود اللام، وعند فحص المعجم في `_apply_lexicon` تُجرَّد الحركات عند الاستعلام في `vocab` (`_strip_marks(word) in vocab` و`_strip_marks(cand) in vocab`) مع الاحتفاظ بالحركات فوق حروفها الأصلية عند المبادلة.

#### سادساً: الخطأ العالي B-06 — عمى الهجائن الفارسية في التشخيص والاتجاه (`normalize.py` + `diagnose.py` + `pipeline.py`)

في ملفات PDF المنتجة عبر خطوط CJK أو Word أو بعض خطوط الويندوز القديمة، تُرمَّز الياء العربية كـ Farsi Yeh (`ی` `U+06CC`) والكاف كـ Keheh (`ک` `U+06A9`) والهاء/التاء المربوطة كـ (`ھ` `U+06BE` أو `ۀ` `U+06C0` أو `ە` `U+06D5`).
في الوضع الحالي:
- عندما يكون النص خالياً من أشكال العرض (`needs_norm = False`)، لا تعمل `fold_pdf_homoglyphs` إلا في السطر `734` من `pipeline.py` — أي **بعد** انتهاء `diagnose` و**بعد** انتهاء `fix_order`!
- النتيجة: عند إدخال جملة معكوسة مثل `'ریبک باتک لک یف هذه ناک'`، يفشل `_signal_lexicon_direction` في مطابقة أي كلمة مع المعجم لأن المعجم مخزون بالكاف والياء القياسيتين (`ك`، `ي`)، فتخرج درجة الانعكاس `0.0`، ولا يُعكس السطر، ثم تُطوى الهجائن في السطر المعكوس وتُدمج كلماته إلى `'ريبك باتك لكيف هذه ناك'`!

**الحل الهندسي الأمثل:**
1. إضافة `"\u06c0": "\u0629"` (`ۀ ← ة`) و`"\u06d5": "\u0647"` (`ە ← ه`) إلى `_PDF_HOMOGLYPH_TABLE` في `normalize.py` و`_HOMOGLYPH_TO_CANON` في `scientific.py`.
2. تطبيق `fold_pdf_homoglyphs` على نسخة الفحص الداخلي في `diagnose.py` (`fold_pdf_homoglyphs(fold_simple_forms(text))`) وفي بداية المرحلة `1أ` في `pipeline.py` (قبل `detect_visual_order`) متى كان `cfg.normalize.fold_pdf_homoglyphs` مفعلاً.

#### سابعاً: الأخطاء B-07 إلى B-12 — حلول دقيقة ومباشرة

| الرمز | سبب الخلل | الحل الهندسي المباشر |
| :--- | :--- | :--- |
| **B-07** | `_rescue_mixed_direction_lines` لا يمرر `rcfg` إلى `fix_order` ولا يطوي أشكال العرض في السطر المنقذ عندما تكون كثافة `PF` في الصفحة كلها `< 2%`، والسطر `475` يفحص `0xFE70..0xFE7F` فقط | تمرير `rcfg = replace(cfg.reorder, forward_flank_marks=cfg.forward_flank_marks)` إلى `_rescue_mixed_direction_lines`، وتطبيق `fold_simple_forms` قبل `fix_order` ثم `expand_deferred_forms` على كل سطر منقذ يحتوي على `PF`، وتصحيح السطر `475` إلى `sum(1 for c in current if is_presentation_form(c))` |
| **B-08** | `_DOUBLE_SENTENCE_DOTS = re.compile(r"\.{2,}")` يمسح كل `...` في السطر | قصر التنظيف على النقطة المزدوجة الناتجة مباشرة عن نقل نقطة السنة/الرقم: `_LEADING_DOT_YEAR = re.compile(r"(?<![\d.])\.(\d{4})\.?\b")` وحذف `_DOUBLE_SENTENCE_DOTS` |
| **B-09** | `_make_paragraph_chunks` في `rag.py` يفحص فقط `vertical_gap > max(...)` فيدمج نهاية العمود الأول ببداية العمود الثاني | إضافة شرط فصل فوري عند تغير العمود أو الارتداد الرأسي لأعلى: `if getattr(line, "column_index", None) != getattr(previous, "column_index", None) or vertical_gap < -page_size: flush()` وعزل `header`/`footer` بدورها الخاص |
| **B-10** | `_is_markable_base` يقبل `TATWEEL` (`U+0640`) لأن فئتها `Lm` تبدأ بـ `"L"` | تعديل `_is_markable_base(ch)` في `order.py` و`pymupdf_extractor.py` إلى: `return bool(ch) and ch != "\u0640" and unicodedata.category(ch).startswith("L")` |
| **B-11** | `_ARABIC_BASE = r"\u0621-\u064A"` في `hygiene.py` لا يسمح بوجود حركات بين الحرف وعلامة الترقيم | تعريف `_ARABIC_TAIL = rf"[{_ARABIC_BASE}]{_MARKS_CLASS}*"` واستخدامه في `_PUNCT_SPACE_BEFORE_RE` و`_CLOSE_PUNCT_SPACE_BEFORE_RE` و`_ARABIC_OPEN_PUNCT_RE` و`_ARABIC_MULTI_SPACE_RE` |
| **B-12** | `_normalize_argv` في `cli.py` يتخطى معاملين فقط لـ `-e/--extractor` دون بقية الخيارات التي تأخذ قيمة | توسيع قائمة الخيارات الثنائية في `_normalize_argv` لتشمل `("-e", "--extractor", "-o", "--output", "--layout", "--reading-order", "--format", "-n", "--pages", "--truth")`|

### 2.3 تشريح سبب إخفاق 6 حالات من أصل 14 في `run_mutation_benchmark.py`

أظهر تشغيل `scripts/run_mutation_benchmark.py` نتيجة `supported_exact = 8/14`. وبفحص ملف المخرجات `reports/audit/mutation-l0.json` كلمةً بكلمة، تبيّن أن الحالات الست المخفقة تعود إلى ثلاثة أسباب محددة:
1. **`pdf_al_meem_confusion` (حالتان في `original.txt` و`iraq_constitution_original.txt`):** يصنّفها `mutation_engine.py` كـ `"supported"`، بينما يستدعي `run_mutation_benchmark.py` دالة `repair_text` بالإعداد الافتراضي `enable_pdf_confusion_repair=False`!
2. **`midword_kerning_split` (حالتان: `إير ان` و`الد ستور`):** الأولى شظية `3+2` (`إير + ان`) يرفضها `collapse_midword_spaces` عمداً لمنع دمج الكلمات الثلاثية مع الثنائية، والثانية `الد ستور` سقطت بسبب اقتصار السطر `323` في `hygiene.py` على `("الع", "الم")` دون `"الد"` (وهي ما يعالجه إصلاح **B-01** أعلاه).
3. **`inverted_parentheses` (حالتان: `)البيجر(` و`()العراقيون متساوون...`):** في الأولى، النص منطقي غير معكوس فلا يعمل `fix_order`، وتقوم `normalize_arabic_punctuation_spacing` بلصق `)البيجر(` بالكلمات المجاورة (`النداء)البيجر (بين`). وفي الثانية، النص الأصلي يحتوي على أقواس مزدوجة `((العراقيون...))` فقام تعبير التوليد في `mutation_engine.py` (`r"\(([{_ARABIC}\s]+)\)"`) بقلب القوس الداخلي الأول مع الخارجي الأول منتجاً `()العراقيون...()`!

## 3. تتبع الأداء والتعقيد الخوارزمي (Performance Profiling)

لتحديد أعناق الزجاجة الفعلية دون تخمين، شُغِّل المحلل المعياري `cProfile` على نصوص عربية بحجم `72 KB` (`10×` نص `original.txt` في الحالتين السليمة والمعكوسة بصرياً) وعلى وضع التدقيق الكامل (`AuditMode.FULL`).

### 3.1 الخريطة الحرارية لاستهلاك المعالج قبل التحسين (`v1.2.0`)

أظهر تحليل `cProfile` (`18.49` مليون نداء دالة في `19.31` ثانية لـ 5 دورات) أن **أكثر من 55% من زمن المعالج يُهدر في عمليات مسح مكررة أو غير ضرورية**:

| المرتبة | الدالة / السطر | الزمن التراكمي (`cumtime`) | عدد النداءات | السبب الجذري للهدر الخوارزمي |
| :--- | :--- | ---: | ---: | :--- |
| **1** | `normalize.py:188 (separate_fused_presentation_forms)` | `3.728 s` | `10` | **لا يوجد فحص خروج مبكر!** تقسم النص بـ `re.split` وتفحص كل محرف بـ `unicodedata.category` وتعيد بناء السلسلة حتى عندما يكون النص خالياً تماماً من أشكال العرض (`pf_ratio == 0`)! |
| **2** | `order.py:302 (grapheme_clusters)` + `_is_markable_base` + `_is_attachable` | `3.381 s` | `4,755` | تستدعي `unicodedata.category` مرتين لكل محرف في كل سطر (`1.3` مليون مرة) وتبني قوائم عناقيد حتى للأسطر التي لا تحتوي على أي حركة تشكيل (`Mn`)! |
| **3** | `diagnose.py:455 (_clean_final_letters_token)` + `_clean_punct_only` | `2.201 s` | `487,610` | تشغّل تعبيراً نمطياً ثقيلاً (`_EDGE_PUNCT.sub`) على كل كلمة عربية على حدة، رغم أن `token.strip(...)` بلغة `C` يؤدي المهمة نفسها أسرع بـ `50` ضعفاً! |
| **4** | `unicode_tables.py:139 (is_pua)` + `in_ranges` | `0.892 s` | `362,650` | حلقة بايثون لكل محرف في النص لفحص `3` نطاقات، بينما تعبير `re` مُترجَم بلغة `C` يفحص النص كله في أقل من `0.1 ms`! |
| **5** | `normalize.py:154 (strip_tatweel_among_presentation_forms)` | `0.810 s` | `10` | بمجرد وجود كشيدة واحدة في النص (مثل خط فاصل `___` أو كشيدة عادية)، تمسح كامل النص حرفاً بحرف حتى مع خلوّه من أشكال العرض! |
| **6** | `diagnose.py:500 (_signal_joining_forms)` | `0.721 s` | `10` | تمسح جميع كلمات النص وحروفه بحثاً عن صيغ وصل `PF_JOINING_FORM` حتى عندما يكون `pf_ratio == 0.0`! |
| **7** | `diagnose.py:321` و`634` (عدّ الحروف العربية مرتين) | `1.382 s` | `572,110` | تحسب `sum(1 for c in text if is_arabic(c) or is_presentation_form(c))` في السطر `634` ثم تعيد حساب المجموع نفسه حرفياً داخل `detect_presentation_forms` في السطر `321`! |
| **8** | `order.py:663` (`"".join(_mirror(c) for c in out)`) | `0.658 s` | `362,605` | حلقة مولّد بايثون واستدعاء دالة لكل محرف بدلاً من `out.translate(_MIRROR_TABLE)` المنفذة بلغة `C`! |
| **9** | `pipeline.py:475` و`546` (ازدواجية الفحص في `repair_text`) | `0.650 s` | `362,655` | السطر `475` يمسح النص كاملاً لعدّ `0xFE70..0xFE7F` حتى عندما يكون `audit_mode="off"`، والسطر `546` يعيد تشغيل `detect_visual_order` للمرة الثانية حتى عندما لا يتغير النص بعد `diagnose`! |
| **10** | `audit.py:162, 315` (`SequenceMatcher` في `AuditMode.FULL`) | `2.850 s` (لكل `7.2 KB`) | `2` | تشغيل `SequenceMatcher(None, before, after, autojunk=False)` بتعقيد $O(N^2)$ على كامل النص (`7,260` حرفاً) دون اقتطاع البادئة واللاحقة المتطابقتين (`_trim_common`) وحتى عندما يكون `original == repaired`! |
| **11** | `context.py:389` + `evidence.py:310` (`DocumentContext.rank`) | ضعف الزمن | لكل كلمة خارج المعجم | تستدعي `DocumentContext.repair` دالة `self.rank(...)` في السطر `389`، ثم تستدعي `candidate_generator.generate(...)` التي تعيد استدعاء `document_context.rank(...)` مرة ثانية بنفس المعاملات! |

### 3.2 نتائج القياس الفعلي بعد تطبيق التحسينات الخوارزمية (بدون أي تبعيات خارجية)

طُبِّقت التحسينات الخوارزمية القياسية (اقتطاع البادئة/اللاحقة في `SequenceMatcher`، بوابات الخروج المبكر بـ `re` المترجمة في `C`، `str.translate` للمحارف المرآتية، و`str.strip` بدلاً من `_EDGE_PUNCT.sub`) وجرى التحقق من **التطابق التام بايت-ببايت (`100% Byte-for-Byte Identity`)** للمخرجات والرقع العكسية:

| مسار القياس وحجم العينة | الزمن قبل التحسين (`v1.2.0`) | الزمن بعد التحسين | معامل التسريع (`Speedup`) | السرعة القياسية الجديدة |
| :--- | ---: | ---: | ---: | ---: |
| إصلاح نص عربي سليم (`72.6 KB`، `audit=off`) | `1,025.27 ms` | **`496.12 ms`** | **`2.07×` أسرع** | `142.9 KB/s` |
| إصلاح نص بصري معكوس بالكامل (`72.6 KB`، `audit=off`) | `1,410.62 ms` | **`735.45 ms`** | **`1.92×` أسرع** | `96.3 KB/s` |
| تدقيق كامل `audit_mode="full"` لنص سليم (`7.26 KB`، `0` تعديل) | `1,571.06 ms` | **`47.55 ms`** | **`33.04×` أسرع** | خفض الكلفة الإضافية من `1495%` إلى `< 5%` |
| تدقيق كامل `audit_mode="full"` مع تعديل (`7.26 KB`، `1` تعديل) | `3,021.47 ms` | **`53.25 ms`** | **`56.74×` أسرع** | خفض زمن بناء الرقعة من `3.02s` إلى `0.05s` |

```python
# الحل الخوارزمي الفائق لـ audit.py (يخفض زمن AuditMode.FULL بمقدار 33x إلى 56x):
def _diff_opcodes(before: str, after: str) -> list[tuple[str, int, int, int, int]]:
    if before == after:
        return []
    n1, n2 = len(before), len(after)
    p = 0
    lim = min(n1, n2)
    while p < lim and before[p] == after[p]:
        p += 1
    s = 0
    lim_s = lim - p
    while s < lim_s and before[n1 - 1 - s] == after[n2 - 1 - s]:
        s += 1
    b_mid, a_mid = before[p : n1 - s], after[p : n2 - s]
    if not b_mid or not a_mid:
        tag = "replace" if (b_mid and a_mid) else ("delete" if b_mid else "insert")
        return [(tag, p, n1 - s, p, n2 - s)]
    matcher = SequenceMatcher(None, b_mid, a_mid, autojunk=False)
    return [
        (tag, p + i1, p + i2, p + j1, p + j2)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]
```

## 4. تتبع الزوائد والركام البرمجي والمعماري (Bloat & Redundancy Audit)

أظهر المسح الشامل للشجرة المجردة (`AST`) ومحتويات المستودع (`13.28 MB`) وجود زوائد على ثلاثة مستويات: **الكود الميت داخل النواة**، **التكرار البنيوي بين الوحدات**، و**الترهل الحجمي في المستودع والتغليف**.

### 4.1 الكود الميت والرموز غير المستعملة في `src/arafix/`

| الموقع | الرمز البرمجي | النوع والحجم | الحالة الفعلية والتوصية |
| :--- | :--- | :--- | :--- |
| `src/arafix/hygiene.py:200-241` | `_PARTICLE_SPACE_AFTER` | `tuple[str, ...]` (`42` سطراً) | **كود ميت تماماً (`0` استخدام).** استُبدل تاريخياً بـ `_ARTICLE_PARTICLES` و`_SAFE_GLUED_FUNCTION_BOUNDARIES` وبقي في الملف؛ يجب حذفه. |
| `src/arafix/hygiene.py:246` | `_NO_COLLAPSE_SINGLE` | `frozenset` (`"اأإآةىوويف"` — مع تكرار حرف `و` مرتين!) | **غير مستخدم في أي مكان (`0` استخدام).** إما أن يُربط في `collapse_midword_spaces` لحماية الحروف المعزولة (حل `B-01`) أو يُحذف. |
| `src/arafix/order.py:251-253` | `_ARABIC_VOWEL_MARKS` | `frozenset` (`11` نقطة كود) | **كود ميت تماماً (`0` استخدام).** تعتمد `order_combining_marks` على `_SHADDA` فقط؛ يُحذف. |
| `src/arafix/order.py:698-728` | `fix_order_result` | دالة (`31` سطراً) | **كود ميت (`0` استخدام في `src/` و`tests/`)** وغير مدرج في `__all__`، وفوق ذلك يحوي خطأ استدعاء `detect_visual_order(text)` دون تطبيع؛ يُحذف. |
| `src/arafix/normalize.py:383-396` | `normalize_result` | دالة (`14` سطراً) | **غير مستخدم داخل `src/`** وغير مدرج في `__all__` (يُستدعى فقط في اختبار قديم بـ `test_arafix.py`)؛ يُحذف أو يُنقل كمساعد اختباري. |
| `src/arafix/pdf_confusions.py:87` | `THUMB_RED_CONFUSIONS` | `tuple = ()` (فارغ) | فارغ عمداً لكنه لا يزال يُدمج ويُفحص في `pdf_confusions.py:100, 171` و`evidence.py:243`؛ يُنظَّف لتبسيط الكود. |

### 4.2 التكرار البنيوي والازدواجية بين الوحدات

| المكون المكرر | المواقع المتعددة | أثر الازدواجية | الحل التوحيدي |
| :--- | :--- | :--- | :--- |
| جدول هجائن PDF (`ی/ھ/ک/ۀ`) | `normalize.py:115` (`_PDF_HOMOGLYPH_TABLE`) و`scientific.py:74` (`_HOMOGLYPH_TO_CANON`) | عند تحديث أحد الجدولين ينحرف مقياس `SHDR` عن سلوك التطبيع الفعلي | تعريف القاموس المرجعي مرة واحدة في `unicode_tables.py` (`PDF_HOMOGLYPH_MAP`) واشتقاق `str.maketrans` منه |
| فحص هوية الاتصال (`_signal_joining_forms`) | `diagnose.py:500-545` و`scientific.py:157-189` (`_joining_integrity`) | تكرار حرفي لنفس حلقة استخراج صيغ الوصل وفحص `_joins_forward(a) == _joins_backward(b)` | استخراج دالة مساعدة مشتركة `count_joining_pairs(text) -> tuple[int, int]` في `diagnose.py` |
| أنماط العناوين وعلامات الوقف | `layout.py:46-55` (`_HEADING_PREFIX`, `_TERMINAL_PUNCT`) و`rag.py:20-26` و`types.py:406` | اختلاف طفيف في علامات الوقف بين `layout.py` (تغفل `:` في `_TERMINAL_PUNCT`) و`rag.py` (تضم `:`) | توحيد الثوابت البنيوية في `layout.py` واستيرادها في `rag.py` و`types.py` |
| فئة الحركات (`_MARKS_CLASS` / `_TASHKEEL`) | `hygiene.py:252` و`pdf_confusions.py:48` و`scientific.py:54` | تكرار تعريف النطاق `\u064B-\u0655\u0670` في ثلاث وحدات منفصلة | تعريف `ARABIC_COMBINING_MARKS_RANGE` في `unicode_tables.py` كمصدر حقيقة وحيد |
| دوال المهايئات المترادفة | `arafix.fix()` و`adapters.fix_any()` و`adapters.repair_extracted()` | ثلاث دوال عامة تؤدي نفس المهمة (نداء `repair_text`) مع اختلاف نوع الإرجاع (`str` مقابل `RepairResult`) | الإبقاء على الأسماء للتوافق الخلفي مع جعل `fix_any = repair_extracted = repair_text` كإحالات مباشرة |

### 4.3 زوائد المستودع وأخطاء التغليف (`13.28 MB` مقابل `980 KB` للكود المصدري)

يمثل الكود المصدري الفعلي (`src/arafix/`) **7.2% فقط** من حجم الأرشيف (`980.9 KB` شاملةً ملفات `.pyc`)، بينما تستهلك الزوائد والملفات الثنائية **92.8%** (`12.3 MB`):

| فئة الزوائد في المستودع | الحجم الفعلي | التفصيل الفني | الإجراء التصحيحي |
| :--- | ---: | :--- | :--- |
| ملفات بايت-كود مترجمة (`__pycache__`) | `~450 KB` | وجود `20` ملفاً بصيغة `src/arafix/__pycache__/*.cpython-311.pyc` داخل الحزمة المصدرية | حذف مجلد `__pycache__` من الأرشيف وتأكيد استبعاده في أدوات التصدير |
| ملفات Wheel ثنائية في `docs/` | `159.3 KB` | `docs/wheels/arafix-1.2.0-py3-none-any.whl` مخزون داخل الشجرة المصدرية لعرض Pyodide/WASM | توليده آلياً داخل `.github/workflows/pages.yml` أثناء نشر GitHub Pages بدلاً من تخزينه ثنائياً في `git` |
| 13 ملف PDF مكرر الخط في `benchmarks/glyph_fixtures/assets/` | `5,795.6 KB` (`5.8 MB`) | كل ملف من الملفات الـ 13 حجمه `445.8 KB` لأنه يضمّن نسخة من خط `Amiri-Regular.ttf` (`421 KB`) الموجود أصلاً في `benchmarks/glyph_fixtures/fonts/`! | توليد الملفات الـ 13 عند الطلب عبر `make_fixtures.py` (يستغرق `< 0.5s`) أو استخدام تجميعة خطوط مشتركة، مما يوفر `5.8 MB` فوراً |
| 42 ملف PDF مُولَّد في `benchmarks/wiki_eval/pdfs/` | `~2,150 KB` (`2.15 MB`) | ملفات PDF مولّدة آلياً من `articles/*.gold.txt` بواسطة `make_pdfs.py` | الاحتفاظ بملفات `.gold.txt` النصية الخفيفة وتوليد الـ PDF عبر `make_pdfs.py` عند تشغيل البنشمارك |
| شعار PNG غير مضغوط (`assets/arafix-logo.png`) | `607.4 KB` | صورة شعار تُعرض بعرض `360px` في `README.md` بحجم يتجاوز نصف ميغابايت | ضغطها بصيغة WebP/PNG محسنة أو SVG ليصبح حجمها `< 35 KB` (وفر `94%`) |
| **خلل عقد `sdist` في `pyproject.toml`** | السطور `80–93` و`111` | يعلن `pyproject.toml` شحن الاختبارات في `sdist` للتحقق المستقل، لكنه يغفل `benchmarks/adversarial_bidi_corpus.json` الذي تستورده `test_architecture_invariants.py` و`test_h5_bidi_fuzz.py` مباشرة، مما يكسر `pytest` على حزمة `sdist`! كما يضع `mypy` على `python_version = "3.10"` خلافاً لعقد `>=3.9` | إضافة `@pytest.mark.skipif(not bidi_path.exists(), ...)` أو نقل `adversarial_bidi_corpus.json` إلى `tests/fixtures/`، وتوحيد `mypy` على `"3.9"` |

## 5. خارطة الطريق للوصول بالمكتبة إلى الصدارة العالمية المطلقة (World-Class SOTA Roadmap)

لتكون `arafix` المرجع العالمي الأول بلا منازع في استرجاع النصوص العربية من ملفات PDF — مع الحفاظ التام على حدودها المعلنة (صفر تبعيات في النواة، صفر تصحيح إملائي عشوائي، صفر إصلاحات كاذبة `FPR = 0`) — يوصى بتنفيذ خطة الترقية التالية على أربع مراحل متكاملة:

### المرحلة الأولى: الإغلاق الفوري للثغرات الحرجة وتصفير الانحدارات (Immediate Patch Set)

1. **تحصين `collapse_midword_spaces` (`B-01`):** منع دمج الكلمات الثنائية (`len(left) == 2`) والحروف الأبجدية المعزولة بعد كلمات التعداد، وتوسيع بادئات `ال` المقطوعة لتشمل كافة الحروف العربية (`_ARTICLE_3_PREFIXES`).
2. **إصلاح `PageResult.body_text` و`to_markdown` (`B-02`):** إرجاع `self.repair.text` في الصفحات أحادية العمود، واستخدام الأسطر المُصلحة على مستوى الصفحة عند بناء Markdown والعناوين بدلاً من إعادة استدعاء `repair_text` سطراً بسطر بلا سياق.
3. **إصلاح `separate_fused_presentation_forms` للاتجاهين المنطقي والبصري (`B-03`):** كشف اتجاه الكتلة عبر هوية الوصل، وفصل الكلمات البصرية عند الانتقال `(INITIAL | ISOLATED) → (FINAL | TA_MARBUTA)`.
4. **موازنة الأقواس وعلامات التنصيص (`B-04`) وإصلاح التشكيل في `lamalef.py` (`B-05`):** اعتماد `_fix_unbalanced_pairs` في `order.py`، وتجريد الحركات عند الاستعلام المعجمي في `lamalef.py` مع عدّ الاستبدالات عبر `subn`.
5. **تقديم `fold_pdf_homoglyphs` قبل التشخيص والعكس (`B-06`) وإصلاح `rescue_mixed_lines` (`B-07`) و`rag.py` (`B-09`).**

### المرحلة الثانية: القفزة الخوارزمية في الأداء (`2×` في السرد و`56×` في التدقيق)

1. **تفعيل `_diff_opcodes` بالاقتطاع الطرفي في `src/arafix/audit.py`:** يقضي نهائياً على عنق الزجاجة في `AuditMode.FULL` (`3,021 ms → 53 ms`).
2. **إضافة حراس الخروج المبكر المترجمة بلغة `C` (`_HAS_PF_RE.search`، `_ATTACHABLE_RE.search`، `_PUA_RE.findall`):** يختصر زمن `separate_fused_presentation_forms` و`grapheme_clusters` و`detect_pua` إلى النصف على النصوص القياسية.
3. **تمرير نتيجة `detect_visual_order` من `diagnose` إلى `repair_text` عند عدم تغير النص (`not needs_norm`):** يلغي ازدواجية مسح الاتجاه في المسار الساخن، وإلغاء الاستدعاء المزدوج لـ `document_context.rank()` في `context.py` + `evidence.py`.

### المرحلة الثالثة: فك الارتباط الأحادي بـ `PyMuPDF` وإضافة محرك استخراج احتياطي (`Extractor Fallback`)

تمتلك `arafix` عقداً معمارياً ممتازاً في `src/arafix/extractors/base.py` (`Extractor`, `RawPage`, `REGISTRY`)، لكن السجل لا يضم حالياً سوى `PyMuPDFExtractor` (`fitz`). في كثير من بيئات الإنتاج والحاويات الحكومية والـ Sandboxes (ومنها هذه البيئة ذاتها!) أو المشاريع التي ترفض رخصة **AGPL-3.0** الخاصة بـ `PyMuPDF`، تتوفر مكتبات بترخيص متسامح (MIT/BSD/Apache) مثل `pypdfium2` أو `pdfplumber`/`pdfminer.six` أو `pypdf`.
- **الحل المعماري ضمن الحدود المعلنة:** إضافة محركين اختياريين خفيفين (`PyPDFium2Extractor` و`PdfMinerExtractor`) في `src/arafix/extractors/` دون أي تبعية إلزامية، بحيث يرتب `get_extractor("auto")` المحركات حسب توفرها: `pymupdf` ← `pypdfium2` ← `pdfplumber`/`pdfminer` ← `pypdf`. هذا يحرر المكتبة من قيد ترخيص `AGPL` ويجعل `arafix.read("file.pdf")` يعمل في أي بيئة بايثون تتوفر فيها أي مكتبة PDF قياسية.

### المرحلة الرابعة: استكمال ربط `GlyphEvidence` وعتبات الثقة الكثافية (`v1.3.0`)

1. **ربط `GlyphEvidence` تلقائياً داخل `extract_pdf` عند تفعيل `enable_context_scoring=True` (البند `P4` في `TODO.md`):** البنية التحتية جاهزة ومثبتة في `evidence.py` و`benchmarks/glyph_fixtures/fusion_gate.py` (`RAR = 100%, FPR = 0`). كل ما يلزم هو تمرير تناقضات `GlyphMap` المكتشفة في الخطوط المضمّنة كـ `glyph_evidence` إلى `DocumentContext.repair()`.
2. **ترقية `confidence_mode="density"` و`rescue_mixed_lines=True` إلى الوضع الافتراضي (بعد تطبيق إصلاح `B-07`):** مما يغلق الثغرة الموثقة `W6` (تفاوت الثقة بين النداء الأول والثاني في الوضع الكلاسيكي) ويضمن ثبات الثقة (`Idempotence`) نصاً ورقماً في كافة الأوضاع.
