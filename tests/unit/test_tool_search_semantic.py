"""Tests for cairn.tools.search_semantic."""

from __future__ import annotations

import pytest

from cairn.core.errors import ToolError
from cairn.embed.fake import FakeEmbedder
from cairn.tools.base import DocumentIndex
from cairn.tools.search_semantic import _evidence_snippet, search_semantic


class TestInputs:
    async def test_empty_query_rejected(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        with pytest.raises(ToolError):
            await search_semantic(index, embedder=fake_embedder, query="   ")

    async def test_invalid_k_rejected(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        with pytest.raises(ToolError):
            await search_semantic(index, embedder=fake_embedder, query="x", k=0)
        with pytest.raises(ToolError):
            await search_semantic(index, embedder=fake_embedder, query="x", k=33)

    async def test_invalid_include_rejected(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        with pytest.raises(ToolError):
            await search_semantic(
                index,
                embedder=fake_embedder,
                query="x",
                include=("body",),  # type: ignore[arg-type]
            )

    async def test_dim_mismatch_rejected(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await search_semantic(
                index,
                embedder=FakeEmbedder(dim=8),  # index built with dim=64
                query="hello",
            )


class TestRanking:
    async def test_self_query_ranks_relevant_section(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        # The "introduction" raw_text in simple.md is "This is the intro
        # body. It spans multiple lines and has some text."
        resp = await search_semantic(
            index,
            embedder=fake_embedder,
            query="intro body lines text",
            k=5,
        )
        hit_ids = [h["id"] for h in resp.data["hits"]]
        assert "introduction" in hit_ids
        # Should be in the top-2 hits.
        assert "introduction" in hit_ids[:2]

    async def test_hits_carry_anchor(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        resp = await search_semantic(
            index, embedder=fake_embedder, query="intro body", k=3
        )
        for hit in resp.data["hits"]:
            assert hit["anchor"].startswith("cairn://simple/")

    async def test_synopsis_attached_when_requested(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        resp = await search_semantic(
            index,
            embedder=fake_embedder,
            query="intro body",
            include=("synopsis",),
        )
        for hit in resp.data["hits"]:
            assert "synopsis" in hit
            assert "head" not in hit
            assert "evidence" not in hit

    async def test_evidence_attached_by_default(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        resp = await search_semantic(
            index,
            embedder=fake_embedder,
            query="intro body lines",
            k=3,
        )
        hit = resp.data["hits"][0]
        assert "evidence" in hit
        assert set(hit["evidence"]) == {"text", "matched_terms", "span"}

    def test_evidence_supports_cjk_queries(self) -> None:
        evidence = _evidence_snippet(
            "这里说明向量数据存储在本地向量库, 并由 manifest 记录维度.",
            "向量数据存储在哪里",
        )

        assert "本地向量库" in evidence["text"]
        assert "向量数据存储" in evidence["matched_terms"]


class TestScope:
    async def test_scope_restricts_to_subtree(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        resp = await search_semantic(
            index,
            embedder=fake_embedder,
            query="anything",
            scope="introduction",
            k=10,
        )
        for hit in resp.data["hits"]:
            assert hit["id"] == "introduction" or hit["id"].startswith("introduction/")
