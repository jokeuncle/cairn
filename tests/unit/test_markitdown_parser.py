"""Tests for optional MarkItDown-backed ingestion."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from cairn.core.errors import ParseError
from cairn.ingest import MarkItDownParser, parser_for_path, supported_extensions


class TestDispatch:
    def test_parser_for_office_extension(self, tmp_path: Path) -> None:
        path = tmp_path / "guide.docx"
        path.write_bytes(b"placeholder")

        parser = parser_for_path(path)

        assert isinstance(parser, MarkItDownParser)
        assert ".docx" in supported_extensions()


class TestMarkItDownParser:
    def test_missing_optional_dependency_has_install_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "guide.docx"
        path.write_bytes(b"placeholder")
        monkeypatch.delitem(sys.modules, "markitdown", raising=False)

        real_import = __import__

        def guarded_import(name: str, *args: Any, **kwargs: Any) -> object:
            if name == "markitdown":
                raise ImportError("not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", guarded_import)

        with pytest.raises(ParseError, match="cairn\\[markitdown\\]"):
            MarkItDownParser().parse(path)

    def test_converted_markdown_is_parsed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "guide.docx"
        path.write_bytes(b"binary document bytes")

        class FakeMarkItDown:
            def __init__(self, *, enable_plugins: bool) -> None:
                assert enable_plugins is False

            def convert_local(self, source: str) -> SimpleNamespace:
                assert source == str(path.resolve())
                return SimpleNamespace(text_content="Body without a heading.")

        module = ModuleType("markitdown")
        module.MarkItDown = FakeMarkItDown  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "markitdown", module)

        doc = MarkItDownParser().parse(path)

        assert doc.id == "guide"
        assert doc.source_path == path.resolve()
        assert len(doc.sections) == 1
        assert doc.sections[0].title == "guide"
        assert "Body without a heading" in doc.sections[0].raw_text
