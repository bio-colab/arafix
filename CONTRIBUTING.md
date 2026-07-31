# Contributing

Thanks for caring about Arabic text integrity.

## Highest-value contributions (in order)

1. **PDFs that break us** — with a short note of expected vs actual text  
2. **Layout edge cases** — multi-column, tables, headers  
3. **New extractors** — implement `Extractor` + `@register`  
4. **Stronger order signals** — pure functions in `diagnose.py`  
5. **Docs** — English or Arabic clarifications  

## Dev setup

```bash
pip install -e ".[dev]"
pytest
ruff check src tests examples
```

## Rules of the house

- **Do not invent characters** (especially CID fonts). Prefer explicit failure.
- **Do not “fix just in case.”** Every stage needs a signal.
- Prefer a new **named test** that documents a *decision*, not a line of code.
- Core stays **dependency-free**. Optional extras only.

## PR tips

- Keep diffs focused.
- Add CHANGELOG notes under a future version heading if you touch user-visible behavior.
- Run the suite before pushing.

License: MIT (see [LICENSE](LICENSE)).
