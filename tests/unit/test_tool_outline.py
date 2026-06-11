"""Tests for cairn.tools.outline."""

from __future__ import annotations

import pytest

from cairn.core.errors import ToolError
from cairn.tools.base import DocumentIndex
from cairn.tools.outline import outline


class TestInputs:
    async def test_invalid_depth_low(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await outline(index, depth=0)

    async def test_invalid_depth_high(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await outline(index, depth=7)

    async def test_empty_include_rejected(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await outline(index, include=())

    async def test_invalid_include_rejected(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await outline(index, include=("digest",))  # type: ignore[arg-type]


class TestOutput:
    async def test_default_returns_gist_only(self, index: DocumentIndex) -> None:
        resp = await outline(index)
        root = resp.data["tree"][0]
        assert "gist" in root
        assert "synopsis" not in root

    async def test_synopsis_attaches_when_requested(
        self, index: DocumentIndex
    ) -> None:
        resp = await outline(index, include=("gist", "synopsis"))
        root = resp.data["tree"][0]
        assert "synopsis" in root

    async def test_doc_id_included(self, index: DocumentIndex) -> None:
        resp = await outline(index)
        assert resp.data["doc"] == "simple"

    async def test_focus_restricts_to_subtree(self, index: DocumentIndex) -> None:
        resp = await outline(index, depth=3, focus="introduction")
        assert len(resp.data["tree"]) == 1
        assert resp.data["tree"][0]["id"] == "introduction"
        # The subtree's children must all be children of "introduction".
        for child in resp.data["tree"][0]["children"]:
            assert child["id"].startswith("introduction/")

    async def test_depth_one_truncates_children(self, index: DocumentIndex) -> None:
        resp = await outline(index, depth=1)
        for root in resp.data["tree"]:
            # simple.md's roots both have children, so each must be marked.
            assert root.get("truncated") is True
            assert root["children"] == []

    async def test_tokens_returned_positive(self, index: DocumentIndex) -> None:
        resp = await outline(index)
        assert resp.tokens_returned > 0
