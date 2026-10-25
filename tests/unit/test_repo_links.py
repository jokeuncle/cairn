"""Explicit repository links: source provenance, scope and offline contracts."""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pytest import MonkeyPatch
from typer.testing import CliRunner

from cairn.cli.app import app
from cairn.cli_output import parse_tool_text
from cairn.core.config import IndexConfig
from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.dispatch import dispatch_repo_tool
from cairn.embed.fake import FakeEmbedder
from cairn.index.vectors import Vectors
from cairn.repo import repo_graph, sync_repo, write_default_config
from cairn.repo_links import LinkDocument, document_reference_graph
from cairn.summarize.fake import FakeSummarizer


def _document(doc: str, source: str, *bodies: str) -> LinkDocument:
    return LinkDocument(
        doc,
        source,
        "indexed",
        tuple((f"cairn://{doc}/section-{number}", body) for number, body in enumerate(bodies)),
    )


def _graph(*documents: LinkDocument, **kwargs: Any) -> dict[str, Any]:
    options = {"doc": None, "max_references": 200, "include_evidence": False, **kwargs}
    return document_reference_graph(tuple(documents), **options)


def test_relative_root_encoded_paths_and_pair_counts() -> None:
    graph = _graph(
        _document(
            "a", "docs/deep/a.md", "[first](../b%20c.md#missing) [root](/docs/b%20c.md?q=1#x)\n"
        ),
        _document("b", "docs/b c.md", "Body"),
    )
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert (edge["source"], edge["target"], edge["reference_count"]) == ("doc:a", "doc:b", 2)
    assert edge["source_anchor"] == "cairn://a/section-0"
    assert "#missing" in edge["href"]  # Fragments are not falsely validated.


def test_reference_style_definitions_in_later_sections_and_unicode_spans() -> None:
    body = "中文提示。\n\nSee [details][later].\n"
    graph = _graph(
        _document("a", "a.md", body, "[later]: b.md\n"),
        _document("b", "b.md", "Details"),
        include_evidence=True,
    )
    edge = graph["edges"][0]
    span = edge["source_span"]
    assert body[span["start"] : span["end"]] == "See [details][later].\n"
    excerpt = edge["evidence_span"]
    assert body[excerpt["start"] : excerpt["end"]] == edge["evidence"]
    assert edge["evidence_complete"] is True


def test_non_document_links_and_code_html_headings_are_excluded() -> None:
    body = (
        "# [heading](b.md)\n\n`[inline](b.md)`\n\n```md\n[fenced](b.md)\n```\n\n"
        '<a href="b.md">HTML</a>\n\n<!-- [comment](b.md) -->\n\n'
        "[external](https://example.com/b.md) [scheme](mailto:b.md) "
        "[network](//example.com/b.md) [unknown](missing.md) [self](a.md#x) "
        "[fragment](#x) [escape](../b.md)\n"
    )
    assert _graph(_document("a", "a.md", body), _document("b", "b.md", ""))["edges"] == []


def test_encoded_paths_are_decoded_only_once() -> None:
    graph = _graph(
        _document("a", "a.md", "[literal](b%2520c.md)"),
        _document("literal", "b%20c.md", ""),
        _document("space", "b c.md", ""),
    )
    assert graph["edges"][0]["target"] == "doc:literal"


def test_incident_filter_and_reference_cap_do_not_claim_completeness() -> None:
    documents = (
        _document("a", "a.md", "[b](b.md) [c](c.md)"),
        _document("b", "b.md", "[c](c.md)"),
        _document("c", "c.md", ""),
    )
    incident = _graph(*documents, doc="b")
    assert {(e["source"], e["target"]) for e in incident["edges"]} == {
        ("doc:a", "doc:b"),
        ("doc:b", "doc:c"),
    }
    capped = _graph(*documents, max_references=1)
    assert capped["stats"]["truncated"] and capped["stats"]["total_document_pairs"] == 3
    assert capped == _graph(*documents, max_references=1)


