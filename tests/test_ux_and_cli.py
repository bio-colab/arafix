"""
Tests for UX ergonomics, top-level convenience API, and smart CLI routing (v1.1.0).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import arafix
from arafix.cli import _normalize_argv, main


class TestTopLevelErgonomics:
    def test_fix_one_liner_returns_pure_str(self):
        result = arafix.fix("\ufee3\ufeae\ufea3\ufe92\ufe8e")
        assert result == "مرحبا"
        assert isinstance(result, str)

    def test_read_pdf_one_liner_returns_pure_str(self):
        pdf_path = Path("tests/fixtures/real_pdf_narrative/file.pdf")
        if not pdf_path.exists():
            return
        text = arafix.read(pdf_path)
        assert isinstance(text, str)
        assert len(text) > 100
        assert "لبنان" in text

    def test_str_on_result_dataclasses(self):
        rep = arafix.repair_text("\ufee3\ufeae\ufea3\ufe92\ufe8e")
        assert str(rep) == "مرحبا"

        pdf_path = Path("tests/fixtures/real_pdf_narrative/file.pdf")
        if pdf_path.exists():
            doc = arafix.extract_pdf(str(pdf_path))
            assert str(doc) == doc.text
            assert str(doc.pages[0]) == doc.pages[0].text

    def test_str_on_blocks(self):
        blocks = [arafix.TextBlock(text="ﺎﺒﺣﺮﻣ", id="b1")]
        res = arafix.repair_blocks(blocks)
        assert str(res.blocks[0]) == "مرحبا"
        assert str(res) == "مرحبا"


class TestSmartCLIRouting:
    def test_normalize_argv_pdf(self):
        norm = _normalize_argv(["doc.pdf"])
        assert norm == ["extract", "doc.pdf"]

        norm_opts = _normalize_argv(["-e", "pymupdf", "doc.pdf", "-o", "out.txt"])
        assert norm_opts == ["-e", "pymupdf", "extract", "doc.pdf", "-o", "out.txt"]

    def test_normalize_argv_text(self):
        norm = _normalize_argv(["ﺎﺒﺣﺮﻣ"])
        assert norm == ["text", "ﺎﺒﺣﺮﻣ"]

    def test_normalize_argv_explicit_unchanged(self):
        assert _normalize_argv(["extract", "doc.pdf"]) == ["extract", "doc.pdf"]
        assert _normalize_argv(["diagnose", "doc.pdf"]) == ["diagnose", "doc.pdf"]
        assert _normalize_argv(["--version"]) == ["--version"]
        assert _normalize_argv([]) == []

    def test_cli_empty_shows_help(self, capsys):
        code = main([])
        assert code == 0
        captured = capsys.readouterr()
        assert "استرجاع النص العربي" in captured.out

    def test_cli_direct_text(self, capsys):
        code = main(["\ufee3\ufeae\ufea3\ufe92\ufe8e"])
        assert code == 0
        captured = capsys.readouterr()
        assert "مرحبا" in captured.out

    def test_python_module_entrypoint(self):
        proc = subprocess.run(
            [sys.executable, "-m", "arafix", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert proc.returncode == 0
        assert "1.2.0" in proc.stdout

    def test_cli_extract_markdown_and_llm(self, capsys):
        pdf_path = Path("tests/fixtures/real_pdf_narrative/file.pdf")
        if not pdf_path.exists():
            return
        code = main(["extract", str(pdf_path), "--format", "markdown"])
        assert code == 0
        captured = capsys.readouterr()
        assert "#" in captured.out

        code_llm = main(["extract", str(pdf_path), "--format", "llm", "--strip-tashkeel"])
        assert code_llm == 0
        captured_llm = capsys.readouterr()
        assert "َ" not in captured_llm.out


def test_cli_explain_text_and_json(capsys):
    import json

    from arafix.cli import main

    # 1. Text with --json
    code = main(["explain", "\ufee3\ufeae\ufea3\ufe92\ufe8e", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["text"] == "مرحبا"
    assert "normalize" in payload["stages_applied"]
    assert payload["audit"] is not None

    # 2. Text without --json (human-readable formatting)
    code_text = main(["explain", "\ufee3\ufeae\ufea3\ufe92\ufe8e"])
    assert code_text == 0
    out_text = capsys.readouterr().out
    assert "النص بعد الإصلاح: مرحبا" in out_text
    assert "المراحل المطبّقة" in out_text


def test_cli_explain_pdf(capsys):
    from pathlib import Path

    from arafix.cli import main

    pdf_path = Path("tests/fixtures/real_pdf_narrative/file.pdf")
    if not pdf_path.exists():
        return

    # PDF human-readable format
    code = main(["explain", str(pdf_path), "-p", "1"])
    assert code == 0
    out = capsys.readouterr().out
    assert "صفحة 1" in out


def test_multisite_confusion_and_glyph_evidence_in_context():
    from arafix.context import DocumentContext
    from arafix.evidence import (
        CandidateGenerator,
        CharacterConfusionModel,
        Confusion,
        GlyphEvidence,
    )

    # 1. Multi-site character confusion: جذيذ -> جديد
    gen = CandidateGenerator(
        confusion_model=CharacterConfusionModel(
            [Confusion("ذ", "د", source="ocr-dot", cost=0.25)]
        )
    )
    corpus = ("هذا كتاب جديد ومفيد " * 6) + "هذا كتاب جذيذ ومفيد"
    ctx = DocumentContext(corpus, candidate_generator=gen)
    rep = ctx.repair("هذا كتاب جذيذ ومفيد")
    assert rep.text == "هذا كتاب جديد ومفيد"
    assert rep.changed

    # 2. GlyphEvidence passed directly to DocumentContext.repair
    rep_glyph = ctx.repair(
        "هذا كتاب خذيذ ومفيد",
        glyph_evidence=[GlyphEvidence(observed="خذيذ", candidate="جديد", score=0.95)],
    )
    assert rep_glyph.text == "هذا كتاب جديد ومفيد"
