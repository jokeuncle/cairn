"""Input-boundary and provenance tests for explicit snippet preprocessing."""

from __future__ import annotations

import hashlib
import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/materialize_doc_snippets.py"
_SPEC = importlib.util.spec_from_file_location("doc_snippets", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
materialize = cast(Callable[[Path, list[str], Path], dict[str, Any]], _MODULE.materialize)


def _source(tmp_path: Path, code: str = "print('hello')\n") -> Path:
    root = tmp_path / "source"
    (root / "docs_src").mkdir(parents=True)
    (root / "docs_src/example.py").write_text(code)
    (root / "guide.md").write_text("# Guide\n\n{* docs_src/example.py hl[1:3] *}\n")
    return root


def test_exact_unicode_snippet_and_provenance_without_execution(tmp_path: Path) -> None:
    code = "# 雪😀 ```\nraise RuntimeError('must never execute')\n"
    root = _source(tmp_path, code)
    original = (root / "guide.md").read_bytes()
    output = tmp_path / "prepared"
    manifest = materialize(root, ["guide.md"], output)
    record = manifest["documents"]["guide.md"]
    snippet = record["snippets"][0]
    text = (output / "guide.md").read_text()
    span = snippet["output_span"]
    assert text[span["start"] : span["end"]] == code
    assert "````python" in text
    assert snippet["source_sha256"] == hashlib.sha256(code.encode()).hexdigest()
    assert record["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert record["output_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert (root / "guide.md").read_bytes() == original
    assert (output / "snippet-manifest.json").is_file()


@pytest.mark.parametrize("relative", ["../guide.md", "/tmp/guide.md"])
def test_rejects_input_path_escape(tmp_path: Path, relative: str) -> None:
    root = _source(tmp_path)
    with pytest.raises(ValueError, match="repository-relative"):
        materialize(root, [relative], tmp_path / "prepared")


def test_rejects_symlink_include_escape_before_any_output(tmp_path: Path) -> None:
    root = _source(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("private = 'not included'\n")
    (root / "docs_src/example.py").unlink()
    (root / "docs_src/example.py").symlink_to(outside)
    output = tmp_path / "prepared"
    with pytest.raises(ValueError, match="leaves the repository"):
        materialize(root, ["guide.md"], output)
    assert not output.exists()


def test_unknown_or_missing_include_does_not_leave_partial_tree(tmp_path: Path) -> None:
    root = _source(tmp_path)
    output = tmp_path / "prepared"
    (root / "bad.md").write_text("{* https://example.test/code.py *}")
    with pytest.raises(ValueError, match="unsupported"):
        materialize(root, ["guide.md", "bad.md"], output)
    assert not output.exists()
    (root / "bad.md").write_text("{* docs_src/missing.py *}")
    with pytest.raises(FileNotFoundError):
        materialize(root, ["guide.md", "bad.md"], output)
    assert not output.exists()


def test_refuses_existing_destination_and_source_tree_output(tmp_path: Path) -> None:
    root = _source(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        materialize(root, ["guide.md"], root / "prepared")
    output = tmp_path / "prepared"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        materialize(root, ["guide.md"], output)
    assert sentinel.read_text() == "keep"


def test_literal_include_text_in_code_is_not_recursively_expanded(tmp_path: Path) -> None:
    code = "template = '{* docs_src/missing.py *}'\n"
    root = _source(tmp_path, code)
    output = tmp_path / "prepared"
    result = materialize(root, ["guide.md"], output)
    assert code in (output / "guide.md").read_text()
    assert len(result["documents"]["guide.md"]["snippets"]) == 1


def test_new_include_content_changes_manifest_and_output(tmp_path: Path) -> None:
    root = _source(tmp_path)
    first = materialize(root, ["guide.md"], tmp_path / "first")
    (root / "docs_src/example.py").write_text("new_value = 17\n")
    second = materialize(root, ["guide.md"], tmp_path / "second")
    a = first["documents"]["guide.md"]
    b = second["documents"]["guide.md"]
    assert a["source_sha256"] == b["source_sha256"]
    assert a["output_sha256"] != b["output_sha256"]
    assert a["snippets"][0]["source_sha256"] != b["snippets"][0]["source_sha256"]


def test_repeated_include_expansion_obeys_byte_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _source(tmp_path, "# 雪😀\n" * 3)
    (root / "guide.md").write_text("{* docs_src/example.py *}\n" * 10)
    monkeypatch.setattr(_MODULE, "_MAX_TOTAL_BYTES", 100)
    output = tmp_path / "prepared"
    with pytest.raises(ValueError, match="prepared documents exceed"):
        materialize(root, ["guide.md"], output)
    assert not output.exists()


def test_oversized_include_is_rejected_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _source(tmp_path, "x" * 80)
    monkeypatch.setattr(_MODULE, "_MAX_FILE_BYTES", 64)
    output = tmp_path / "prepared"
    with pytest.raises(ValueError, match="source file exceeds"):
        materialize(root, ["guide.md"], output)
    assert not output.exists()
