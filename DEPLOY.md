# Deploy checklist — arafix 0.9.0 → PyPI

You are shipping an **Alpha**. That is honest and correct. This file is the
short path from “green on your machine” to “live on PyPI.”

## Pre-flight (in-tree for 0.9.0)

- [x] Version `0.9.0` in `pyproject.toml` and `src/arafix/__init__.py`
- [x] `CHANGELOG.md` has `## 0.9.0`
- [x] Tests pass (`pytest`) including scientific floors + real-PDF regression
- [x] Real corpus under `tests/fixtures/real_pdf_narrative/`
- [x] English blurb on README + English `description`
- [x] `src/arafix/py.typed` (PEP 561)
- [x] MIT license, classifiers, CLI entry point, optional extras

## Your steps (need your accounts)

### 1) GitHub repo

```text
https://github.com/bio-colab/arafix   (public)
```

Push this tree to `main`. Ensure workflows exist:

- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`

### 2) GitHub Environments

Configure the **pypi** environment for Trusted Publishing (OIDC) as documented
in [RELEASING.md](RELEASING.md). A *pending* publisher does **not** reserve the
PyPI name — publish promptly after the first green release workflow.

### 3) Tag and release

```bash
# from a clean main with 0.9.0 already committed
git tag v0.9.0
git push origin main --tags
gh release create v0.9.0 --title "0.9.0" --notes-file CHANGELOG.md
```

Or let `publish.yml` build from the tag if that is how the repo is wired.

### 4) Verify install

```bash
pip install -U "arafix[pdf]==0.9.0"
arafix --version
python -c "from arafix import scientific_audit; print('ok')"
```

### 5) Optional checks before tag

```bash
pip install -e ".[dev,pdf]"
pytest -q
ruff check src tests
python -m build
twine check --strict dist/*
```

Update the README badge if you add a PyPI version shield after the first
successful upload.
