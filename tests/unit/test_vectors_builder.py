"""Tests for cairn.index.vectors.VectorBuilder."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from cairn.core.errors import IndexBuildError
from cairn.core.types import Document
from cairn.embed.fake import FakeEmbedder
from cairn.index.vectors import (
    VECTORS_DB_DIRNAME,
    VECTORS_FORMAT_VERSION,
    VECTORS_MANIFEST_FILENAME,
    VectorBuilder,
    Vectors,
    embedding_text,
    l2_normalize,
)
from cairn.ingest.markdown import MarkdownParser


@pytest.fixture
def parsed_simple(simple_md: str) -> Document:
    return MarkdownParser().parse(simple_md, doc_id="simple")


# -- helpers ----------------------------------------------------------------


class TestHelpers:
    def test_embedding_text_includes_title_and_body(self) -> None:
        from cairn.core.types import SectionNode, Span

        node = SectionNode(
            id="x",
            title="Hello",
            level=1,
            parent=None,
            children=(),
            span=Span(start=0, end=10),
            path=("Hello",),
            raw_text="World",
        )
        assert embedding_text(node) == "Hello\n\nWorld"

    def test_embedding_text_falls_back_to_title_for_empty_body(self) -> None:
        from cairn.core.types import SectionNode, Span

        node = SectionNode(
            id="x",
            title="JustTitle",
            level=1,
            parent=None,
            children=(),
            span=Span(start=0, end=0),
            path=("JustTitle",),
            raw_text="   \n  ",
        )
        assert embedding_text(node) == "JustTitle"

    def test_l2_normalize_unit_vector(self) -> None:
        out = l2_normalize([3.0, 4.0])
        norm = math.sqrt(sum(x * x for x in out))
        assert math.isclose(norm, 1.0)

    def test_l2_normalize_zero_vector_unchanged(self) -> None:
        out = l2_normalize([0.0, 0.0, 0.0])
        assert out == [0.0, 0.0, 0.0]


# -- Build ------------------------------------------------------------------


class TestVectorBuilder:
    async def test_writes_manifest_and_table(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        path = await VectorBuilder(FakeEmbedder(dim=32)).build(
            parsed_simple, out_dir=out
        )
        assert path == out / VECTORS_MANIFEST_FILENAME
        assert path.exists()
        assert (out / VECTORS_DB_DIRNAME).is_dir()

    async def test_manifest_payload(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await VectorBuilder(FakeEmbedder(dim=32)).build(parsed_simple, out_dir=out)
        manifest = json.loads((out / VECTORS_MANIFEST_FILENAME).read_text())
        assert manifest["format_version"] == VECTORS_FORMAT_VERSION
        assert manifest["doc_id"] == "simple"
        assert manifest["embedder"] == "fake:bow-hash"
        assert manifest["dim"] == 32
        assert manifest["section_count"] == len(parsed_simple.sections)

    async def test_rebuild_clears_old_table(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await VectorBuilder(FakeEmbedder(dim=16)).build(parsed_simple, out_dir=out)
        # Build again with a different dim — clean state is required.
        await VectorBuilder(FakeEmbedder(dim=32)).build(parsed_simple, out_dir=out)
        manifest = json.loads((out / VECTORS_MANIFEST_FILENAME).read_text())
        assert manifest["dim"] == 32
        vectors = Vectors.load(out)
        assert vectors.dim == 32

    def test_batch_size_zero_rejected(self) -> None:
        with pytest.raises(IndexBuildError):
            VectorBuilder(FakeEmbedder(dim=8), batch_size=0)

    async def test_batches_respect_size_limit(self, tmp_path: Path) -> None:
        md = "\n\n".join(f"# Section {i}\n\nBody {i}." for i in range(10))
        doc = MarkdownParser().parse(md, doc_id="batched")
        out = tmp_path / "doc"

        class CountingEmbedder:
            name = "fake:counting"
            dim = 8

            def __init__(self) -> None:
                self.batch_sizes: list[int] = []
                self._inner = FakeEmbedder(dim=self.dim)

            async def embed(self, texts: list[str]) -> list[list[float]]:
                self.batch_sizes.append(len(texts))
                return await self._inner.embed(texts)

        embedder = CountingEmbedder()
        await VectorBuilder(embedder, batch_size=3).build(doc, out_dir=out)
        # 10 sections → batch sizes 3, 3, 3, 1
        assert embedder.batch_sizes == [3, 3, 3, 1]


# -- End-to-end through Vectors.load ----------------------------------------


class TestEndToEnd:
    async def test_load_after_build(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await VectorBuilder(FakeEmbedder(dim=32)).build(parsed_simple, out_dir=out)
        vectors = Vectors.load(out)
        assert vectors.doc_id == "simple"
        assert vectors.embedder == "fake:bow-hash"
        assert vectors.dim == 32
        assert await vectors.count() == len(parsed_simple.sections)
