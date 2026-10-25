"""Tests for cairn.mcp.server.

We test ``dispatch_tool`` directly — it is the seam between the MCP wire
layer and the tool functions, and is the smallest unit that exercises the
envelope shape contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cairn.cli.config import IndexConfig
from cairn.embed.fake import FakeEmbedder
from cairn.mcp.schemas import CAIRN_TOOLS, REPO_TOOLS
from cairn.mcp.server import (
    REPO_INSTRUCTIONS,
    RepoRootResolver,
    _compact_search_data,
    dispatch_repo_tool,
    dispatch_tool,
    dispatch_workspace_repo_tool,
)
from cairn.repo import sync_repo, write_default_config
from cairn.summarize.fake import FakeSummarizer
from cairn.tools.base import DocumentIndex


class TestSchemas:
    def test_compact_search_keeps_evidence_metadata_and_recovery_signals(self) -> None:
        evidence = {"text": "original source", "truncated_code": True}
        mismatch = {"query_dim": 64, "index_dims": [32], "documents": ["d"]}
        data: dict[str, Any] = {
            "query": "source",
            "searched_documents": 1,
            "hits": [
                {
                    "doc": "d",
                    "id": "s",
                    "anchor": "cairn://d/s",
                    "evidence": evidence,
                    "metadata": {"version": "2"},
                    "explanation": {"score": 0.9},
                }
            ],
            "embedding_mismatch": mismatch,
            "stale_documents": ["d"],
            "skipped_documents": [{"id": "bad", "reason": "incompatible dimensions"}],
            "next_steps": [{"command": "docsgraph sync"}],
        }
        compact = _compact_search_data(data)
        assert compact["hits"][0]["evidence"] == evidence
        assert compact["hits"][0]["metadata"] == {"version": "2"}
        assert compact["embedding_mismatch"] == mismatch
        assert compact["stale_documents"] == ["d"]
        assert compact["skipped_documents"] == data["skipped_documents"]
        assert compact["next_steps"] == data["next_steps"]
        assert "explanation" not in compact["hits"][0]
        assert "explanation" in data["hits"][0]

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

    def test_repo_tools_accept_project_path(self) -> None:
        for tool in REPO_TOOLS:
            assert "projectPath" in tool.inputSchema["properties"]

    def test_sections_per_doc_is_only_on_repo_search_schema(self) -> None:
        semantic = next(t for t in CAIRN_TOOLS if t.name == "search_semantic")
        repo_search = next(t for t in REPO_TOOLS if t.name == "search_documents")

        assert "sections_per_doc" not in semantic.inputSchema["properties"]
        assert "sections_per_doc" in repo_search.inputSchema["properties"]

    def test_repo_tool_descriptions_set_usage_boundaries(self) -> None:
        repo_context = next(t for t in REPO_TOOLS if t.name == "repo_context")
        repo_search = next(t for t in REPO_TOOLS if t.name == "search_documents")
        repo_get_section = next(t for t in REPO_TOOLS if t.name == "get_section")
        repo_context_description = repo_context.description
        repo_search_description = repo_search.description
        repo_get_section_description = repo_get_section.description

        assert repo_context_description is not None
        assert repo_search_description is not None
        assert repo_get_section_description is not None

        assert "product" in repo_context_description
        assert "architecture" in repo_search_description
        assert "exact literal search" in repo_context_description
        assert "source-code symbol" in repo_search_description
        assert "before reading raw README" in repo_context_description
        assert "Start with `repo_context`" in repo_get_section_description

    def test_repo_instructions_push_cairn_before_raw_docs(self) -> None:
        assert "Before reading raw README" in REPO_INSTRUCTIONS
        assert "If a repo tool reports setup next steps" in REPO_INSTRUCTIONS
        assert "Each repository is isolated" in REPO_INSTRUCTIONS
        assert "projectPath" in REPO_INSTRUCTIONS


class TestDispatchHappyPath:
    async def test_outline(self, index: DocumentIndex, fake_embedder: FakeEmbedder) -> None:
        env = await dispatch_tool("outline", {"depth": 2}, index, fake_embedder)
        assert env["ok"] is True
        assert env["tokens_returned"] > 0
        assert "tree" in env["data"]

    async def test_get_section(self, index: DocumentIndex, fake_embedder: FakeEmbedder) -> None:
        env = await dispatch_tool("get_section", {"id": "introduction"}, index, fake_embedder)
        assert env["ok"] is True
        assert env["data"]["id"] == "introduction"

    async def test_expand(self, index: DocumentIndex, fake_embedder: FakeEmbedder) -> None:
        env = await dispatch_tool(
            "expand",
            {"id": "introduction", "to": "full"},
            index,
            fake_embedder,
        )
        assert env["ok"] is True
        assert "This is the intro body" in env["data"]["content"]

    async def test_search_semantic(self, index: DocumentIndex, fake_embedder: FakeEmbedder) -> None:
        env = await dispatch_tool(
            "search_semantic",
            {"query": "intro body lines", "k": 3},
            index,
            fake_embedder,
        )
        assert env["ok"] is True
        assert "hits" in env["data"]
        assert any(
            step["name"] == "embed_query"
            and step["embedder"] == fake_embedder.name
            and step["dim"] == fake_embedder.dim
            for step in env["trace"]["steps"]
        )

    async def test_search_keyword(self, index: DocumentIndex, fake_embedder: FakeEmbedder) -> None:
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
        env = await dispatch_tool("nonexistent_tool", {}, index, fake_embedder)
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
        env = await dispatch_tool("outline", {"depth": 99}, index, fake_embedder)
        assert env["ok"] is False
        assert env["error"]["code"] == "INVALID_INPUT"
        assert "depth" in env["error"]["message"].lower()

    async def test_unknown_section_returns_not_found(
        self, index: DocumentIndex, fake_embedder: FakeEmbedder
    ) -> None:
        env = await dispatch_tool("get_section", {"id": "ghost"}, index, fake_embedder)
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
    async def test_workspace_dispatch_resolves_nearest_repo(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        repo = tmp_path / "repo"
        nested = repo / "docs" / "nested"
        nested.mkdir(parents=True)
        (repo / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
        write_default_config(repo)
        await sync_repo(
            repo,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        resolver = RepoRootResolver(workspace_hint=nested)
        env = await dispatch_workspace_repo_tool("list_documents", {}, resolver, fake_embedder)

        assert env["ok"] is True
        assert env["data"]["root"] == str(repo)
        assert env["trace"]["repo_root"] == str(repo)
        assert any(
            step["name"] == "resolve_repo_root" and step["source"] == "workspace_hint"
            for step in env["trace"]["steps"]
        )

    async def test_workspace_dispatch_project_path_overrides_workspace(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
        write_default_config(repo)
        await sync_repo(
            repo,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        resolver = RepoRootResolver(workspace_hint=tmp_path / "unindexed")
        env = await dispatch_workspace_repo_tool(
            "list_documents",
            {"projectPath": str(repo / "docs")},
            resolver,
            fake_embedder,
        )

        assert env["ok"] is True
        assert env["data"]["root"] == str(repo)
        assert env["trace"]["arguments"]["projectPath"] == str(repo / "docs")
        assert any(
            step["name"] == "resolve_repo_root" and step["source"] == "projectPath"
            for step in env["trace"]["steps"]
        )

    async def test_workspace_dispatch_without_config_fails_closed(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        resolver = RepoRootResolver(workspace_hint=tmp_path)

        env = await dispatch_workspace_repo_tool("list_documents", {}, resolver, fake_embedder)

        assert env["ok"] is False
        assert env["error"]["code"] == "INVALID_CONFIG"
        assert env["error"]["details"]["workspace"] == str(tmp_path)
        assert "projectPath" in env["error"]["message"]
        commands = [step["command"] for step in env["error"]["details"]["next_steps"]]
        assert commands[:2] == ["docsgraph init -y", "docsgraph sync"]

    async def test_workspace_dispatch_bad_project_path_fails_closed(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        resolver = RepoRootResolver(workspace_hint=Path("/unused"))
        project_path = tmp_path / "unindexed"

        env = await dispatch_workspace_repo_tool(
            "list_documents",
            {"projectPath": str(project_path)},
            resolver,
            fake_embedder,
        )

        assert env["ok"] is False
        assert env["error"]["code"] == "INVALID_CONFIG"
        assert env["error"]["details"]["source"] == "projectPath"
        assert env["error"]["details"]["projectPath"] == str(project_path)
        commands = [step["command"] for step in env["error"]["details"]["next_steps"]]
        assert commands[:2] == ["docsgraph init -y", "docsgraph sync"]

    async def test_list_documents_and_route_tool(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        listed = await dispatch_repo_tool("list_documents", {}, tmp_path, fake_embedder)
        assert listed["ok"] is True
        assert listed["data"]["documents"][0]["id"] == "readme"
        assert "documentation" in listed["data"]["usage_guidance"]["prefer_cairn_for"][0]
        assert "source-code symbol" in listed["data"]["usage_guidance"]["prefer_other_tools_for"][0]

        outlined = await dispatch_repo_tool(
            "outline",
            {"doc": "readme", "depth": 1},
            tmp_path,
            fake_embedder,
        )
        assert outlined["ok"] is True
        assert outlined["data"]["doc"] == "readme"

    async def test_list_documents_readme_only_returns_config_guidance(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        listed = await dispatch_repo_tool("list_documents", {}, tmp_path, fake_embedder)

        assert listed["ok"] is True
        guidance = listed["data"]["config_guidance"]
        assert guidance["status"] == "narrow"
        assert ".cairn/config.toml" in guidance["message"]
        assert "guides/**/*.md" in guidance["include_examples"]
        assert "node_modules/**" in guidance["exclude_examples"]

    async def test_list_documents_without_sync_returns_next_steps(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
        write_default_config(tmp_path)

        listed = await dispatch_repo_tool("list_documents", {}, tmp_path, fake_embedder)

        assert listed["ok"] is True
        assert listed["data"]["documents"][0]["state"] == "missing"
        commands = [step["command"] for step in listed["data"]["next_steps"]]
        assert commands[:2] == ["docsgraph sync", "docsgraph status"]

    async def test_search_documents(self, tmp_path: Path, fake_embedder: FakeEmbedder) -> None:
        (tmp_path / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("# Guide\n\nDetailed docs.\n", encoding="utf-8")
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
        assert "ranker" not in env["data"]
        assert all("explanation" not in hit for hit in env["data"]["hits"])
        detailed = await dispatch_repo_tool(
            "search_documents",
            {"query": "detailed docs", "k": 4, "include_details": True},
            tmp_path,
            fake_embedder,
        )
        assert detailed["ok"] is True
        assert "ranker" in detailed["data"]
        assert [hit["anchor"] for hit in env["data"]["hits"]] == [
            hit["anchor"] for hit in detailed["data"]["hits"]
        ]
        for compact, full in zip(env["data"]["hits"], detailed["data"]["hits"], strict=True):
            assert compact["evidence"] == full["evidence"]
            assert "explanation" in full
        assert env["tokens_returned"] < detailed["tokens_returned"]

    async def test_search_keyword_without_doc_searches_all_repo_documents(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text("# Readme\n\nRoot overview.\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "# Guide\n\nThe cross repo needle appears here.\n", encoding="utf-8"
        )
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=fake_embedder,
            index_config=IndexConfig(),
        )

        env = await dispatch_repo_tool(
            "search_keyword",
            {"terms": ["needle"]},
            tmp_path,
            fake_embedder,
        )

        assert env["ok"] is True
        assert any(hit["doc"] == "docs-guide" for hit in env["data"]["hits"])
        assert all("source" in hit for hit in env["data"]["hits"])

    async def test_search_documents_without_sync_returns_setup_steps(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
        write_default_config(tmp_path)

        env = await dispatch_repo_tool(
            "search_documents",
            {"query": "project overview", "k": 4},
            tmp_path,
            fake_embedder,
        )

        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND"
        assert env["error"]["details"]["root"] == str(tmp_path)
        assert env["error"]["details"]["indexed_count"] == 0
        commands = [step["command"] for step in env["error"]["details"]["next_steps"]]
        assert commands[:2] == ["docsgraph sync", "docsgraph status"]

    async def test_repo_document_tool_without_sync_returns_setup_steps(
        self, tmp_path: Path, fake_embedder: FakeEmbedder
    ) -> None:
        (tmp_path / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
        write_default_config(tmp_path)

        env = await dispatch_repo_tool(
            "outline",
            {"doc": "readme", "depth": 1},
            tmp_path,
            fake_embedder,
        )

        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND"
        assert env["error"]["details"]["doc"] == "readme"
        assert env["error"]["details"]["state"] == "missing"
        commands = [step["command"] for step in env["error"]["details"]["next_steps"]]
        assert commands[:2] == ["docsgraph sync", "docsgraph status"]

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
            {"query": "plugin tools install", "k": 2, "related_k": 2, "include_details": True},
            tmp_path,
            fake_embedder,
        )
        assert context["ok"] is True
        assert context["data"]["context_sections"]
        assert context["data"]["relationship_map"]["nodes"]
        assert context["data"]["codegraph_bridge"]["status"] == "not_invoked"
        evidence = await dispatch_repo_tool(
            "repo_context",
            {
                "query": "plugin tools install",
                "queries": ["plugin install", "tools"],
                "level": "evidence",
                "max_context_chars": 1000,
            },
            tmp_path,
            fake_embedder,
        )
        assert evidence["ok"] is True
        assert evidence["data"]["context_sections"][0]["evidence_blocks"]
        assert evidence["data"]["returned_source_characters"] <= 1000
        assert "hits" not in evidence["data"]
        invalid_evidence = await dispatch_repo_tool(
            "repo_context",
            {"query": "plugin", "level": "evidence", "include_details": True},
            tmp_path,
            fake_embedder,
        )
        assert invalid_evidence["ok"] is False
        section = context["data"]["context_sections"][0]
        anchored = await dispatch_repo_tool(
            "get_section", {"id": section["anchor"], "level": "full"}, tmp_path, fake_embedder
        )
        assert anchored["ok"] is True
        assert anchored["data"]["id"] == section["id"]
        assert anchored["data"]["doc"] == section["doc"]
        related = await dispatch_repo_tool(
            "get_related",
            {"id": section["anchor"], "kinds": ["parent", "sibling"]},
            tmp_path,
            fake_embedder,
        )
        assert related["ok"] is True
        conflicting = await dispatch_repo_tool(
            "get_section", {"id": section["anchor"], "doc": "other"}, tmp_path, fake_embedder
        )
        assert conflicting["ok"] is False
        assert "conflicts" in conflicting["error"]["message"]
        for invalid in ("cairn://readme/", "cairn://[invalid/path", "cairn://readme/id?x=1"):
            malformed = await dispatch_repo_tool(
                "get_section", {"id": invalid}, tmp_path, fake_embedder
            )
            assert malformed["ok"] is False
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
        (tmp_path / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
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
