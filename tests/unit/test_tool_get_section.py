"""Tests for cairn.tools.get_section and cairn.tools.expand."""

from __future__ import annotations

import pytest

from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.tools.base import DocumentIndex
from cairn.tools.get_section import expand, get_section


class TestGetSection:
    async def test_default_level_is_synopsis(self, index: DocumentIndex) -> None:
        resp = await get_section(index, id="introduction")
        assert resp.data["level"] == "synopsis"
        # FakeSummarizer produces non-empty synopsis from the body.
        assert resp.data["content"]

    async def test_level_gist(self, index: DocumentIndex) -> None:
        resp = await get_section(index, id="introduction", level="gist")
        assert resp.data["level"] == "gist"
        assert resp.data["content"]

    async def test_level_full_returns_raw_text(self, index: DocumentIndex) -> None:
        resp = await get_section(index, id="introduction", level="full")
        assert "This is the intro body" in resp.data["content"]

    async def test_digest_unavailable_in_v01(self, index: DocumentIndex) -> None:
        with pytest.raises(IndexNotFoundError) as exc:
            await get_section(index, id="introduction", level="digest")
        assert "digest" in exc.value.message.lower()

    async def test_missing_section_id(self, index: DocumentIndex) -> None:
        with pytest.raises(IndexNotFoundError):
            await get_section(index, id="ghost")

    async def test_include_children_reserved(self, index: DocumentIndex) -> None:
        with pytest.raises(ToolError):
            await get_section(index, id="introduction", include_children=True)

    async def test_anchor_includes_doc_and_id(self, index: DocumentIndex) -> None:
        resp = await get_section(index, id="introduction/quickstart")
        assert resp.data["anchor"] == "cairn://simple/introduction/quickstart"

    async def test_path_is_breadcrumb(self, index: DocumentIndex) -> None:
        resp = await get_section(index, id="introduction/quickstart")
        assert resp.data["path"] == ["Introduction", "Quickstart"]

    async def test_has_children_flag(self, index: DocumentIndex) -> None:
        intro = await get_section(index, id="introduction")
        leaf = await get_section(index, id="introduction/quickstart")
        assert intro.data["has_children"] is True
        assert leaf.data["has_children"] is False

    async def test_next_levels_available_at_synopsis(
        self, index: DocumentIndex
    ) -> None:
        resp = await get_section(index, id="introduction", level="synopsis")
        # v0.1 has no digest, so next available after synopsis is just full.
        assert resp.data["next_levels_available"] == ["full"]

    async def test_next_levels_available_at_gist(
        self, index: DocumentIndex
    ) -> None:
        resp = await get_section(index, id="introduction", level="gist")
        # synopsis exists, digest doesn't, full always does.
        assert "synopsis" in resp.data["next_levels_available"]
        assert "full" in resp.data["next_levels_available"]

    async def test_tokens_match_content(self, index: DocumentIndex) -> None:
        resp = await get_section(index, id="introduction", level="full")
        # Non-empty content → non-zero tokens.
        assert resp.tokens_returned > 0


class TestExpand:
    async def test_equivalent_to_get_section(self, index: DocumentIndex) -> None:
        a = await get_section(index, id="introduction", level="full")
        b = await expand(index, id="introduction", to="full")
        assert a.data == b.data
