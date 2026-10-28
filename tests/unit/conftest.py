"""Unit-test fixtures specific to tool/index integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.embed.fake import FakeEmbedder
from cairn.index.summaries import SummaryBuilder
from cairn.index.tree import TreeBuilder
from cairn.index.vectors import VectorBuilder
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.fake import FakeSummarizer
from cairn.tools.base import DocumentIndex


@pytest.fixture
async def built_doc_dir(tmp_path: Path, simple_md: str) -> Path:
    """A fully built document directory: Tree + Summaries + Vectors."""
    doc = MarkdownParser().parse(simple_md, doc_id="simple")
    TreeBuilder().build(doc, out_dir=tmp_path)
    await SummaryBuilder(FakeSummarizer()).build(doc, out_dir=tmp_path)
    await VectorBuilder(FakeEmbedder(dim=64)).build(doc, out_dir=tmp_path)
    return tmp_path


@pytest.fixture
async def index(built_doc_dir: Path) -> DocumentIndex:
    return DocumentIndex.load(built_doc_dir)


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder(dim=64)
