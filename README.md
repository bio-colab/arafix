<p align="center">
  <img src="assets/arafix-logo.png" alt="Arafix — إصلاح واسترجاع النص العربي من PDF" width="360">
</p>

# arafix

[![PyPI version](https://img.shields.io/pypi/v/arafix.svg)](https://pypi.org/project/arafix/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/arafix.svg)](https://pypi.org/project/arafix/)
[![Live Web Demo](https://img.shields.io/badge/Playground-Live%20WASM%20Demo-10b981?style=flat&logo=webassembly&logoColor=white)](https://bio-colab.github.io/arafix/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Status: Stable](https://img.shields.io/badge/status-stable-brightgreen)
![Typing](https://img.shields.io/badge/typing-py.typed-blue)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21733978.svg)](https://doi.org/10.5281/zenodo.21733978)

**Recover broken Arabic text from PDFs** — diagnose first, then apply a graded repair ladder. Not a single hammer, and not “just run OCR.”

> 🚀 **Try it live in your browser (100% Client-Side WebAssembly — Zero Server):** [**arafix Web Playground**](https://bio-colab.github.io/arafix/)

| | |
|---|---|
| **Core** | Zero dependencies (stdlib only) for text stages 0–2 |
| **PDF** | `pip install "arafix[pdf]"` — geometric extract + Arabic repair |
| **Layout** | Multi-column RTL, spanning banners/footnotes, simple tables (`layout=auto`) |
| **1.2.0** | SOTA Output Engineering: Multi-Format Exporters (Markdown/LLM/CSV/Pandas), Tokenomics Optimization, Heading Tree Introspection |
| **1.1.0** | SOTA Multi-Column Layout, Precision Spacing Recovery, One-liner API (`arafix.fix`/`read`), Smart CLI |
| **1.0** | Core lexicon, smart BiDi/LTR, hybrid mojibake, stress-gated (FPR=0, RAR=100%) |
| **Quality** | Cluster-aware diacritics, PDF homoglyph fold, scientific metrics (MCS/DBR/BFE/SHDR) — [metrics reference](docs/metrics.md) |
| **Hardening** | Conservative embedded-font CMap fallback, geometric-noise filtering, and solid-block Latin/Bidi protection |
| **Spacing** | Explicit PDF-space preservation and context-aware Arabic punctuation spacing |
| **Eval** | Independent Safahat book samples + manual gold, plus a 1,000-case adversarial Bidi corpus (`benchmarks/`) |
| **Status** | **Stable 1.2.0** — production-ready for native Arabic PDF recovery |

### Install

```bash
pip install arafix              # text repair only (zero dependencies)
pip install "arafix[pdf]"       # recommended — PDF extract & repair
pip install "arafix[all]"       # + fonttools (advanced CMap recovery)
```

> **Dependency guarantee:** The core package declares zero runtime dependencies (`stdlib` only). PDF and CMap support are opt-in extras. No Torch, Transformers, or OCR dependencies.

### 30-second start

#### ⚡ Fast One-Liners (حل سريع بسطر واحد)

```python
import arafix

# Fix broken Arabic string directly
clean = arafix.fix("\ufee3\ufeae\ufea3\ufe92\ufe8e")  # 'مرحبا'

# Extract & fix full Arabic PDF directly to string
text = arafix.read("thesis.pdf")

# Extract directly to structured Markdown (#, ##, tables, lists)
md = arafix.read_markdown("thesis.pdf")

# Extract ultra-clean prompt context for LLMs (up to 45% token savings)
llm_context = arafix.read_llm("thesis.pdf", strip_tashkeel=True)
```

#### 💻 Direct CLI (من الطرفية مباشرة)

```bash
# Fix a string directly
python -m arafix "ﺎﺒﺣﺮﻣ"             # → مرحبا

# Extract plain text
arafix extract thesis.pdf -o out.txt

# Extract structured Markdown
arafix extract thesis.pdf --format markdown -o out.md

# Extract token-optimized context for LLMs
arafix extract thesis.pdf --format llm --strip-tashkeel
```

#### 🔬 Detailed Graded API (تحكم كامل وتشخيص مدقق)

```python
from arafix import repair_text, extract_pdf

# Detailed repair with diagnosis and confidence
res = repair_text("صدرت المجالت العلمية")
print(res.text)             # 'صدرت المجلات العلمية'
print(res.confidence)       # 0.95
print(res.stages_applied)   # [<Stage.DIAGNOSE>, <Stage.REPAIR_LAM_ALEF>]

# Native Arabic PDF with multi-column layout detection
doc = extract_pdf("thesis.pdf")
print(doc.text)
print(doc.confidence, doc.pages[0].n_columns)
print(doc.metadata.get("producer"), doc.metadata.get("creator"))
```

```python
from arafix import reverse_visual_line

# Smart LTR: page numbers, URLs, quotes, currency, and ranges
print(reverse_visual_line("(140-125 .ص) ثحبلا عجرم"))
# → مرجع البحث (ص. 125-140)

print(reverse_visual_line("ةسارد )21 .ص("))
# → دراسة (ص. 12)

print(reverse_visual_line("»سابتقا« ةسارد"))
# → دراسة «اقتباس»

print(reverse_visual_line("(1=b?a/moc.elpmaxe//:sptth ةيبسنلا)"))
# → (https://example.com/a?b=1 النسبية)

print(reverse_visual_line(")00.052,1 DSU-( يفاصلا"))
# → الصافي (-USD 1,250.00)
```

### 🏆 SOTA Multi-Engine & Competitor Pipeline Benchmark (Objective & Reproducible)

Measured on official real-world publication ([`iraq_constitution.pdf`](tests/fixtures/real_pdf_narrative/iraq_constitution.pdf)) against human-verified gold ground-truth, comparing `arafix` against raw extractors as well as popular heuristic pipelines (`arabic_reshaper + python-bidi`) and specialized repair packages (`arabic-repair`):

| Engine / Pipeline | CER (Full) | CER (Letters Only) | WER (Word Error Rate) | Word Accuracy | Speed (ms) |
|---|---:|---:|---:|---:|---:|
| **Raw PyMuPDF (no repair)** | 66.06% | 64.89% | 99.40% | 0.60% | 112.3 ms |
| **Raw pdfplumber (no repair)** | 101.91% | 79.50% | 100.48% | 0.00% | 357.4 ms |
| **pdfplumber + arabic_reshaper + python-bidi** | 99.15% | 99.97% | 98.92% | 1.08% | 389.9 ms |
| **PyMuPDF + arabic_reshaper + python-bidi** | 97.70% | 99.97% | 101.68% | 0.00% | 143.7 ms |
| **pdfplumber + arabic-repair** | 79.04% | 71.73% | 93.50% | 6.50% | 363.9 ms |
| **PyMuPDF + arabic-repair** | 65.83% | 64.33% | 91.22% | 8.78% | 120.0 ms |
| **pdfminer.six** | 103.74% | 79.55% | 116.49% | 0.00% | 470.4 ms |
| **arafix (default)** | **2.15%** | **0.82%** | **13.48%** | **86.52%** | 315.7 ms |
| **arafix (layout-aware)** | **2.15%** | **0.82%** | **13.48%** | **86.52%** | 285.8 ms |

> **Reproduce locally:**
> ```bash
> python scripts/bench_cross_engine.py --pdf tests/fixtures/real_pdf_narrative/iraq_constitution.pdf --truth tests/fixtures/real_pdf_narrative/iraq_constitution_original.txt
> ```

```bash
arafix diagnose thesis.pdf -v
arafix extract  thesis.pdf -o out.txt
arafix extract  paper.pdf --layout full -v --tables
arafix eval     thesis.pdf --truth thesis.txt --scientific
python scripts/bench_cross_engine.py --pdf doc.pdf --truth truth.txt
python scripts/eval_unified.py --pdf thesis.pdf --truth thesis.txt -v
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

### Native Spatial RAG output

For retrieval-augmented generation pipelines, `extract_pdf_rag()` returns a deterministic JSON document whose chunks contain repaired text, page number, exact PDF coordinates when PyMuPDF provides them, structural role, and parent heading context. It uses the existing reading-order and table analysis; it does not download an embedding model, call an LLM, or add a vector-store dependency.

```python
from arafix import extract_pdf_rag

rag_json = extract_pdf_rag("thesis.pdf", max_chars=1200)
```

The same output is available after normal extraction through `DocumentResult.to_rag_json()`. The schema is `arafix.spatial-rag.v1`:

```json
{
  "id": "p2-b3-0",
  "text": "Repaired Arabic paragraph",
  "page": 2,
  "bbox": [72.0, 144.2, 510.4, 198.7],
  "role": "paragraph",
  "parent_context": ["الفصل الأول"],
  "source": "thesis.pdf",
  "metadata": {"line_count": 3}
}
```

Chunking is structure-aware rather than embedding-based: headings start a new ancestry scope, nearby lines are grouped until a geometric paragraph break or `max_chars`, and table cells become individually citeable chunks with row/column metadata. Exact paint bboxes are collected only for this opt-in RAG path; ordinary `extract_pdf()` keeps the previous output and does not retain them.

### Recovery Audit and reversible decisions

`repair_text()` keeps its historical fast path by default. For an inspectable provenance record, opt into `audit_mode="summary"` or `audit_mode="full"`:

```python
from arafix import PipelineConfig, repair_text

result = repair_text(
    "دراسة\\u00a0مقارنة المادة(١٧)",
    PipelineConfig(audit_mode="full"),
)

print(result.text)
print(result.audit.to_json())
recovered_original = result.reversible_patch.revert(result.text)
assert recovered_original == result.original
```

The audit schema is `arafix.recovery-audit.v1`. A full audit records the stage, rule, before/after span, evidence, decision, and hash-guarded reversible patch. `summary` records stage-level events without retaining changed substrings; `off` is the default and returns `audit=None`. The output text must be identical in all three modes.

Decisions are deliberately conservative. `SAFE` changes are limited to rules with explicit evidence and closed or deterministic behavior. `UNCERTAIN` records a plausible but unresolved case, and `UNSAFE` records a case for which the available text or PDF evidence is insufficient. Neither `UNCERTAIN` nor `UNSAFE` changes the text automatically. A confidence field is a rule-evidence score, not a calibrated probability; the project does not claim calibrated confidence until a separately held-out labeled corpus supports it.

| Decision | Automatic text change | Example |
|---|---:|---|
| `SAFE` | Yes | Unicode extraction cleanup, closed PDF confusion, or a decisive lam-alef repair |
| `UNCERTAIN` | No | Ambiguous lam-alef or low-density presentation forms |
| `UNSAFE` | No | Broken CMap with no reliable mapping or a missing text layer |

The repository also contains reproducible evaluation tools. `scripts/audit_corpus.py` measures no-op preservation, false repair rate, exact recovery, abstentions, and patch reversion on the existing stress corpus. `scripts/mutation_engine.py` and `scripts/run_mutation_benchmark.py` provide a seeded text-level L0 benchmark only for mutation classes supported by the current pipeline; CMap reconstruction, watermark geometry, column order, and multi-page table layout remain explicitly deferred to PDF-level fixtures. These tools are evaluation-only and add no runtime dependency.

When document-level lexicon harvesting makes a later page correction, the page audit is extended and its full patch is rebuilt from `PageResult.original` to the final `PageResult.text`. This keeps the recorded hash and reversible patch applicable to the actual page result rather than to an intermediate text.

The development gate also runs `mypy src` against the Python 3.9-compatible type contract. This is a development check only; the package still declares no runtime dependencies.

### Optional document-local Context Scoring

`DocumentContext` is an opt-in recovery layer for repeated document vocabulary, and it is now connected to the same recovery path rather than acting as a parallel spell checker. The flow is `detector → CandidateGenerator → evidence sources → EvidenceFusion → SAFE/UNCERTAIN/UNSAFE decision → repair → audit`. `DocumentContext` contributes document-local evidence; it does not authorize a repair by itself.

The dependency-free evidence layer exposes `CandidateGenerator`, `CharacterConfusionModel`, `Confusion`, `GlyphEvidence`, `NegativeEvidenceModel`, and `EvidenceFusion`. Candidates can come from document vocabulary, edit-distance-one insertion/deletion/substitution/transposition, explicitly injected character confusions, the closed PDF-confusion list, or caller-supplied glyph evidence. `CharacterConfusionModel` records observed-to-candidate substitutions with source and cost but never decides. `NegativeEvidenceModel` protects URLs, identifiers, quoted text, and actual Latin/code islands. `EvidenceFusion` is the only component that can authorize a `SAFE` repair; otherwise it records `UNCERTAIN` or `UNSAFE` and leaves the text unchanged.

The document model retains word frequencies, word bigrams, word trigrams, character trigrams, character 4-grams, and paragraph-local counts. The extra features are evidence signals, not a large external language model. Character confusions and glyph-derived candidates are opt-in inputs; no normal-character glyph correction is enabled automatically without a labeled PDF fixture.

```python
from arafix import DocumentContext, PipelineConfig, repair_text

context = DocumentContext.from_texts(["نناقش الطاقة المتجددة في العراق."] * 4)
result = repair_text(
    "نناقش الطاقة المتجدة في العراق.",
    PipelineConfig(
        context_model=context,
        enable_context_scoring=True,
        audit_mode="full",
    ),
)
assert result.text == "نناقش الطاقة المتجددة في العراق."
```

For a complete PDF, set `enable_context_scoring=True` without supplying a model; a model is then learned from the extracted pages and applied once at document scope. The feature is disabled by default and adds no runtime dependency. The same fusion decisions are recorded in `audit_mode="summary"` or `"full"`, including ranked candidates, source signals, negative evidence, and reversible patches.

The accepted mutation benchmark remains unchanged after the architectural refactor: constitution **61/61 exact**, narrative **57/57 exact**, CER/WER **0%** on both supported mutation sets, and **0/18 false repairs** on the safe gate. Clean real-document inputs remain byte-for-byte unchanged. These are seeded text mutations based on real reference texts, not a claim of labeled PDF glyph-repair performance.

To add an explicit confusion source without enabling it by accident, inject it into the pipeline:

```python
from arafix import (
    CandidateGenerator, CharacterConfusionModel, Confusion,
    DocumentContext, PipelineConfig, repair_text,
)

confusions = CharacterConfusionModel([
    Confusion("ة", "ه", source="font-specific", cost=0.7),
])
context = DocumentContext.from_texts(
    ["نناقش الطاقة المتجددة في العراق."] * 4,
    candidate_generator=CandidateGenerator(confusion_model=confusions),
)
config = PipelineConfig(
    enable_context_scoring=True,
    context_model=context,
)
result = repair_text("نناقش الطاقة المتجدة في العراق.", config)
```

The closed PDF list is similarly available through `CandidateGenerator.with_pdf_confusions()`. Glyph evidence can be supplied as `GlyphEvidence` to the generator, but it remains evidence only; without a labeled fixture proving normal-character CER/WER improvement, the default pipeline does not invent glyph-based repairs.

### Glyph Evidence status

PyMuPDF already exposes optional glyph ID, font, size, sequence, and bounding-box evidence, and the embedded-font CMap layer can resolve many glyph IDs. A normal-character correction rule was **not** enabled in this release: the repository has no labeled PDF fixture where a wrong Unicode character is paired with a known correct glyph shape/identity, so no CER/WER gain can be claimed for that task. The library therefore preserves the conservative behavior and does not guess from glyph shape alone.

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
| Two columns mixed | Line-joined gutters | layout (auto) |
| Empty / PUA soup | Broken ToUnicode / scan | 3 / 4 (OCR not shipped) |

### Configuration highlights

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

Further reading: [docs/metrics.md](docs/metrics.md) (all 10 quality metrics: definitions, gates, measured values, reproduction commands) · [benchmarks/optin_field](benchmarks/optin_field/) (measured evidence for the opt-in `rescue_mixed_lines` / `confidence_mode` features and the documented default decision) · [DEPLOY.md](DEPLOY.md) · [CHANGELOG.md](CHANGELOG.md) · [RELEASING.md](RELEASING.md) · [CITATION.cff](CITATION.cff) · [PR #3](https://github.com/bio-colab/arafix/pull/3) · [PR #5](https://github.com/bio-colab/arafix/pull/5) · [PR #7](https://github.com/bio-colab/arafix/pull/7)



---

# arafix — التوثيق العربي

**arafix** مكتبة بايثون لاسترجاع النص العربي من ملفات PDF الأصلية التي تحتوي على طبقة نص، حتى عندما يكون النص المستخرج معكوس الترتيب، أو مخزناً في صورة رسومية، أو متأثراً بخلل في `ToUnicode` أو بتبعثر علامات الترقيم والحركات.

> **الفكرة الأساسية:** لا تطبق arafix إصلاحاً عشوائياً على كل نص عربي. تشخّص نوع الخلل أولاً، ثم تطبق المعالجة المناسبة فقط عندما تتوفر قرينة كافية. وإذا كان الدليل غير كافٍ، تمتنع المكتبة عن التخمين وتسجل الحالة بدلاً من تغيير النص.

> **الخط الفاصل الرسمي (مبدأ مثبت باختبارات H15):**
>
> **استرجاع الترميز ≠ تصحيح لغوي.**
>
> ‏arafix يستعيد ما كان في الترميز — انعكاساً وأشكال عرض وموجيبيك وCMap — **ولا يصحّح ما كتبه المؤلف**. «المجالت» قد تكون خطأ استخراجٍ لرباط لا-ألف، وقد تكون النص الأصلي نفسه؛ ولذلك:
>
> * نصٌ سليمُ الترميزِ خاطئٌ لغوياً («المكتبه»، «فى»، «هاذا») يمر **بلا أي مساس** افتراضياً.
> * المنطقة الرمادية الوحيدة (انقلاب لا-ألف) مقيدة بقاعدة مغلقة من فئة عيوب الاستخراج + معجم مُثبت + تدقيق مسجل، وبمفتاحَي إيقاف (`enable_lam_alef_repair` / `use_core_lexicon`).
> * التصحيح السياقي موجود لكنه **opt-in صريح** (`enable_context_scoring`) يحتاج إجماع أدلة مستقلة (`EvidenceFusion`).
> * لا يوجد ولا سيُنشأ مفتاح «تصحيح إملائي عام» في الواجهة — وأي اقتراح به يجب أن يُرفض بقرار موثق يعدّل `tests/hardening/test_h15_mission_boundary.py`.

هذه المكتبة موجهة إلى من يعمل على **الكتب العربية، والأبحاث، والوثائق الحكومية، وملفات PDF المصدرة من Word أو InDesign، وأنظمة الفهرسة وRAG**. وهي ليست محرك OCR؛ فإذا كان الملف صورة ممسوحة بلا طبقة نص، تكشف arafix ذلك ولا تدّعي أنها تستطيع استعادة ما لم يُحفظ في الملف.

---

## قبل أن تبدأ: ما نوع ملفك؟

تعمل arafix أساساً مع **PDF أصلي يحتوي على نص قابل للاستخراج**. أما PDF الممسوح ضوئياً، أو الصفحة التي لا تحتوي على طبقة نص، فتحتاج إلى OCR خارجي قبل تمرير النص إلى arafix.

| حالة الملف | ما الذي تفعله arafix؟ | النتيجة المتوقعة |
|---|---|---|
| PDF عربي أصلي بطبقة نص | تقرأ تيار الرسم، وتشخّص الخلل، ثم تعيد ترتيب النص وتطبّعه | استرجاع عربي قابل للقراءة مع الحفاظ على الأدلة |
| PDF يحتوي على نص معطوب أو معكوس | تطبق درجات الإصلاح المناسبة، مع حماية الأرقام واللاتينية والتشكيل | نص عربي أوضح، من دون عكس الجزر اللاتينية |
| PDF ممسوح ضوئياً بلا نص | تكشف غياب طبقة النص | تحتاج إلى OCR خارجي؛ OCR غير مضمّن في arafix |
| CMap تالفة أو خط CID بلا خريطة موثوقة | تحاول الاسترجاع المحافظ عند توفر دليل من الخط والجليف | تمتنع إذا لم توجد خريطة يمكن الدفاع عنها |

---

## التثبيت

النواة النصية تعمل بالمكتبة القياسية فقط، ولا تضيف أي تبعية تشغيلية. استخدم الإضافة الاختيارية الخاصة بـPDF عندما تريد قراءة الملفات مباشرة.

```bash
# إصلاح النصوص فقط — بلا تبعيات تشغيلية إضافية (مكتبة قياسية فقط)
pip install arafix

# قراءة PDF واستخراج النص منه — الخيار الموصى به
pip install "arafix[pdf]"

# دعم CMap والخطوط المضمّنة في المراحل المتقدمة
pip install "arafix[all]"
```

للتأكد من أن نسخة المصدر تعمل في بيئتك:

```bash
git clone https://github.com/bio-colab/arafix
cd arafix
pip install -e ".[dev]"
pytest -q
```

> **ضمان التبعيات:** لا تستخدم المراحل النصية الأساسية OCR أو LLM أو Torch أو Transformers. وتظل إضافات PDF وCMap اختيارية.

---

## تجربة سريعة

### إصلاح نص عربي مستخرج بشكل خاطئ

```python
from arafix import repair_text

result = repair_text("ﻣﺮﺣﺒﺎ")
print(result.text)  # مرحبا
```

يمكنك فحص سبب الإصلاح ودرجته بدلاً من الاكتفاء بالنص الناتج:

```python
print(result.diagnosis.summary())
print(result.confidence)
print(result.notes)
```

### استخراج PDF عربي أصلي

```python
from arafix import extract_pdf

document = extract_pdf("thesis.pdf")

print(document.text)
print(document.confidence)
print(len(document.pages))
print(document.metadata.get("producer"), document.metadata.get("creator"))

```

### 📊 محرك التصدير المنظم ودعم الذكاء الاصطناعي (Multi-Format & LLMs)

توفر `arafix` محرك تصدير مهيكل مدمج يرفع كفاءة استخراج المستندات للأبحاث، والمشاريع، وأنظمة الـ RAG، ونماذج اللغة الكبيرة (LLMs):

#### 1. استخراج فوري بصيغة Markdown مهيكلة:
يترجم العناوين آلياً إلى وسوم `#` و `##` و `###` بحسب هرمية الخط، ويرتب القوائم والجداول في تدفق متناسق:
```python
import arafix

# قراءة سريعة بسطر واحد
markdown = arafix.read_markdown("report.pdf")

# أو عبر كائن الوثيقة المستخرجة
doc = arafix.extract_pdf("report.pdf")
print(doc.to_markdown())

# استعراض هرمية العناوين المكتشفة مع درجاتها وأرقام صفحاتها
for title, level, page in doc.headings:
    print(f"P{page} H{level}: {title}")
```

#### 2. تصدير فائق الكفاءة لـ LLMs (توفير حتى 45% من التوكنز):
يحذف الترويسات والتذييلات وأرقام الصفحات المتكررة، يوصل الجمل المنكسرة عبر حواف الصفحات، ويزيل الكشيدة (`ـ`)، مع خيار تجريد التشكيل (`strip_tashkeel=True`) لمنع هدر التوكنز في نماذج مثل GPT-4 و Claude و Gemini:
```python
# سياق نقي مهيأ مباشرةً لنافذة السياق (Context Window)
prompt_context = arafix.read_llm("report.pdf", strip_tashkeel=True)
```

#### 3. كائن الجداول الغني `TableResult`:
يتيح تصدير الجداول المستخرجة مباشرة إلى صيغ Markdown و CSV و Dict و Pandas:
```python
doc = arafix.extract_pdf("tables.pdf")

for tbl in doc.tables:
    print(tbl.to_markdown())   # جدول Markdown قياسي
    print(tbl.to_csv())        # نص CSV جاهز للفتح
    records = tbl.to_dict()    # [{'الاسم': 'أحمد', ...}]
    df = tbl.to_dataframe()    # pandas.DataFrame مباشرة!
```

للتشخيص قبل الاستخراج أو الإصلاح:

```bash
arafix diagnose thesis.pdf -v
arafix extract thesis.pdf -o thesis.txt
arafix extract thesis.pdf --layout full --tables -o thesis.md
arafix eval thesis.pdf --truth thesis.txt --scientific
```

ولتشغيل أدوات القياس المعيارية والمقارنة متعددة المحركات:

```bash
# مقارنة أداء arafix ضد PyMuPDF الخام و pdfplumber و pdfminer
python scripts/bench_cross_engine.py --pdf thesis.pdf --truth thesis.txt

# فحص المقاييس العلمية الشاملة (CER, Letters-CER, WER, MCS, DBR)
python scripts/eval_unified.py --pdf thesis.pdf --truth thesis.txt --scientific -v
```

### 🏆 المقارنة المعيارية متعددة المحركات (Cross-Engine Benchmark)

مقاسة على وثيقة حكومية رسمية واقعية ([`iraq_constitution.pdf`](tests/fixtures/real_pdf_narrative/iraq_constitution.pdf)) مقابل حقيقة أرضية مدققة بشرياً:

| المستخرج / المحرك | CER (كامل) | CER (حروف فقط) | WER (خطأ الكلمات) | دقة الكلمات (Word Acc) | السرعة (ms) |
|---|---:|---:|---:|---:|---:|
| **Raw PyMuPDF (خام بدون إصلاح)** | 66.06% | 64.89% | 99.40% | 0.60% | 115.5 ms |
| **pdfplumber** | 101.91% | 79.50% | 100.48% | 0.00% | 383.3 ms |
| **pdfminer.six** | 103.74% | 79.55% | 116.49% | 0.00% | 484.3 ms |
| **arafix (الافتراضي)** | **3.05%** | **0.82%** | **17.21%** | **82.79%** | 300.8 ms |
| **arafix (بإدراك التخطيط)** | **3.05%** | **0.82%** | **17.21%** | **82.79%** | 243.0 ms |

> [!NOTE]
> تحقق `arafix` نسبة خطأ في استرجاع الحروف المجردة تبلغ **0.82% فقط** (أقل من 1%)، ودقة كلمات **82.79%**، متفوقة بوضوح حاسم على كافة المستخرجات التقليدية.

---

## ما المشكلات التي تعالجها المكتبة؟

تتعامل arafix مع فئات مختلفة من الأعطال، ولا تستخدم القاعدة نفسها لكل حالة. يوضح الجدول التالي أمثلة عملية على الأعراض والمرحلة المسؤولة عنها.

| العرض في النص المستخرج | السبب المعتاد | المعالجة |
|---|---|---|
| `ﻣﺮﺣﺒﺎ` أو أشكال عربية رسومية | تخزين الحروف في نطاقات العرض العربية | تطبيع موجّه للأشكال العربية |
| `ا ب ح ر م` أو سطر عربي معكوس | ترتيب بصري بدلاً من الترتيب المنطقي | إعادة ترتيب عنقودية تحمي الأرقام واللاتينية |
| `()مقدمة` بدلاً من `(مقدمة)` | تبعثر الأقواس والمحايدات في محرك الاستخراج | قراءة هندسية ومرآة الأقواس |
| `ج[ هنا-الفقرة ]أ` | خلط الجزر العربية واللاتينية والمحايدات | حماية LTR/Bidi للكتل الصلبة |
| `Ø§Ù„Ù…` | فك UTF-8 باستخدام Latin-1 أو CP1256 | إصلاح موجيبيك ضمن نافذة محدودة |
| `المجالت` أو `االنترنيت` | خلل في رباط لام-ألف أو فكّه قبل ترتيب السطر | إصلاح حتمي أو معجم مغلق، لا تخمين إملائي عام |
| `نشُرت` بدلاً من `نُشرت` | انفصال الحركة عن عنقودها أو عكس المحارف منفردة | ربط عنقودي للحركات أثناء الاستخراج |
| `ی` أو `ھ` بدلاً من `ي` أو `ه` | اختلاف `ToUnicode` في الخط المضمّن | طيّ هجائن PDF عند تفعيله |
| أعمدة مختلطة أو ترويسة مكررة | فقدان البنية المكانية | تحليل التخطيط والأعمدة والترويسات |
| رموز PUA أو نص فارغ | CMap غير موثوقة أو غياب طبقة النص | استرجاع CMap محافظ أو تقرير الحاجة إلى OCR |

لا تحاول المكتبة اختراع تشكيل غير موجود في طبقة PDF، ولا تحوّل كل كلمة نادرة إلى كلمة أخرى. هذه الحدود جزء من التصميم وليست نقصاً مخفياً.

---

## كيف تعمل arafix؟

يمر النص في سلم إصلاح متدرج. تبدأ المكتبة بالتشخيص، ثم تطبق المراحل التي تدعمها الأدلة الموجودة في النص أو في PDF، وتترك المراحل غير المبررة دون تغيير.

```text
PDF أو نص خام
    │
    ├─ الاستخراج الهندسي من تيار الرسم عند التعامل مع PDF
    │
    ├─ 0  التشخيص: موجيبيك، أشكال عرض، PUA، ترتيب بصري، ضوضاء
    │
    ├─ 1a التطبيع الآمن: تنظيف Unicode دون كسر العناقيد
    │
    ├─ 2  إعادة الترتيب: عربي بصري ← منطقي، مع حماية LTR/Bidi
    │
    ├─ 1b إكمال التطبيع: الرباطات والحركات التي يجب تأجيلها
    │
    ├─ CMap اختياري: استرجاع محافظ من الخط والجليف عند توفر الدليل
    │
    ├─ Context اختياري: أدلة محلية للوثيقة داخل محرك القرار نفسه
    │
    └─ audit اختياري: القرار والدليل والرقعة القابلة للعكس
```

من القرارات المعمارية المهمة أن arafix لا تعكس السلسلة كاملة باستخدام `text[::-1]`. فالأرقام واللاتينية تبقى من اليسار إلى اليمين، والأقواس لها سلوك مرآتي، والحركات يجب أن تتحرك مع الحرف الأساسي لا مع موضعها المنفرد. لذلك تعمل المكتبة على **عناقيد نصية وكتل اتجاهية**، لا على محارف معزولة فقط.

كما أن استخراج PDF الافتراضي يقرأ `get_texttrace()` وتيار الرسم، لا مخرج `get_text()` المرتب مسبقاً من محرك MuPDF. هذا يحافظ على `glyph_id` وfont وbbox وتسلسل الرسم عندما تكون متاحة، ويمنع محركاً آخر من إخفاء العلاقة الهندسية التي تحتاجها مرحلة الإصلاح.

---

## الاستخدام من النص أو من PDF

### إصلاح نص كامل

```python
from arafix import repair_text

result = repair_text(broken_text)

print(result.text)
print(result.diagnosis.summary())
print(result.confidence)
print([stage.value for stage in result.stages_applied])
```

### استخراج بنية PDF

```python
from arafix import PipelineConfig, extract_pdf

config = PipelineConfig(
    layout="auto",       # استخدم "columns" أو "full" عند الحاجة
    audit_mode="off",    # المسار الأسرع؛ هذا هو الافتراضي
)
document = extract_pdf("thesis.pdf", config)

for page in document.pages:
    print(page.page_number, page.text)
```

يدعم مسار التخطيط الأعمدة العربية من اليمين إلى اليسار، والترويسات والتذييلات، وبعض الجداول. يبقى الكشف إحصائياً؛ فإذا كانت الصفحة تحتوي على أعمدة متداخلة جداً أو جدولاً بلا فواصل هندسية واضحة، قد تحتاج إلى ضبط `LayoutConfig` أو مراجعة النتيجة يدوياً.

عند استخدام محرك PyMuPDF، تحفظ `DocumentResult.metadata` حقلي `producer` و`creator` إذا سجلهما ملف PDF. هذه البيانات وصفية للفرز والتحليل فقط؛ لا تغيّر التشخيص ولا تفعّل أو تعطل أي إصلاح تلقائياً. قد تكون الحقول فارغة أو غير موثوقة، ولذلك لا تُعامل كهوية قاطعة لبرنامج الإنتاج.

### التشخيص وحده

```python
from arafix import diagnose

diagnosis = diagnose(text)
print(diagnosis.defects)
print(diagnosis.confidence)
for evidence in diagnosis.evidence:
    print(evidence)
```

درجة الثقة هنا **درجة قوة دليل القاعدة** وليست احتمالاً إحصائياً معايراً. لا ينبغي تفسير `0.94` على أنه «احتمال صحة يساوي 94%» ما لم يتوفر corpus مستقل مُعنون يثبت المعايرة.

---

## إخراج Spatial RAG

إذا كنت تبني نظام بحث أو RAG، يمكنك طلب مخرج مكاني منظم بدلاً من النص المسطح فقط:

```python
from arafix import extract_pdf_rag

rag_json = extract_pdf_rag("thesis.pdf", max_chars=1200)
print(rag_json)
```

يمكن أيضاً استعمال `document.to_rag_json()` بعد `extract_pdf()`. كل chunk يحمل النص المسترد، ورقم الصفحة، و`bbox` الدقيق عندما يوفره محرك PDF، والدور البنيوي، وسياق العنوان الأبوي.

```json
{
  "schema": "arafix.spatial-rag.v1",
  "chunks": [
    {
      "id": "p2-b3-0",
      "text": "فقرة عربية مستردة",
      "page": 2,
      "bbox": [72.0, 144.2, 510.4, 198.7],
      "role": "paragraph",
      "parent_context": ["الفصل الأول"],
      "source": "thesis.pdf"
    }
  ]
}
```

هذا التقسيم حتمي ومبني على العناوين والفواصل الهندسية وحد المحارف، وليس على embedding model أو LLM أو vector store. أما `extract_pdf()` العادي فلا يحتفظ بالـbbox الدقيق إلا إذا طلبت مسار RAG المكاني، ولذلك لا تتغير كلفة المسار العادي بلا سبب.

---

## التدقيق والقرارات القابلة للعكس

المسار الافتراضي لا ينشئ سجلاً إضافياً. إذا احتجت إلى معرفة ما الذي تغير ولماذا، فعّل التدقيق:

```python
from arafix import PipelineConfig, repair_text

result = repair_text(
    "دراسة\u00a0مقارنة المادة(١٧)",
    PipelineConfig(audit_mode="full"),
)

print(result.text)
print(result.audit.to_json())
assert result.reversible_patch.revert(result.text) == result.original
```

يستخدم التدقيق العقد `arafix.recovery-audit.v1`:

| الوضع | ما الذي يسجله؟ | متى تستخدمه؟ |
|---|---|---|
| `off` | لا يسجل audit؛ وهو الافتراضي | الإنتاج والمسار الأسرع |
| `summary` | يسجل المراحل والقرارات دون حفظ المقاطع المتغيرة كاملة | المراقبة والتشخيص الخفيف |
| `full` | يسجل قبل/بعد، القاعدة، الدليل، الهاش، والرقعة القابلة للعكس | التحقيق والتدقيق وإعادة الإنتاج |

هناك ثلاثة قرارات ممكنة. `SAFE` يغير النص عندما يكون الدليل صريحاً والقاعدة مغلقة أو حتمية. `UNCERTAIN` يسجل حالة معقولة لكنها غير محسومة ولا يغير النص. `UNSAFE` يعني أن الأدلة المتاحة غير كافية أو أن طبقة النص غير موثوقة؛ ولا يغير النص أيضاً.

---

## Context Scoring والأدلة المتعددة

`DocumentContext` طبقة اختيارية مرتبطة بمحرك الاسترجاع نفسه، وليست مصححاً لغوياً منفصلاً. مسار القرار هو:

```text
detector
  ↓
candidate generation
  ↓
DocumentContext + CharacterConfusion + GlyphEvidence + NegativeEvidence
  ↓
EvidenceFusion
  ↓
SAFE / UNCERTAIN / UNSAFE
  ↓
repair + audit
```

يبني `DocumentContext` نموذجاً صغيراً من الوثيقة نفسها: تكرار الكلمات، وتجاورات الكلمات، وتسلسلات الكلمات الثلاث، وcharacter trigrams وcharacter 4-grams، والمفردات المحلية داخل الفقرات. لا يحتاج إلى LLM أو نموذج لغوي كبير.

تولد `CandidateGenerator` المرشحين ولا تحكم بصحتهم. ويمكن أن تأتي المرشحات من معجم الوثيقة، أو من حذف/إضافة/استبدال/تبديل محرف واحد، أو من confusion صريح يحقنه المستعمل، أو من قائمة PDF مغلقة، أو من `GlyphEvidence`. أما `CharacterConfusionModel` فيحفظ مصدر كل confusion وكلفته، ولا يقرر وحده.

تحمي `NegativeEvidenceModel` الجزر اللاتينية الفعلية، والروابط، والمعرفات، والنصوص المقتبسة، والمصطلحات التي ينبغي إبقاؤها كما هي. ولا يملك أي detector منفرد صلاحية فرض الإصلاح؛ وحده `EvidenceFusion` يستطيع إصدار `SAFE` عندما تتفق الأدلة المستقلة.

```python
from arafix import DocumentContext, PipelineConfig, repair_text

context = DocumentContext.from_texts(
    ["نناقش الطاقة المتجددة في العراق."] * 4
)

result = repair_text(
    "نناقش الطاقة المتجدة في العراق.",
    PipelineConfig(
        context_model=context,
        enable_context_scoring=True,
        audit_mode="full",
    ),
)

assert result.text == "نناقش الطاقة المتجددة في العراق."
```

عند استخراج PDF كامل، يمكنك تفعيل `enable_context_scoring=True` من دون تمرير نموذج؛ فتتعلم المكتبة النموذج من صفحات الوثيقة ثم تطبقه على مستوى الوثيقة. تبقى الميزة مطفأة افتراضياً، ولا تضيف تبعية تشغيلية.

المقياس المقبول الحالي لهذا المسار هو **61/61** استرجاعاً exact في مجموعة constitution و**57/57** في narrative، مع CER وWER يساويان صفراً في مجموعتي التحوير المدعومتين و**0/18** false repairs في بوابة النصوص السليمة. هذه قياسات لتحويرات نصية مشتقة من نصوص مرجعية حقيقية، وليست ادعاءً بأن كل PDF سيحصل على النتيجة نفسها.

---

## Glyph Evidence: ما الذي نفع وما الذي لم يُعتمد؟

توفر arafix أدلة اختيارية من `glyph_id` واسم الخط والحجم وتسلسل الرسم و`bbox`، كما تستطيع طبقة CMap استرجاع بعض glyphs من الخطوط المضمّنة. لكن التصحيح التلقائي لمحرف عربي عادي اعتماداً على «شكل الجليف» لم يُفعّل.

السبب منهجي: لا توجد في المستودع fixture PDF معلّمة تربط glyph خاطئاً بحرفه الصحيح وتثبت خفض CER/WER بعد التصحيح. لذلك يبقى Glyph Evidence مصدراً للمرشحين والدليل، ولا يملك وحده صلاحية اختراع إصلاح. كما أن إعادة ربط التشكيل عبر مصفوفات PDF الهندسية لم تُعتمد بعد؛ الاختبارات الحالية لم تثبت مكسباً على PDF حقيقي، وبعض variants أدت إلى regression.

هذه المحافظة مقصودة. إذا لم تتوفر خريطة CMap أو fixture معلّمة أو دليل هندسي كافٍ، تقول المكتبة ذلك بدلاً من إنتاج نص يبدو سليماً لكنه غير موثوق.

---

## إعدادات مهمة

```python
from arafix import (
    NormalizeConfig,
    PipelineConfig,
    ReorderConfig,
    repair_text,
)

config = PipelineConfig(
    use_core_lexicon=True,
    enable_lam_alef_repair=True,
    normalize=NormalizeConfig(
        strip_diacritics=False,   # الافتراضي: استرجاع النص لا حذف التشكيل
        unify_alef=True,           # مناسب للفهرسة عند طلبه صراحة
        fold_pdf_homoglyphs=True,
    ),
    reorder=ReorderConfig(
        smart_ltr_restore=True,
        normalize_page_ranges=True,
        repair_ltr_parens=True,
        relocate_sentence_punct=True,
    ),
)

result = repair_text(broken_text, config)
```

لا تفعّل `strip_diacritics` أو طيّ الهجائن إذا كنت تحتاج إلى المحافظة على الفروق الأصلية بين العربية والفارسية والأوردية. استخدم `lexicon=` عندما تملك معجماً خاصاً بالمجال، ولا تعتبر كل تصحيح معجمي صالحاً خارج سياقه.

---

## القياس والنتائج المنشورة في المشروع

الاختبارات لا تكتفي بأن «النص يبدو جيداً». يستخدم المشروع عشرة مقاييس موثقة في
[`docs/metrics.md`](docs/metrics.md) — المرجع الكامل بالتعريفات والصيغ والبوابات
وقيم اليوم وأوامر إعادة الإنتاج. خلاصتها:

| الطبقة | المقاييس |
|---|---|
| الخطأ النصي | **CER** و**WER** (والـ**LE** — مسافة ليفنشتاين المُطبَّعة، وهي ≡ CER بالبناء؛ الدقة `accuracy = 1 − CER`) |
| العلمية | **MCS** استمرارية الهيكل الحرفي · **DBR** مخزون التشكيل ودقة التصاقه (= «دقة التشكيل») · **BFE** إنتروبيا تدفّق الاتجاه مقابل المرجع · **SHDR** انجراف هجائن PDF |
| السلامة | **FPR** إصلاح كاذب على النصوص السليمة (بوابة صارمة = 0) · **RAR** استرجاع تام ≥ 98% |
| الاتجاه | BFE Δref ≤ 0.02 + corpus خصمي 1000/1000 + fuzzing |

البوابات المثبتة (لا تُخفَّض بلا قرار موثّق): MCS ≥ 0.99 · DBR ≥ 0.99 (attach ≥ 0.99)
· SHDR = 0 · BFE Δref ≤ 0.02 — انظر `tests/test_scientific_floors.py`.

وتوجد corpus حقيقية وملفات stress وbenchmark للـBidi داخل المستودع.

| المجال | النتيجة الموثقة |
|---|---:|
| constitution mutation benchmark | 61/61 exact، وCER/WER = 0% |
| narrative mutation benchmark | 57/57 exact، وCER/WER = 0% |
| safe corpus | 0/18 false repairs في التشغيلة الكاملة¹، وFPR = 0% |
| Latin/Bidi adversarial corpus | 1000/1000 حالة ناجحة |
| PDF الدستور الحقيقي | تحسن CER/WER الموثق من 3.486% / 20.939% إلى 3.092% / 17.208% بعد إصلاحات المسافات والبنية |
| المسار الافتراضي | لا يتلقى كلفة Context أو RAG أو audit إلا عند تفعيلها |

¹ **سياق العدّاد:** corpus الإجهاد يحتوي 18 حالة must-not-change بينها حالة
`perf_safe` واحدة (A6-04). عند التشغيل بـ`--skip-perf` أو عبر `audit_corpus.py`
يصبح العداد 17 لأن تلك الحالة تُستبعد مع كتل الأداء. الرقمان صحيحان لوضعيهما؛
التفصيل في [`docs/metrics.md`](docs/metrics.md) §3.2.

هذه الأرقام مرتبطة بالـfixtures والنسخة وإعدادات القياس الموجودة في المستودع. لا ينبغي تعميمها على كل ملفات PDF من دون تشغيل `arafix eval` على ملفاتك مع نص مرجعي.

---

## الاختبارات

من جذر المستودع:

```bash
pytest -q
pytest tests/test_scientific_floors.py -v
pytest --doctest-modules src/arafix
ruff check src tests examples scripts
mypy src
```

كل اختبار يثبت عقداً أو قراراً، وليس مجرد تنفيذ داخلي. توجد أيضاً أدوات تقييم قابلة لإعادة التشغيل في `scripts/` لقياس الحفاظ على النص السليم، وFalse Repair Rate، والاسترجاع الحرفي، والامتناع، ونجاح عكس الرقعة.

تظل بعض الجوانب خارج ادعاء المحاكاة النصية، مثل إعادة بناء CMap كاملة، وضوضاء العلامات المائية من PDF، وترتيب الأعمدة المعقدة، والجداول الممتدة عبر صفحات. هذه تحتاج إلى fixtures PDF مستقلة، ولا يصح استنتاج نجاحها من اختبار نصي فقط.

---

## حدود معلنة بوضوح

لا تنفذ arafix OCR، ولا توجد حزمة `arafix[ocr]`. فإذا كان الملف صورة ممسوحة، استخدم OCR خارجياً ثم مرر النص إلى arafix عند الحاجة.

قد تعجز المرحلة المتقدمة عن الخطوط CID ذات الأسماء الداخلية غير الدالة. في هذه الحالة تسجل المكتبة انخفاض الثقة أو الامتناع، ولا تخترع Unicode من رقم مثل `cid1234`.

كاشف الاتجاه يستند إلى شواهد ودرجات، وليس حكماً لغوياً مطلقاً. كما أن إصلاح لام-ألف يحسم الحالات الحتمية، بينما تحتاج الحالات الملتبسة إلى معجم النواة أو معجم المستخدم أو Context الوثيقة؛ لا تستخدم المكتبة spell checker عاماً.

تدعم المكتبة الأعمدة والجداول الأساسية عبر `layout="auto"`, `layout="columns"`, و`layout="full"`. لكن الصفحات ذات الأعمدة المتداخلة جداً أو الجداول التي لا تحمل فواصل مكانية واضحة قد تحتاج إلى ضبط يدوي ومراجعة.

لا تضيف المكتبة تشكيلاً غائباً عن طبقة PDF، ولا تزعم أن Glyph Evidence أو إعادة ربط الحركات حلّ مثبت لكل ملفات PDF. ما لا يمكن قياسه على fixture معلّمة يبقى خارج السلوك الافتراضي.

---

## توسيع المشروع

لإضافة مستخرج جديد، طبّق عقد `Extractor` وسجله:

```python
from arafix.extractors import Extractor, RawPage, register

@register
class PdfMinerExtractor(Extractor):
    name = "pdfminer"

    @classmethod
    def available(cls) -> bool:
        try:
            import pdfminer  # type: ignore[import-not-found]
            return True
        except ImportError:
            return False

    def pages(self, path):
        # أعد RawPage لكل صفحة.
        ...

    def font_bytes(self, path):
        return {}
```

بعد ذلك يمكن اختيار المستخرج عبر `PipelineConfig(extractor="pdfminer")`. ولإضافة كاشف جديد، أضف defect وevidence واختباراً يثبت القرار، لا اختباراً يثبت أن سطراً بعينه نُفّذ.

---

## خارطة الطريق

المراحل الأساسية الحالية مستقرة: التشخيص، التطبيع الموجه، إعادة ترتيب RTL/LTR، استخراج PDF الهندسي، CMap المحافظ، التخطيط البنيوي، التدقيق القابل للعكس، والإخراج المكاني لـRAG.

أما مطابقة شكل الجليف بصرياً، وغلاف OCR، ومحرّكات استخراج إضافية، وحزمة PDF مرجعية أوسع، وإخراج PDF قابل للبحث بالنص المصحح، فهي أعمال مستقبلية لا تُعد منجزة حتى تتوفر fixtures وقياسات تثبت فائدتها. معيار المشروع هو: **أي إضافة لا تخفض CER/WER أو لا تحسن قابلية الاستخدام بوضوح، أو ترفع False Repair Rate أو تثقل المسار بلا فائدة، تُرفض أو تبقى اختيارية.**

---

## المساهمة

أفضل مساهمة عملية هي ملف PDF عربي حقيقي يمكن توزيعه أو اختبارُه، مع النص المرجعي والخلل المتوقع، ثم حالة اختبار صغيرة توضّح القرار المطلوب. كما نرحب بمستخرج جديد يلتزم بعقد `Extractor`، أو بدليل هندسي قابل لإعادة الإنتاج، أو بتحسين يمر عبر الاختبارات والقياسات دون تبعيات إجبارية.

## الاستشهاد

إذا استخدمت arafix في عمل أكاديمي، استخدم بيانات الاستشهاد الموجودة في [`CITATION.cff`](./CITATION.cff)، أو:

```bibtex
@software{sharar_arafix_2026,
  author  = {Sharar, Elias},
  title   = {{arafix: Evidence-Based Repair of Broken Arabic Text in Native PDFs}},
  year    = {2026},
  version = {1.2.0},
  doi     = {10.5281/zenodo.21733978},
  url     = {https://github.com/bio-colab/arafix},
  license = {MIT}
}
```

## الترخيص

المشروع مرخص بموجب MIT. راجع ملف [`LICENSE`](./LICENSE) للتفاصيل.

