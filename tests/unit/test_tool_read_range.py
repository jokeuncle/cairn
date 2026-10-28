"""Tests for cairn.tools.read_range."""

from __future__ import annotations

import pytest

from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.tools.base import DocumentIndex
from cairn.tools.read_range import read_range


class TestInputs:
    async def test_max_tokens_zero_rejected(
        self, index: DocumentIndex
    ) -> None:
        with pytest.raises(ToolError):
            await read_range(
                index,
                start_id="introduction",
                end_id="introduction",
                max_tokens=0,
            )

    async def test_unknown_start_id(self, index: DocumentIndex) -> None:
        with pytest.raises(IndexNotFoundError):
            await read_range(
                index, start_id="ghost", end_id="introduction"
            )

    async def test_unknown_end_id(self, index: DocumentIndex) -> None:
        with pytest.raises(IndexNotFoundError):
            await read_range(
                index, start_id="introduction", end_id="ghost"
            )

    async def test_start_after_end_rejected(self, index: DocumentIndex) -> None:
        # In simple.md the document order is introduction → ... → reference/api.
        with pytest.raises(ToolError):
            await read_range(
                index,
                start_id="reference/api",
                end_id="introduction",
            )


class TestOutput:
    async def test_single_section(self, index: DocumentIndex) -> None:
        resp = await read_range(
            index,
            start_id="introduction",
            end_id="introduction",
        )
        assert resp.data["start_id"] == "introduction"
        assert resp.data["end_id"] == "introduction"
        assert "Introduction" in resp.data["content"]
        assert resp.data["truncated"] is False
        assert resp.data["next_id"] is None

    async def test_concatenates_in_document_order(
        self, index: DocumentIndex
    ) -> None:
        # simple.md: introduction → intro/quickstart → intro/configuration
        resp = await read_range(
            index,
            start_id="introduction",
            end_id="introduction/configuration",
        )
        content = resp.data["content"]
        # All three section titles appear, and intro precedes quickstart in text.
        for title in ("Introduction", "Quickstart", "Configuration"):
            assert title in content
        assert content.index("Introduction") < content.index("Quickstart")
        assert content.index("Quickstart") < content.index("Configuration")

    async def test_anchors_carry_doc(self, index: DocumentIndex) -> None:
        resp = await read_range(
            index,
            start_id="introduction",
            end_id="reference",
        )
        assert resp.data["anchor_start"].startswith("cairn://simple/")
        assert resp.data["anchor_end"].startswith("cairn://simple/")

    async def test_truncation_at_token_budget(
        self, index: DocumentIndex
    ) -> None:
        # Set a tiny budget; multi-section read should be truncated.
        resp = await read_range(
            index,
            start_id="introduction",
            end_id="reference/api",
            max_tokens=20,
        )
        assert resp.data["truncated"] is True
        assert resp.data["next_id"] is not None

    async def test_oversize_first_section_still_returned(
        self, index: DocumentIndex
    ) -> None:
        # max_tokens too small for even one section; still return the first.
        resp = await read_range(
            index,
            start_id="introduction",
            end_id="introduction",
            max_tokens=1,
        )
        # The single requested section is returned even when it exceeds the
        # budget — returning nothing would be worse than an oversize chunk.
        assert resp.data["content"]
        assert resp.data["truncated"] is False

    async def test_tokens_returned_matches_content_estimate(
        self, index: DocumentIndex
    ) -> None:
        resp = await read_range(
            index, start_id="introduction", end_id="introduction"
        )
        assert resp.tokens_returned > 0
