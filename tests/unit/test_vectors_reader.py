"""Tests for cairn.index.vectors.Vectors (read-side queries)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.core.types import Document
from cairn.embed.fake import FakeEmbedder
from cairn.index.vectors import (
    VECTORS_MANIFEST_FILENAME,
    VectorBuilder,
    Vectors,
)
from cairn.ingest.markdown import MarkdownParser


@pytest.fixture
def parsed_simple(simple_md: str) -> Document:
    return MarkdownParser().parse(simple_md, doc_id="simple")


@pytest.fixture
async def built_dir(tmp_path: Path, parsed_simple: Document) -> Path:
    out = tmp_path / "doc"
    await VectorBuilder(FakeEmbedder(dim=64)).build(parsed_simple, out_dir=out)
    return out


# -- Load -------------------------------------------------------------------


class TestLoad:
    async def test_load_missing_manifest_raises(self, tmp_path: Path) -> None:
        with pytest.raises(IndexNotFoundError):
            Vectors.load(tmp_path / "ghost")

    async def test_load_missing_lancedb_raises(self, tmp_path: Path) -> None:
        # Write a manifest but no .lance directory.
        out = tmp_path / "partial"
        out.mkdir()
        (out / VECTORS_MANIFEST_FILENAME).write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "doc_id": "x",
                    "embedder": "fake",
                    "dim": 4,
                    "section_count": 0,
                    "generated_at": "2026-01-01T00:00:00+00:00",
                }
            )
        )
        with pytest.raises(IndexNotFoundError):
            Vectors.load(out)

    async def test_unsupported_version_raises(self, tmp_path: Path) -> None:
        out = tmp_path / "future"
        out.mkdir()
        (out / VECTORS_MANIFEST_FILENAME).write_text(
            json.dumps(
                {
                    "format_version": 99,
                    "doc_id": "x",
                    "embedder": "fake",
                    "dim": 4,
                    "section_count": 0,
                    "generated_at": "2026-01-01T00:00:00+00:00",
                }
            )
        )
        (out / "vectors.lance").mkdir()
        with pytest.raises(IndexNotFoundError):
            Vectors.load(out)


# -- Search -----------------------------------------------------------------


class TestSearch:
    async def test_query_dim_mismatch_raises(self, built_dir: Path) -> None:
        vectors = Vectors.load(built_dir)
        with pytest.raises(IndexBuildError):
            await vectors.search([0.1, 0.2], k=4)

    async def test_invalid_k_raises(self, built_dir: Path) -> None:
        vectors = Vectors.load(built_dir)
        with pytest.raises(IndexBuildError):
            await vectors.search([0.0] * 64, k=0)

    async def test_search_returns_at_most_k(self, built_dir: Path) -> None:
        vectors = Vectors.load(built_dir)
        hits = await vectors.search([0.0] * 64, k=2)
        assert len(hits) <= 2

    async def test_scores_within_unit_range(self, built_dir: Path) -> None:
        vectors = Vectors.load(built_dir)
        hits = await vectors.search([0.1] * 64, k=5)
        for hit in hits:
            assert 0.0 <= hit.score <= 1.0

    async def test_self_query_ranks_source_section_first(
        self, tmp_path: Path
    ) -> None:
        # Build with a known query: embedding the same text used at index time
        # should return that section as the top hit.
        md = (
            "# Hooks\n\nuseEffect lets you synchronize a component "
            "with an external system.\n\n"
            "# Other\n\nTotally unrelated content about quantum dynamics.\n"
        )
        doc = MarkdownParser().parse(md, doc_id="hooks")
        embedder = FakeEmbedder(dim=64)
        out = tmp_path / "doc"
        await VectorBuilder(embedder).build(doc, out_dir=out)
        vectors = Vectors.load(out)

        # Query with the exact text that should match the "hooks" section.
        from cairn.index.vectors import embedding_text

        target_section = doc.sections[0]
        query_vec = (await embedder.embed([embedding_text(target_section)]))[0]
        hits = await vectors.search(query_vec, k=2)
        assert hits[0].id == "hooks"


class TestScopeFilter:
    async def test_scope_prefix_restricts_results(
        self, tmp_path: Path
    ) -> None:
        md = (
            "# Intro\n\nIntro body.\n\n"
            "## Setup\n\nSetup body.\n\n"
            "## Config\n\nConfig body.\n\n"
            "# Reference\n\nReference body.\n\n"
            "## API\n\nAPI body.\n"
        )
        doc = MarkdownParser().parse(md, doc_id="d")
        out = tmp_path / "doc"
        await VectorBuilder(FakeEmbedder(dim=32)).build(doc, out_dir=out)
        vectors = Vectors.load(out)

        hits = await vectors.search([0.1] * 32, k=10, scope_prefix="intro")
        for hit in hits:
            assert hit.id == "intro" or hit.id.startswith("intro/")

    async def test_invalid_scope_prefix_raises(self, built_dir: Path) -> None:
        vectors = Vectors.load(built_dir)
        with pytest.raises(IndexBuildError):
            await vectors.search([0.0] * 64, k=4, scope_prefix="evil'; DROP")
