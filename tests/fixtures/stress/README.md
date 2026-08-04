# Ultra-Complex Stress Corpus (50 packages / 6 axes)

Target: **arafix ≥ 0.9.3**

| Axis | Theme | Count |
|------|--------|------:|
| 1 | Complex Mojibake & Encoding Interleaving | 9 |
| 2 | BiDi, Page Ranges & Currencies | 9 |
| 3 | Diacritics, PF, Tatweel, Lexicon | 8 |
| 4 | False-Positive Safe Guards | 12 |
| 5 | Punctuation & Parentheses | 8 |
| 6 | Performance & Latency | 4 |

## Run

```bash
# Full report (includes 10k-line package)
python scripts/stress_test_report.py --json-out reports/stress.json

# Faster (skip all perf packages)
python scripts/stress_test_report.py --skip-perf

# Skip only the 10k block
python scripts/stress_test_report.py --skip-ultra
```

## Decision gates

| Metric | Gate |
|--------|------|
| **FPR** | must be **0.00%** |
| **RAR** | must be **≥ 98%** |
| CER | reported (soft) |
| Throughput | lines/sec, ms/line |

Regenerate corpus (if needed):

```bash
python scripts/_gen_stress_corpus.py
```
