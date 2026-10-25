"""Physical model instructions, legacy compatibility and query-role integration."""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from typing import Any

import httpx
from pytest import MonkeyPatch
from typer.testing import CliRunner

from cairn.bench.baseline import NaiveRAG
from cairn.cli.app import app
from cairn.core.config import IndexConfig, load_embed_config
from cairn.embed.base import embed_query_texts
from cairn.embed.fake import FakeEmbedder
from cairn.embed.task_prefix import TaskPrefixEmbedder
from cairn.embed.windowed import WindowedEmbedder
from cairn.providers import make_embedder
from cairn.repo import repo_context, sync_repo, write_default_config
from cairn.summarize.fake import FakeSummarizer
from cairn.tools.base import DocumentIndex
from cairn.tools.search_semantic import search_semantic


class RoleSpy(FakeEmbedder):
    def __init__(self, dim: int = 64) -> None:
        super().__init__(dim=dim)
        self.documents: list[str] = []
        self.queries: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.documents.extend(texts)
        return await super().embed(texts)

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        self.queries.extend(texts)
        return await super().embed(texts)


async def test_query_extension_is_optional_and_preserves_legacy_window_values() -> None:
    legacy = FakeEmbedder(dim=8)
    windows = WindowedEmbedder(legacy, max_input_bytes=16)
    values = ["", "short", "汉字 plus source\n" * 8]
    assert await embed_query_texts(legacy, values) == await legacy.embed(values)
    assert await embed_query_texts(windows, values) == await windows.embed(values)


async def test_task_prefix_preserves_native_roles_and_empty_inputs() -> None:
    spy = RoleSpy()
    embedder = TaskPrefixEmbedder(spy, document_prefix="DOC: ", query_prefix="QUERY: ")
    assert await embedder.embed([]) == []
    assert await embed_query_texts(embedder, []) == []
    assert spy.documents == spy.queries == []
    await embedder.embed(["source"])
    await embed_query_texts(embedder, ["question"])
    assert spy.documents == ["DOC: source"]
    assert spy.queries == ["QUERY: question"]


def test_policy_identity_is_stable_sensitive_to_both_roles_and_not_plaintext() -> None:
    base = FakeEmbedder(dim=8)
    assert TaskPrefixEmbedder(base).name == base.name
    one = TaskPrefixEmbedder(base, document_prefix="a", query_prefix="bc")
    same = TaskPrefixEmbedder(base, document_prefix="a", query_prefix="bc")
    other = TaskPrefixEmbedder(base, document_prefix="ab", query_prefix="c")
    spaced = TaskPrefixEmbedder(base, document_prefix="a ", query_prefix="bc")
    changed_query = TaskPrefixEmbedder(base, document_prefix="a", query_prefix="bc ")
    assert one.name == same.name
    assert len({one.name, other.name, spaced.name, changed_query.name}) == 4
    assert "task-prefix-v1:" in one.name


async def test_factory_sends_correct_instruction_on_every_physical_http_window(
    monkeypatch: MonkeyPatch,
) -> None:
    for key, value in {
        "PROVIDER": "windowed-openai-compatible",
        "MODEL": "unit-model",
        "DIM": "2",
        "BASE_URL": "http://unit.test/v1",
        "API_KEY": "",
        "DOCUMENT_PREFIX": "search_document: ",
        "QUERY_PREFIX": "search_query: ",
    }.items():
        monkeypatch.setenv("CAIRN_EMBED_" + key, value)
    inputs: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/embeddings"
        inputs.extend(body["input"])
        return httpx.Response(
            200, json={"data": [{"embedding": [1.0, 0.0]} for _ in body["input"]]}
        )

    client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=transport, **kwargs)
    )
    config = load_embed_config()
    assert config.document_prefix == "search_document: "
    assert config.query_prefix == "search_query: "
    embedder = make_embedder(False)
    assert isinstance(embedder, WindowedEmbedder)
    assert isinstance(embedder.delegate, TaskPrefixEmbedder)
    body = "汉字与原文 " * 500
    await embedder.embed([body])
    document_inputs = list(inputs)
    assert len(document_inputs) > 1
    assert all(text.startswith(config.document_prefix) for text in document_inputs)
    assert "".join(text.removeprefix(config.document_prefix) for text in document_inputs) == body
    inputs.clear()
    await embed_query_texts(embedder, [body])
    assert all(text.startswith(config.query_prefix) for text in inputs)
    assert "".join(text.removeprefix(config.query_prefix) for text in inputs) == body
    monkeypatch.setenv("CAIRN_EMBED_DOCUMENT_PREFIX", "")
    monkeypatch.setenv("CAIRN_EMBED_QUERY_PREFIX", "")
    plain = make_embedder(False)
    assert "task-prefix-v1:" not in plain.name


async def test_document_lookup_uses_query_role(index: DocumentIndex) -> None:
    spy = RoleSpy(dim=index.vectors.dim)
    await search_semantic(index, embedder=spy, query="pip", k=3)
    assert spy.queries == ["pip"]
    assert spy.documents == []


async def test_flat_rag_control_uses_the_same_query_role(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    spy = RoleSpy()
    baseline = NaiveRAG(spy)
    monkeypatch.setattr(baseline, "_sync_retrieve", lambda *args: [])
    await baseline.retrieve("question", out_dir=tmp_path)
    assert spy.queries == ["question"]
    assert spy.documents == []


async def test_repository_index_and_lookup_keep_roles_separate_and_source_untouched(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text("# Guide\n\nconnection_limit = 37\n")
    write_default_config(tmp_path)
    spy = RoleSpy()
    embedder = TaskPrefixEmbedder(spy, document_prefix="DOC: ", query_prefix="QUERY: ")
    await sync_repo(
        tmp_path, summarizer=FakeSummarizer(), embedder=embedder, index_config=IndexConfig()
    )
    assert spy.documents and all(text.startswith("DOC: ") for text in spy.documents)
    assert not spy.queries
    result = await repo_context(tmp_path, query="connection_limit", embedder=embedder, level="full")
    assert spy.queries == ["QUERY: connection_limit"]
    content = "\n".join(s["content"] for s in result["data"]["context_sections"])
    assert "connection_limit = 37" in content
    assert "DOC: " not in content and "QUERY: " not in content


async def test_cli_rejects_changed_prefix_policy_before_any_query_embedding(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text("# Guide\n\nconnection_limit = 37\n")
    write_default_config(tmp_path)
    await sync_repo(
        tmp_path,
        summarizer=FakeSummarizer(),
        embedder=FakeEmbedder(dim=64),
        index_config=IndexConfig(),
    )
    spy = RoleSpy()
    changed = TaskPrefixEmbedder(spy, query_prefix="QUERY: ")
    monkeypatch.setattr(
        importlib.import_module("cairn.cli.app"), "_make_embedder", lambda _: changed
    )

    def invoke() -> None:
        result = CliRunner().invoke(
            app,
            [
                "query",
                "tool",
                "search_documents",
                '{"query":"connection_limit"}',
                "--repo",
                str(tmp_path),
                "--real",
            ],
        )
        assert result.exit_code != 0
        data: dict[str, Any] = json.loads(result.stdout)
        assert not data["ok"] and "embedder" in data["error"]["message"]

    await asyncio.to_thread(invoke)
    assert spy.documents == spy.queries == []
