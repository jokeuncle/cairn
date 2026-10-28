"""Tests for cairn.engine.manifest."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cairn.core.errors import IndexNotFoundError
from cairn.engine.manifest import (
    MANIFEST_FILENAME,
    MANIFEST_FORMAT_VERSION,
    Manifest,
    SubIndexEntry,
    read_manifest,
    write_manifest,
)


def _manifest() -> Manifest:
    return Manifest(
        format_version=MANIFEST_FORMAT_VERSION,
        doc_id="d",
        cairn_version="0.0.1",
        source_path="/tmp/x.md",
        source_hash="0" * 64,
        indexed_at=datetime.now(UTC),
        subindexes={
            "tree": SubIndexEntry(path="tree.json", builder_version=1),
            "summaries": SubIndexEntry(
                path="summaries.json",
                builder_version=1,
                model="fake:words",
                levels=["gist", "synopsis"],
            ),
            "vectors": SubIndexEntry(
                path="vectors_manifest.json",
                builder_version=1,
                embedder="fake:bow-hash",
                dim=32,
            ),
        },
    )


class TestRoundTrip:
    def test_write_then_read(self, tmp_path: Path) -> None:
        m = _manifest()
        path = write_manifest(tmp_path, m)
        assert path == tmp_path / MANIFEST_FILENAME

        loaded = read_manifest(tmp_path)
        assert loaded.doc_id == m.doc_id
        assert loaded.source_hash == m.source_hash
        assert loaded.subindexes.keys() == m.subindexes.keys()
        assert loaded.subindexes["summaries"].levels == ["gist", "synopsis"]
        assert loaded.subindexes["vectors"].dim == 32

    def test_unknown_version_rejected(self, tmp_path: Path) -> None:
        (tmp_path / MANIFEST_FILENAME).write_text(
            json.dumps({"format_version": 99, "doc_id": "x"})
        )
        with pytest.raises(IndexNotFoundError):
            read_manifest(tmp_path)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(IndexNotFoundError):
            read_manifest(tmp_path / "ghost")
