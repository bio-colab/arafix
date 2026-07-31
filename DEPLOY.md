# Deploy checklist — arafix 0.8.0 → PyPI

You are shipping an **Alpha**. That is honest and correct. This file is the
short path from “green on your machine” to “live on PyPI.”

## Pre-flight (already done in-tree)

- [x] Version `0.8.0` in `pyproject.toml` and `src/arafix/__init__.py`
- [x] `CHANGELOG.md` has `## 0.8.0`
- [x] Tests pass (`pytest`)
- [x] `ruff check src tests examples`
- [x] `python -m build` + `twine check --strict dist/*`
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

*Settings → Environments → New environment*

| Name | Required reviewers |
|---|---|
| `testpypi` | optional |
| `pypi` | **yes — you** |

### 3) Pending publishers (PyPI + TestPyPI)

[PyPI → Publishing → Add pending publisher](https://pypi.org/manage/account/publishing/)

| Field | Value |
|---|---|
| Project name | `arafix` |
| Owner | `bio-colab` |
| Repository | `arafix` |
| Workflow name | `publish.yml` |
| Environment | `pypi` |

Repeat on [test.pypi.org](https://test.pypi.org) with environment `testpypi`.

> **Critical:** a pending publisher does **not** reserve the name. Configure
> then publish the same day.

### 4) Local smoke (optional but smart)

```bash
cd arafix   # package root (where pyproject.toml lives)
python -m pip install -e ".[dev]"
pytest
ruff check src tests examples
python -m build
python -m twine check --strict dist/*
```

### 5) TestPyPI

GitHub Actions → **publish** → Run workflow → target: **testpypi**

Then:

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            arafix
arafix --version
python -c "from arafix import repair_text; print(repair_text('\ufee3\ufeae\ufea3\ufe92\ufe8e').text)"
```

### 6) Real PyPI

```bash
# versions already 0.8.0 — bump only if you change code after TestPyPI
git tag v0.8.0
git push origin main --tags
gh release create v0.8.0 --title "0.8.0" --notes-file CHANGELOG.md
```

Approve the `pypi` environment in Actions. Done.

### 7) After live

```bash
pip install -U "arafix[pdf]"
arafix --version
```

Update the README badge if you add a PyPI version shield:

```markdown
[![PyPI](https://img.shields.io/pypi/v/arafix.svg)](https://pypi.org/project/arafix/)
```

## What not to claim on the PyPI page

- “Full OCR for scanned PDFs” — stage 4 is not shipped
- “Perfect every multi-column magazine” — layout is heuristic
- “Production-stable 1.0” — classifier is Alpha

Do claim: graded Arabic recovery, zero-dep core, evidence-based diagnosis,
optional PDF + layout.

## If something fails

| Symptom | Fix |
|---|---|
| Twine rejects README | Ensure README renders; re-run `twine check --strict` |
| OIDC / publisher error | Workflow name must be exactly `publish.yml` |
| Version already exists | Bump to `0.8.1` in both files + CHANGELOG |
| Name taken | See RELEASING.md rename options (`warraq`, …) |

## One-liner philosophy for the release notes

> arafix 0.8 recovers broken Arabic from native PDFs: diagnose with evidence,
> repair presentation forms / visual order / lam-alef, clean PDF artifacts,
> and read multi-column pages right-to-left — without a fake OCR dependency.
