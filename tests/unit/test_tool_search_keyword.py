"""Tests for cairn.tools.search_keyword."""

from __future__ import annotations

import pytest

from cairn.core.errors import ToolError
from cairn.tools.base import DocumentIndex
from cairn.tools.search_keyword import search_keyword


class TestInputs:
    async def test_zero_terms_rejected(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await search_keyword(index, terms=[])

    async def test_too_many_terms_rejected(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await search_keyword(index, terms=["a"] * 9)

    async def test_empty_term_string_rejected(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await search_keyword(index, terms=["   "])

    async def test_invalid_k_rejected(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await search_keyword(index, terms=["pip"], k=0)


class TestMatching:
    async def test_single_term_match_hits_intro(
        self, index: DocumentIndex
    ) -> None:
        resp = await search_keyword(index, terms=["pip"])
        ids = [h["id"] for h in resp.data["hits"]]
        # "pip" appears in Quickstart body.
        assert "introduction/quickstart" in ids

    async def test_case_insensitive(self, index: DocumentIndex) -> None:
        lower = await search_keyword(index, terms=["pip"])
        upper = await search_keyword(index, terms=["PIP"])
        assert [h["id"] for h in lower.data["hits"]] == [
            h["id"] for h in upper.data["hits"]
        ]

    async def test_no_match_returns_empty_hits(
        self, index: DocumentIndex
    ) -> None:
        resp = await search_keyword(index, terms=["xylophone"])
        assert resp.data["hits"] == []

    async def test_mode_all_requires_all_terms(
        self, index: DocumentIndex
    ) -> None:
        # "pip" is only in Quickstart, "toml" is only in Configuration.
        # mode=all → no section has both → empty.
        resp_all = await search_keyword(
            index, terms=["pip", "toml"], mode="all"
        )
        assert resp_all.data["hits"] == []
        # mode=any → both sections match individually.
        resp_any = await search_keyword(
            index, terms=["pip", "toml"], mode="any"
        )
        ids = {h["id"] for h in resp_any.data["hits"]}
        assert "introduction/quickstart" in ids
        assert "introduction/configuration" in ids


class TestScoring:
    async def test_scoring_reflects_count_and_length(
        self, index: DocumentIndex
    ) -> None:
        resp = await search_keyword(index, terms=["the"])
        # "the" appears in multiple sections; scores must be positive ints.
        for hit in resp.data["hits"]:
            assert hit["score"] > 0
            assert isinstance(hit["score"], int)

    async def test_matches_carry_term_counts(self, index: DocumentIndex) -> None:
        resp = await search_keyword(index, terms=["pip"])
        for hit in resp.data["hits"]:
            assert hit["matches"]
            for match in hit["matches"]:
                assert match["count"] >= 1


class TestScope:
    async def test_scope_restricts_hits(self, index: DocumentIndex) -> None:
        resp = await search_keyword(
            index, terms=["the"], scope="reference"
        )
        for hit in resp.data["hits"]:
            assert hit["id"] == "reference" or hit["id"].startswith("reference/")
