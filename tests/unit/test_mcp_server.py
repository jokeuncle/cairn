"""Tests for cairn.mcp.server.

We test ``dispatch_tool`` directly — it is the seam between the MCP wire
layer and the tool functions, and is the smallest unit that exercises the
envelope shape contract.
"""

from __future__ import annotations

from cairn.embed.fake import FakeEmbedder
from cairn.mcp.schemas import CAIRN_TOOLS
from cairn.mcp.server import dispatch_tool
from cairn.tools.base import DocumentIndex


class TestSchemas:
    def test_v02_tools_registered(self) -> None:
        names = {t.name for t in CAIRN_TOOLS}
        assert names == {
            "outline",
            "get_section",
            "expand",
            "search_semantic",
            "search_keyword",
            "find_mentions",
            "get_related",
        }

    def test_every_tool_has_description_and_schema(self) -> None:
        for tool in CAIRN_TOOLS:
            assert tool.description
            assert tool.inputSchema.get("type") == "object"


class TestDispatchHappyPath:
    async def test_outline(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool("outline", {"depth": 2}, index, fake_embedder)
        assert env["ok"] is True
        assert env["tokens_returned"] > 0
        assert "tree" in env["data"]

    async def test_get_section(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool(
            "get_section", {"id": "introduction"}, index, fake_embedder
        )
        assert env["ok"] is True
        assert env["data"]["id"] == "introduction"

    async def test_expand(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool(
            "expand",
            {"id": "introduction", "to": "full"},
            index,
            fake_embedder,
        )
        assert env["ok"] is True
        assert "This is the intro body" in env["data"]["content"]

    async def test_search_semantic(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool(
            "search_semantic",
            {"query": "intro body lines", "k": 3},
            index,
            fake_embedder,
        )
        assert env["ok"] is True
        assert "hits" in env["data"]

    async def test_search_keyword(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool(
            "search_keyword",
            {"terms": ["pip"]},
            index,
            fake_embedder,
        )
        assert env["ok"] is True
        ids = [h["id"] for h in env["data"]["hits"]]
        assert "introduction/quickstart" in ids


class TestDispatchErrors:
    async def test_unknown_tool_returns_error_envelope(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool(
            "nonexistent_tool", {}, index, fake_embedder
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "INVALID_INPUT"

    async def test_missing_required_argument_returns_error(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool("get_section", {}, index, fake_embedder)
        assert env["ok"] is False
        # Either a TypeError-derived INVALID_INPUT envelope, or a ToolError.
        assert env["error"]["code"] in ("INVALID_INPUT", "NOT_FOUND")

    async def test_tool_error_propagates_as_envelope(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        # outline with invalid depth → ToolError → envelope
        env = await dispatch_tool(
            "outline", {"depth": 99}, index, fake_embedder
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "INVALID_INPUT"
        assert "depth" in env["error"]["message"].lower()

    async def test_unknown_section_returns_not_found(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool(
            "get_section", {"id": "ghost"}, index, fake_embedder
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND"


class TestEnvelopeShape:
    async def test_success_envelope_has_required_keys(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool("outline", {}, index, fake_embedder)
        assert set(env.keys()) == {"ok", "tokens_returned", "data"}

    async def test_error_envelope_has_required_keys(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool("nope", {}, index, fake_embedder)
        assert set(env.keys()) == {"ok", "error"}
        assert set(env["error"].keys()) == {"code", "message", "details"}
