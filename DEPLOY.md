# Deploy checklist — arafix **1.0.0** → PyPI

You are shipping a **Stable** release. This file is the pre-flight checklist.

## Pre-flight (in-tree for 1.0.0)

- [x] Version `1.0.0` in `pyproject.toml` and `src/arafix/__init__.py`
- [x] `CHANGELOG.md` has `## 1.0.0`
- [x] `CITATION.cff` version + date-released updated
- [x] README badges: Stable + PyPI
- [x] Development Status classifier: Production/Stable
- [x] FLAW_01…08 green; stress corpus FPR=0, RAR=100%
- [x] `publish.yml` Trusted Publisher (OIDC) — no API token in repo
- [x] `.gitignore` excludes `dist/`, `build/`, `reports/`, caches

## Local build check

```bash
pip install -U build twine
python -m build
python -m twine check --strict dist/*
```

## Release on GitHub (triggers PyPI publish)

```bash
# from a clean main with 1.0.0 already committed
git tag v1.0.0
git push origin v1.0.0
gh release create v1.0.0 --title "1.0.0" --notes-file CHANGELOG.md
```

`publish.yml` runs on `release: published`, verifies tag == `__version__`,
runs tests, builds, then publishes via **OIDC** to the `pypi` environment
(requires reviewer approval if configured).

Manual TestPyPI dry-run: *Actions → publish → Run workflow → testpypi*.

## After publish

```bash
pip install -U "arafix[pdf]==1.0.0"
arafix --version
python -c "from arafix import repair_text; print(repair_text('\ufee3\ufeae\ufea3\ufe92\ufe8e').text)"
```

See [RELEASING.md](RELEASING.md) for pending-publisher setup on PyPI.
