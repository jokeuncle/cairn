"""Tests for cairn.engine.indexer.Indexer."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.embed.fake import FakeEmbedder
from cairn.engine.indexer import Indexer
from cairn.engine.manifest import MANIFEST_FILENAME, read_manifest
from cairn.index.summaries import SUMMARIES_FILENAME
from cairn.index.tree import TREE_FILENAME
from cairn.index.vectors import VECTORS_DB_DIRNAME, VECTORS_MANIFEST_FILENAME
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.base import SummaryLevel
from cairn.summarize.fake import FakeSummarizer
from cairn.tools.base import DocumentIndex


@pytest.fixture
def fixture_md(fixture_dir: Path) -> Path:
    return fixture_dir / "simple.md"


@pytest.fixture
def indexer() -> Indexer:
    return Indexer(
        parser=MarkdownParser(),
        summarizer=FakeSummarizer(),
        embedder=FakeEmbedder(dim=32),
    )


class TestIndexer:
    async def test_index_path_writes_all_artifacts(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        result = await indexer.index_path(fixture_md, out_dir=out)
        assert result.manifest_path == out / MANIFEST_FILENAME
        assert result.rebuilt is True
        for filename in (
            MANIFEST_FILENAME,
            TREE_FILENAME,
            SUMMARIES_FILENAME,
            VECTORS_MANIFEST_FILENAME,
        ):
            assert (out / filename).exists(), filename
        assert (out / VECTORS_DB_DIRNAME).is_dir()

    async def test_manifest_records_provenance(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        await indexer.index_path(fixture_md, out_dir=out, doc_id="simple")
        manifest = read_manifest(out)
        assert manifest.doc_id == "simple"
        assert manifest.source_hash  # non-empty
        assert manifest.cairn_version
        assert set(manifest.subindexes) == {"tree", "summaries", "vectors"}
        assert manifest.subindexes["summaries"].model == "fake:words"
        assert manifest.subindexes["summaries"].levels == [
            "gist",
            "synopsis",
            "digest",
        ]
        assert manifest.subindexes["vectors"].embedder == "fake:bow-hash"
        assert manifest.subindexes["vectors"].dim == 32

    async def test_doc_id_overrides_filename(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        await indexer.index_path(fixture_md, out_dir=out, doc_id="custom")
        manifest = read_manifest(out)
        assert manifest.doc_id == "custom"

    async def test_built_index_loads_via_document_index(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        await indexer.index_path(fixture_md, out_dir=out)
        index = DocumentIndex.load(out)
        # Each sub-index aligned to the same doc_id.
        assert index.doc_id == "simple"
        assert len(index.tree) > 0
        assert len(index.summaries) > 0

    async def test_custom_summary_levels(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        await indexer.index_path(
            fixture_md,
            out_dir=out,
            summary_levels=(SummaryLevel.GIST,),
        )
        manifest = read_manifest(out)
        assert manifest.subindexes["summaries"].levels == ["gist"]


class TestIncrementalRebuild:
    async def test_second_call_is_no_op(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        first = await indexer.index_path(fixture_md, out_dir=out)
        assert first.rebuilt is True
        first_indexed_at = read_manifest(out).indexed_at

        second = await indexer.index_path(fixture_md, out_dir=out)
        assert second.rebuilt is False
        assert second.manifest_path == first.manifest_path
        # Manifest was not touched.
        assert read_manifest(out).indexed_at == first_indexed_at

    async def test_force_overrides_no_op(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        first = await indexer.index_path(fixture_md, out_dir=out)
        assert first.rebuilt is True
        first_indexed_at = read_manifest(out).indexed_at

        second = await indexer.index_path(fixture_md, out_dir=out, force=True)
        assert second.rebuilt is True
        # Rebuilt → new indexed_at.
        assert read_manifest(out).indexed_at >= first_indexed_at

    async def test_changed_source_triggers_rebuild(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        await indexer.index_path(fixture_md, out_dir=out)

        # Modify the source and re-index.
        modified = tmp_path / "modified.md"
        modified.write_text(
            fixture_md.read_text() + "\n\n## New section\n\nnew body.\n",
            encoding="utf-8",
        )
        result = await indexer.index_path(modified, out_dir=out)
        assert result.rebuilt is True

    async def test_missing_manifest_still_builds(
        self, indexer: Indexer, tmp_path: Path, fixture_md: Path
    ) -> None:
        out = tmp_path / "doc"
        # First call: no manifest exists → must build.
        result = await indexer.index_path(fixture_md, out_dir=out)
        assert result.rebuilt is True
