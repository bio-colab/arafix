# Integrating arafix with other tools

arafix is a **post-extraction Arabic recovery layer**. It does not need to own
your document pipeline. Pipe text through it after any extractor.

## One-liner (any tool)

```python
from arafix import repair_text, fix_any

fixed = repair_text(any_extractor(path)).text
# or
fixed = fix_any(pdfminer_text).text
```

## MarkItDown

### A) Plugin (PDF → Arabic-aware extract)

```bash
pip install "arafix[markitdown]"   # or arafix[pdf] + markitdown
```

```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=True)  # loads entry point `arafix`
result = md.convert("thesis.pdf")
print(result.markdown)  # repaired; HTML comment has confidence
```

The plugin prefers arafix’s geometric PDF path when PyMuPDF is installed.

### B) Post-process any MarkItDown result

```python
from markitdown import MarkItDown
from arafix import fix_markitdown

raw = MarkItDown().convert("doc.pdf")
fixed = fix_markitdown(raw)
print(fixed.text, fixed.diagnosis.summary(), fixed.confidence)
```

Works for DOCX/PPTX/HTML output too — anything that ends as text.

## Tables / cells (independent repair)

```python
from arafix import fix_table, repair_blocks, TextBlock

# 2D grid
print(fix_table([["مقلوب…", "OK"], ["…", "…"]]))

# explicit blocks (ids preserved)
out = repair_blocks([
    TextBlock(cell, id=f"r{i}c{j}", role="cell")
    for i, row in enumerate(rows)
    for j, cell in enumerate(row)
])
```

Each block is diagnosed alone: a reversed cell never forces reorder on a healthy neighbor.

## CLI pipes

```bash
# whole blob
markitdown thesis.pdf | arafix text

# line = block (tables exported as TSV lines, etc.)
some_table_export | arafix blocks -v
```

## pdfminer / pypdf / browser copy-paste

```python
from arafix.integrations import wrap_callable

def my_extract(path: str) -> str:
    ...

extract = wrap_callable(my_extract)
print(extract("f.pdf").text)
```

## Layout (columns / tables / headers) — 0.8.0+

```python
from arafix import extract_pdf, PipelineConfig, LayoutConfig

doc = extract_pdf("newspaper.pdf", PipelineConfig(
    layout="full",  # or auto | columns | linear
    layout_config=LayoutConfig(reading_order="rtl"),
))
print(doc.pages[0].n_columns)
for grid in doc.all_tables:
    print(grid)
```

```bash
arafix extract newspaper.pdf --layout full -v --tables
```

## What arafix will not do for you

- Perfect 3+ column magazine layouts without tuning
- OCR of scanned pages (roadmap; no fake extra)
- Invent characters for unmapped CID fonts

It **will** fix presentation forms, visual order, neutrals (with geometry extract),
mojibake, NBSP/soft-hyphen artifacts, lam-alef damage, and (0.8) multi-column
RTL reading order + simple tables — with evidence.
