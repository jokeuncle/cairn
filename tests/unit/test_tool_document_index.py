"""Tests for cairn.tools.base.DocumentIndex composite loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.core.errors import IndexBuildError
from cairn.embed.fake import FakeEmbedder
from cairn.index.summaries import Summaries, SummaryBuilder
from cairn.index.tree import Tree, TreeBuilder
from cairn.index.vectors import VectorBuilder, Vectors
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.fake import FakeSummarizer
from cairn.tools.base import DocumentIndex, estimate_tokens, estimate_tokens_of_payload


class TestLoad:
    async def test_load_composite(self, tmp_path: Path, simple_md: str) -> None:
        doc = MarkdownParser().parse(simple_md, doc_id="simple")
        TreeBuilder().build(doc, out_dir=tmp_path)
        await SummaryBuilder(FakeSummarizer()).build(doc, out_dir=tmp_path)
        await VectorBuilder(FakeEmbedder(dim=32)).build(doc, out_dir=tmp_path)

        index = DocumentIndex.load(tmp_path)
        assert index.doc_id == "simple"
        assert isinstance(index.tree, Tree)
        assert isinstance(index.summaries, Summaries)
        assert isinstance(index.vectors, Vectors)

    async def test_anchor_format(self, index: DocumentIndex) -> None:
        assert index.anchor("introduction") == "cairn://simple/introduction"

    async def test_doc_id_mismatch_rejected(
        self, tmp_path: Path, simple_md: str
    ) -> None:
        # Build two docs with different ids, then mix sub-indexes.
        doc_a = MarkdownParser().parse(simple_md, doc_id="a")
        doc_b = MarkdownParser().parse(simple_md, doc_id="b")

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        TreeBuilder().build(doc_a, out_dir=dir_a)
        await SummaryBuilder(FakeSummarizer()).build(doc_a, out_dir=dir_a)
        await VectorBuilder(FakeEmbedder(dim=16)).build(doc_a, out_dir=dir_a)

        TreeBuilder().build(doc_b, out_dir=dir_b)
        await SummaryBuilder(FakeSummarizer()).build(doc_b, out_dir=dir_b)
        await VectorBuilder(FakeEmbedder(dim=16)).build(doc_b, out_dir=dir_b)

        tree_a = Tree.load(dir_a)
        summaries_a = Summaries.load(dir_a)
        vectors_b = Vectors.load(dir_b)

        with pytest.raises(IndexBuildError):
            DocumentIndex(tree=tree_a, summaries=summaries_a, vectors=vectors_b)


class TestTokenEstimator:
    def test_empty_string_zero_tokens(self) -> None:
        assert estimate_tokens("") == 0

    def test_non_empty_at_least_one(self) -> None:
        assert estimate_tokens("hi") >= 1

    def test_scales_with_words(self) -> None:
        small = estimate_tokens("one two three")
        big = estimate_tokens("one two three four five six seven eight nine ten")
        assert big > small

    def test_payload_flattens_strings(self) -> None:
        payload = {"a": "hello world", "b": ["foo bar", {"c": "baz"}]}
        n = estimate_tokens_of_payload(payload)
        assert n >= estimate_tokens("hello world foo bar baz") - 1
