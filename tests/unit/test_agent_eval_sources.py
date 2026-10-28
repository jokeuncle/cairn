"""Keep comparison sources complete and prevent reads outside the frozen corpus."""

from pathlib import Path

import pytest

from scripts.eval_document_server import Sources


def test_section_baseline_keeps_preamble_and_ignores_headings_inside_code(tmp_path: Path) -> None:
    source = tmp_path / "guide.md"
    source.write_text("Preamble.\n\n# API\n\n```python\n# comment\n```\n\n## Limits\n\nForty.\n")
    store = Sources(tmp_path, ["guide.md"])
    assert len(store.sections) == 3
    assert store.sections[0]["text"].startswith("Preamble.")
    hit = store.search("limits forty", 1, "bm25")[0]
    assert "Forty." in store.read(hit["id"])["text"]


def test_raw_search_and_read_report_truncation_and_reject_unknown_paths(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text("word\n" * 121)
    store = Sources(tmp_path, ["guide.md"])
    assert len(store.search("WORD", 2, "raw")) == 2
    assert store.read("guide.md")["truncated"] is True
    with pytest.raises(ValueError, match="Unknown source"):
        store.read("../secret.txt")
    with pytest.raises(ValueError, match="Line outside"):
        store.read("guide.md#L0")
