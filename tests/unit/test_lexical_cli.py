"""Explicit offline query mode, provider/vector isolation and CLI contracts."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

from cairn.cli.app import app
from cairn.cli_output import parse_tool_text
from cairn.core.config import IndexConfig
from cairn.core.errors import ToolError
from cairn.dispatch import dispatch_repo_tool
from cairn.embed.fake import FakeEmbedder
from cairn.index.vectors import Vectors
from cairn.repo import repo_context, search_repo_documents, sync_repo, write_default_config
from cairn.summarize.fake import FakeSummarizer


@pytest.fixture
async def cached_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text(
        "# Guide\n\nOverview.\n\n## Limits\n\nconnection_limit = 37\n\n"
        "```python\n" + 'print("quoted source")\n' * 30 + "```\n"
    )
    write_default_config(tmp_path)
    await sync_repo(
        tmp_path,
        summarizer=FakeSummarizer(),
        embedder=FakeEmbedder(dim=64),
        index_config=IndexConfig(),
    )
    return tmp_path


async def test_lexical_does_not_read_vectors_and_keeps_source(
    cached_repo: Path, monkeypatch: MonkeyPatch
) -> None:
    async def forbidden_entries(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("lexical retrieval must not read vector entries")

    monkeypatch.setattr(Vectors, "entries", forbidden_entries)
    result = await repo_context(
        cached_repo,
        query="connection_limit",
        retrieval="lexical",
        level="evidence",
        k=3,
        max_section_chars=2000,
    )
    data = result["data"]
    assert data["retrieval_mode"] == "lexical"
    assert data["context_sections"]
    assert any(
        "connection_limit = 37" in b["text"]
        for s in data["context_sections"]
        for b in s["evidence_blocks"]
    )
    miss = await search_repo_documents(cached_repo, query="zzqunfindablezzq", retrieval="lexical")
    assert miss["data"]["hits"] == []


async def test_default_hybrid_and_lexical_caches_remain_independent(cached_repo: Path) -> None:
    embedder = FakeEmbedder(dim=64)
    before = await search_repo_documents(cached_repo, query="connection_limit", embedder=embedder)
    await search_repo_documents(cached_repo, query="connection_limit", retrieval="lexical")
    after = await search_repo_documents(
        cached_repo, query="connection_limit", embedder=embedder, retrieval="hybrid"
    )
    assert before == after
    with pytest.raises(ToolError, match="requires an embedding provider"):
        await search_repo_documents(cached_repo, query="connection_limit")


async def test_lexical_preserves_stale_warning_and_reads_cached_body(cached_repo: Path) -> None:
    path = cached_repo / "docs/guide.md"
    path.write_text(path.read_text().replace("connection_limit = 37", "connection_limit = 99"))
    result = await repo_context(
        cached_repo,
        query="connection_limit",
        retrieval="lexical",
        level="full",
    )
    data = result["data"]
    assert data["stale_documents"] == ["docs-guide"]
    assert any("connection_limit = 37" in s["content"] for s in data["context_sections"])
    assert all("connection_limit = 99" not in s["content"] for s in data["context_sections"])


async def test_mcp_dispatch_supports_provider_free_search_and_truthful_trace(
    cached_repo: Path,
) -> None:
    result = await dispatch_repo_tool(
        "search_documents", {"query": "connection_limit", "retrieval": "lexical"}, cached_repo, None
    )
    assert result["ok"]
    assert result["data"]["retrieval_mode"] == "lexical"
    steps = [s["name"] for s in result["trace"]["steps"]]
    assert "lexical_query" in steps and "embed_query" not in steps


async def test_cli_reads_and_lexical_queries_do_not_construct_provider(
    cached_repo: Path, monkeypatch: MonkeyPatch
) -> None:
    def forbidden_provider(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("cached reads must not construct an embedding provider")

    monkeypatch.setattr(
        importlib.import_module("cairn.cli.app"), "_make_embedder", forbidden_provider
    )
    monkeypatch.setenv("CAIRN_EMBED_PROVIDER", "invalid-unconfigured-provider")
    runner = CliRunner()
    # CliRunner must run outside the fixture's active asyncio loop.
    import asyncio

    def calls() -> None:
        search = runner.invoke(
            app,
            [
                "query",
                "tool",
                "repo_context",
                '{"query":"connection_limit","level":"evidence"}',
                "--repo",
                str(cached_repo),
                "--retrieval",
                "lexical",
                "--format",
                "text",
                "--real",
            ],
        )
        assert search.exit_code == 0, search.output
        assert parse_tool_text(search.stdout)["data"]["context_sections"]
        section = runner.invoke(
            app,
            [
                "query",
                "tool",
                "get_section",
                '{"doc":"docs-guide","id":"guide/limits","level":"full"}',
                "--repo",
                str(cached_repo),
                "--format",
                "text",
            ],
        )
        assert section.exit_code == 0, section.output
        assert "connection_limit" in parse_tool_text(section.stdout)["data"]["content"]

    await asyncio.to_thread(calls)


def test_cli_rejects_bad_arguments_before_provider_setup(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("CAIRN_EMBED_PROVIDER", "invalid-unconfigured-provider")
    runner = CliRunner()
    for arguments in [
        "[]",
        '{"query":12}',
        '{"query":"x","queries":[12]}',
        '{"projectPath":"/other"}',
    ]:
        result = runner.invoke(app, ["query", "tool", "repo_context", arguments])
        assert result.exit_code != 0
        assert not json.loads(result.stdout)["ok"]


async def test_cli_hybrid_checks_index_provider_compatibility(
    cached_repo: Path, monkeypatch: MonkeyPatch
) -> None:
    import asyncio

    module = importlib.import_module("cairn.cli.app")
    monkeypatch.setattr(module, "_make_embedder", lambda _: FakeEmbedder(dim=32))

    def invoke() -> None:
        result = CliRunner().invoke(
            app,
            [
                "query",
                "tool",
                "search_documents",
                '{"query":"connection_limit"}',
                "--repo",
                str(cached_repo),
            ],
        )
        assert result.exit_code != 0
        payload = json.loads(result.stdout)
        assert not payload["ok"]
        assert "embedder" in payload["error"]["message"]

    await asyncio.to_thread(invoke)


async def test_backend_progress_uses_stderr_not_the_result_stream(
    cached_repo: Path, monkeypatch: MonkeyPatch
) -> None:
    import asyncio

    async def handler(*args: Any, **kwargs: Any) -> dict[str, Any]:
        print("BACKEND PROGRESS")
        return {"ok": True, "data": {"content": 'print("source")\n' * 100}}

    monkeypatch.setattr(importlib.import_module("cairn.cli.app"), "dispatch_repo_tool", handler)

    def invoke() -> None:
        result = CliRunner().invoke(
            app,
            [
                "query",
                "tool",
                "outline",
                "--repo",
                str(cached_repo),
                "--format",
                "text",
            ],
        )
        assert result.exit_code == 0, result.output
        assert parse_tool_text(result.stdout)["ok"]
        assert "BACKEND PROGRESS" not in result.stdout
        assert "BACKEND PROGRESS" in result.stderr

    await asyncio.to_thread(invoke)