def test_long_source_excerpt_is_verbatim_bounded_and_explicitly_partial() -> None:
    body = "一" * 500 + " [details](b.md)\n"
    edge = _graph(_document("a", "a.md", body), _document("b", "b.md", ""), include_evidence=True)[
        "edges"
    ][0]
    assert edge["evidence"] == body[:240]
    assert edge["evidence_complete"] is False
    assert edge["source_span"]["end"] == len(body)


@given(st.text(alphabet="abcdef0123456789", min_size=1, max_size=30))
def test_arbitrary_external_hosts_cannot_resolve_as_local_documents(host: str) -> None:
    graph = _graph(
        _document("a", "a.md", f"[link](https://{host}/b.md)"), _document("b", "b.md", "")
    )
    assert graph["edges"] == []


@pytest.fixture
async def linked_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a.md").write_text(
        "# A\n\n[Details][later].\n\n## Definitions\n\n[later]: b.md#missing\n"
    )
    (tmp_path / "docs/b.md").write_text("# B\n\n[Return](a.md).\n")
    write_default_config(tmp_path)
    await sync_repo(
        tmp_path,
        summarizer=FakeSummarizer(),
        embedder=FakeEmbedder(dim=64),
        index_config=IndexConfig(),
    )
    return tmp_path


async def test_actual_repo_dispatch_retains_cached_links_and_reports_stale(
    linked_repo: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("graph must not read vectors")

    monkeypatch.setattr(Vectors, "entries", forbidden)
    original = (await repo_graph(linked_repo, view="documents"))["data"]
    assert original["complete"] and len(original["edges"]) == 2
    assert "evidence" not in original["edges"][0]
    (linked_repo / "docs/a.md").write_text("# A\n\nReference removed from current source.\n")
    result = await dispatch_repo_tool("repo_graph", {"view": "documents"}, linked_repo, None)
    assert result["ok"] and result["data"]["edges"] == original["edges"]
    assert result["data"]["stale_documents"] == ["docs-a"]
    assert result["data"]["complete"] is False


async def test_document_cap_missing_index_and_default_view_compatibility(linked_repo: Path) -> None:
    default = (await repo_graph(linked_repo))["data"]
    explicit = (await repo_graph(linked_repo, view="sections"))["data"]
    assert default == explicit and "view" not in default
    assert any(node["kind"] == "section" for node in default["nodes"])
    capped = (await repo_graph(linked_repo, view="documents", max_documents=1))["data"]
    assert capped["stats"]["truncated"] and not capped["complete"]
    focused = (await repo_graph(linked_repo, view="documents", doc="docs-b"))["data"]
    assert len(focused["edges"]) == 2
    with pytest.raises(IndexNotFoundError):
        await repo_graph(linked_repo, view="documents", doc="absent")
    (linked_repo / ".cairn/documents/docs-b/tree.json").unlink()
    broken = (await repo_graph(linked_repo, view="documents"))["data"]
    assert not broken["complete"]
    assert broken["skipped_documents"] or broken["unavailable_documents"]


@pytest.mark.parametrize(
    "options", [{"view": "invalid"}, {"max_documents": 0}, {"max_references": 2001}]
)
async def test_graph_limits_fail_explicitly(linked_repo: Path, options: dict[str, Any]) -> None:
    with pytest.raises(ToolError):
        await repo_graph(linked_repo, **options)


async def test_actual_cli_graph_works_with_invalid_provider(
    linked_repo: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("graph must not construct a provider")

    monkeypatch.setattr(importlib.import_module("cairn.cli.app"), "_make_embedder", forbidden)
    monkeypatch.setenv("CAIRN_EMBED_PROVIDER", "unconfigured-invalid")

    def invoke() -> None:
        result = CliRunner().invoke(
            app,
            [
                "query",
                "tool",
                "repo_graph",
                json.dumps({"view": "documents", "include_evidence": True}),
                "--repo",
                str(linked_repo),
                "--real",
                "--format",
                "text",
            ],
        )
        assert result.exit_code == 0, result.output
        graph = parse_tool_text(result.stdout)
        assert graph["ok"] and len(graph["data"]["edges"]) == 2

    await asyncio.to_thread(invoke)
