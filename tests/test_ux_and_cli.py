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
        assert "1.1.0" in proc.stdout
