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
        manifest_path = await indexer.index_path(fixture_md, out_dir=out)
        assert manifest_path == out / MANIFEST_FILENAME
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
        assert manifest.subindexes["summaries"].levels == ["gist", "synopsis"]
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
