"""Tests for cairn.mcp.server.

We test ``dispatch_tool`` directly — it is the seam between the MCP wire
layer and the tool functions, and is the smallest unit that exercises the
envelope shape contract.
"""

from __future__ import annotations

from pathlib import Path

from cairn.cli.config import IndexConfig
from cairn.embed.fake import FakeEmbedder
from cairn.mcp.schemas import CAIRN_TOOLS, REPO_TOOLS
from cairn.mcp.server import dispatch_repo_tool, dispatch_tool
from cairn.repo import sync_repo, write_default_config
from cairn.summarize.fake import FakeSummarizer
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
            "read_range",
        }

    def test_every_tool_has_description_and_schema(self) -> None:
        for tool in CAIRN_TOOLS:
            assert tool.description
            assert tool.inputSchema.get("type") == "object"
            assert tool.outputSchema is not None
            assert tool.outputSchema.get("oneOf")
            assert tool.annotations is not None
            assert tool.annotations.title
            assert tool.annotations.readOnlyHint is True

    def test_repo_tools_have_titles_and_output_schemas(self) -> None:
        for tool in REPO_TOOLS:
            assert tool.description
            assert tool.outputSchema is not None
            assert tool.annotations is not None
            assert tool.annotations.title
            assert tool.annotations.readOnlyHint is True

    def test_repo_tools_add_document_catalog_and_search(self) -> None:
        names = {t.name for t in REPO_TOOLS}
        assert "list_documents" in names
        assert "search_documents" in names
        assert "repo_context" in names
        assert "repo_graph" in names
        assert "repo_impact" in names
        assert "outline" in names

    def test_sections_per_doc_is_only_on_repo_search_schema(self) -> None:
        semantic = next(t for t in CAIRN_TOOLS if t.name == "search_semantic")
        repo_search = next(t for t in REPO_TOOLS if t.name == "search_documents")

        assert "sections_per_doc" not in semantic.inputSchema["properties"]
        assert "sections_per_doc" in repo_search.inputSchema["properties"]


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
        assert set(env.keys()) == {"ok", "tokens_returned", "data", "trace"}
        assert env["trace"]["server"] == "cairn"
        assert env["trace"]["tool"] == "outline"
        assert env["trace"]["mode"] == "document"
        assert env["trace"]["status"] == "ok"
        assert env["trace"]["steps"][-1]["name"] == "return_result"

    async def test_error_envelope_has_required_keys(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool("nope", {}, index, fake_embedder)
        assert set(env.keys()) == {"ok", "error", "trace"}
        assert set(env["error"].keys()) == {"code", "message", "details"}
        assert env["trace"]["status"] == "error"
        assert env["trace"]["steps"][-1]["name"] == "return_error"
        assert env["trace"]["steps"][-1]["code"] == "INVALID_INPUT"


class TestRepoDispatch:
    async def test_list_documents_and_route_tool(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text(
            "# Readme\n\nProject overview.\n", encoding="utf-8"
        )
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        listed = await dispatch_repo_tool(
            "list_documents", {}, tmp_path, fake_embedder
        )
        assert listed["ok"] is True
        assert listed["data"]["documents"][0]["id"] == "readme"

        outlined = await dispatch_repo_tool(
            "outline",
            {"doc": "readme", "depth": 1},
            tmp_path,
            fake_embedder,
        )
        assert outlined["ok"] is True
        assert outlined["data"]["doc"] == "readme"

    async def test_search_documents(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text(
            "# Readme\n\nProject overview.\n", encoding="utf-8"
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "# Guide\n\nDetailed docs.\n", encoding="utf-8"
        )
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        env = await dispatch_repo_tool(
            "search_documents",
            {"query": "detailed docs", "k": 4},
            tmp_path,
            fake_embedder,
        )

        assert env["ok"] is True
        assert env["tokens_returned"] > 0
        assert any(hit["doc"] == "docs-guide" for hit in env["data"]["hits"])

    async def test_repo_context_graph_and_impact(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text(
            "# Readme\n\nProject overview for Plugin Tools.\n", encoding="utf-8"
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "\n".join(
                [
                    "# Guide",
                    "",
                    "Detailed docs for Plugin Tools.",
                    "",
                    "## Install",
                    "",
                    "Install Plugin Tools before configuring agents.",
                ]
            ),
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        context = await dispatch_repo_tool(
            "repo_context",
            {"query": "plugin tools install", "k": 2, "related_k": 2},
            tmp_path,
            fake_embedder,
        )
        assert context["ok"] is True
        assert context["data"]["context_sections"]
        assert context["data"]["relationship_map"]["nodes"]
        assert context["data"]["codegraph_bridge"]["status"] == "not_invoked"
        context_steps = {step["name"] for step in context["trace"]["steps"]}
        assert {
            "search_documents",
            "load_context_sections",
            "build_relationship_map",
            "return_result",
        }.issubset(context_steps)

        graph = await dispatch_repo_tool(
            "repo_graph",
            {"doc": "docs-guide", "max_sections": 10},
            tmp_path,
            fake_embedder,
        )
        assert graph["ok"] is True
        assert any(node["kind"] == "document" for node in graph["data"]["nodes"])
        assert any(edge["kind"] == "contains" for edge in graph["data"]["edges"])
        assert graph["data"]["codegraph_bridge"]["status"] == "external"

        impact = await dispatch_repo_tool(
            "repo_impact",
            {"doc": "docs-guide", "id": "guide/install"},
            tmp_path,
            fake_embedder,
        )
        assert impact["ok"] is True
        assert impact["data"]["scope"] == "section"
        assert "search_documents" in impact["data"]["affected_surfaces"]

    async def test_repo_tool_bad_arguments_return_error_envelope(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text(
            "# Readme\n\nProject overview.\n", encoding="utf-8"
        )
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        env = await dispatch_repo_tool(
            "repo_graph",
            {"unknown": True},
            tmp_path,
            fake_embedder,
        )

        assert env["ok"] is False
        assert env["error"]["code"] == "INVALID_INPUT"
        assert env["error"]["details"]["arguments"] == {"unknown": True}
