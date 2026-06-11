"""Tests for cairn.bench.dataset (TOML loader)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.bench.dataset import load_suite
from cairn.core.errors import ConfigError


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "suite.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_minimal_suite(tmp_path: Path) -> None:
    # Source file referenced relatively
    (tmp_path / "doc.md").write_text("# Hi\n", encoding="utf-8")
    suite_path = _write(
        tmp_path,
        """
name = "minimal"

[[documents]]
id = "d1"
source = "doc.md"

[[documents.questions]]
id = "q1"
question = "what?"
expected_anchors = ["foo"]
tags = ["test"]
""",
    )
    suite = load_suite(suite_path)
    assert suite.name == "minimal"
    assert len(suite.documents) == 1
    doc = suite.documents[0]
    assert doc.id == "d1"
    assert doc.source == (tmp_path / "doc.md").resolve()
    assert len(doc.questions) == 1
    q = doc.questions[0]
    assert q.id == "q1"
    assert q.expected_anchors == ("foo",)
    assert q.tags == ("test",)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_suite(tmp_path / "ghost.toml")


def test_question_without_expected_anchors_defaults_empty(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("# Hi\n", encoding="utf-8")
    suite_path = _write(
        tmp_path,
        """
name = "n"
[[documents]]
id = "d"
source = "doc.md"

[[documents.questions]]
id = "q"
question = "?"
""",
    )
    suite = load_suite(suite_path)
    assert suite.documents[0].questions[0].expected_anchors == ()


def test_default_name_falls_back_to_filename(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("# Hi\n", encoding="utf-8")
    suite_path = _write(
        tmp_path,
        """
[[documents]]
id = "d"
source = "doc.md"
""",
    )
    suite = load_suite(suite_path)
    assert suite.name == suite_path.stem
