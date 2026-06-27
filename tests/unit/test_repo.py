"""Tests for repository-level Cairn documentation workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from cairn import repo_search as repo_search_module
from cairn.cli.config import IndexConfig
from cairn.embed.fake import FakeEmbedder
from cairn.engine.manifest import read_manifest
from cairn.repo import (
    DEFAULT_EXCLUDE,
    RepoConfig,
    discover_documents,
    load_repo_config,
    load_repo_document_index,
    repo_context,
    repo_graph,
    repo_impact,
    repo_status,
    search_repo_documents,
    sync_lock_path,
    sync_repo,
    write_default_config,
)
from cairn.summarize.base import SummaryLevel
from cairn.summarize.fake import FakeSummarizer


def _write_repo_docs(root: Path) -> None:
    (root / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text(
        "# Guide\n\nDetailed docs.\n", encoding="utf-8"
    )


class _BlockingSummarizer:
    name = FakeSummarizer.name

    def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
        self.started = started
        self.release = release
        self.fake = FakeSummarizer()

    async def summarize(
        self,
        *,
        title: str,
        body: str,
        level: SummaryLevel,
    ) -> str:
        self.started.set()
        await self.release.wait()
        return await self.fake.summarize(title=title, body=body, level=level)


def _write_complex_repo_docs(root: Path) -> None:
    (root / "README.md").write_text(
        "# Project Atlas\n\nRepository documentation graph for MCP agents.\n",
        encoding="utf-8",
    )
    (root / "docs" / "specs").mkdir(parents=True)
    (root / "docs" / "ops").mkdir(parents=True)
    (root / "docs" / "private").mkdir(parents=True)
    (root / "docs" / "specs" / "storage.md").write_text(
        "\n".join(
            [
                "# Storage Spec",
                "",
                "Vector data is stored under `.cairn/documents/<doc_id>/vectors.lance`.",
                "Repo manifests live at `.cairn/manifest.json`.",
            ]
        ),
        encoding="utf-8",
    )
    (root / "docs" / "specs" / "plugins.md").write_text(
        "\n".join(
            [
                "# Plugin System",
                "",
                "Plug-ins provide parser, summarizer, embedder, and xref interfaces.",
                "MCP tools route by doc id in repository mode.",
            ]
        ),
        encoding="utf-8",
    )
    (root / "docs" / "ops" / "runbook.md").write_text(
        "# Runbook\n\nIncident response escalation policy.\n", encoding="utf-8"
    )
    (root / "docs" / "private" / "secret.md").write_text(
        "# Secret\n\nShould be excluded.\n", encoding="utf-8"
    )
    (root / "docs" / "A B.md").write_text("# Alpha\n\nFirst duplicate.\n", encoding="utf-8")
    (root / "docs" / "a-b.md").write_text("# Alpha\n\nSecond duplicate.\n", encoding="utf-8")


class TestRepoConfig:
    def test_default_config_discovers_repo_docs(self, tmp_path: Path) -> None:
        _write_repo_docs(tmp_path)
        (tmp_path / "docs" / "page.html").write_text(
            "<h1>HTML doc</h1>", encoding="utf-8"
        )
        write_default_config(tmp_path)
        cfg = load_repo_config(tmp_path)

        docs = discover_documents(tmp_path, cfg)

        assert [doc.id for doc in docs] == ["readme", "docs-guide"]
        assert docs[0].relative_source == "README.md"
        assert docs[1].relative_source == "docs/guide.md"

    def test_default_config_discovers_one_level_nested_readmes(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "README.md").write_text(
            "# Backend\n\nAPI service docs.\n", encoding="utf-8"
        )
        (tmp_path / "examples" / "demo").mkdir(parents=True)
        (tmp_path / "examples" / "demo" / "README.md").write_text(
            "# Demo\n\nDeep example docs.\n", encoding="utf-8"
        )
        (tmp_path / ".pytest_cache").mkdir()
        (tmp_path / ".pytest_cache" / "README.md").write_text(
            "# pytest cache\n\nTool cache docs.\n", encoding="utf-8"
        )
        write_default_config(tmp_path)
        cfg = load_repo_config(tmp_path)

        docs = discover_documents(tmp_path, cfg)
        ids = {doc.id for doc in docs}

        assert "readme" in ids
        assert "backend-readme" in ids
        assert "examples-demo-readme" not in ids
        assert "pytest-cache-readme" not in ids

    def test_default_excludes_skip_nested_dependency_and_build_dirs(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "apps" / "web").mkdir(parents=True)
        (tmp_path / "apps" / "web" / "README.md").write_text(
            "# Web app\n\nFrontend docs.\n", encoding="utf-8"
        )
        noisy_paths = [
            "apps/web/node_modules/pkg/README.md",
            "apps/web/dist/README.md",
            "packages/lib/build/README.md",
            "docs/site/README.md",
        ]
        for rel in noisy_paths:
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Generated\n\nDo not index.\n", encoding="utf-8")

        cfg = RepoConfig(include=("**/*.md",), exclude=DEFAULT_EXCLUDE)
        docs = discover_documents(tmp_path, cfg)

        assert [doc.relative_source for doc in docs] == ["apps/web/README.md"]

    def test_markitdown_config_discovers_extra_formats(self, tmp_path: Path) -> None:
        _write_repo_docs(tmp_path)
        (tmp_path / "docs" / "page.html").write_text(
            "<h1>HTML doc</h1>", encoding="utf-8"
        )
        write_default_config(tmp_path, enable_markitdown=True)
        cfg = load_repo_config(tmp_path)

        docs = discover_documents(tmp_path, cfg)

        assert "docs-page" in {doc.id for doc in docs}
        assert cfg.enable_markitdown is True

    def test_complex_discovery_handles_excludes_and_duplicate_ids(
        self, tmp_path: Path
    ) -> None:
        _write_complex_repo_docs(tmp_path)
        write_default_config(tmp_path)
        (tmp_path / ".cairn" / "config.toml").write_text(
            "\n".join(
                [
                    'documents_dir = "documents"',
                    "enable_markitdown = false",
                    'primary_doc = "readme"',
                    'include = ["*.md", "docs/**/*.md"]',
                    'exclude = ["docs/private/**"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        cfg = load_repo_config(tmp_path)

        docs = discover_documents(tmp_path, cfg)
        ids = [doc.id for doc in docs]

        assert "docs-private-secret" not in ids
        assert "docs-a-b" in ids
        assert "docs-a-b-2" in ids


class TestRepoSync:
    async def test_sync_indexes_discovered_documents(self, tmp_path: Path) -> None:
        _write_repo_docs(tmp_path)
        write_default_config(tmp_path)

        results = await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
            index_config=IndexConfig(),
        )

        assert {result.id for result in results} == {"readme", "docs-guide"}
        assert all(result.rebuilt for result in results)
        status = repo_status(tmp_path)
        assert status.indexed_count == 2
        assert status.missing_count == 0
        assert (tmp_path / ".cairn" / "manifest.json").exists()
        assert load_repo_document_index(tmp_path).doc_id == "readme"

    async def test_sync_skips_unchanged_documents(self, tmp_path: Path) -> None:
        _write_repo_docs(tmp_path)
        write_default_config(tmp_path)
        first = await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
            index_config=IndexConfig(),
        )
        indexed_at = {
            result.id: read_manifest(result.manifest_path.parent).indexed_at
            for result in first
            if result.manifest_path is not None
        }

        second = await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
            index_config=IndexConfig(),
        )

        assert {result.id for result in second} == {"readme", "docs-guide"}
        assert all(result.ok for result in second)
        assert all(not result.rebuilt for result in second)
        assert {
            result.id: read_manifest(result.manifest_path.parent).indexed_at
            for result in second
            if result.manifest_path is not None
        } == indexed_at

    async def test_concurrent_sync_waits_for_repo_lock(self, tmp_path: Path) -> None:
        _write_repo_docs(tmp_path)
        write_default_config(tmp_path)
        started = asyncio.Event()
        release = asyncio.Event()
        second_progress: list[str] = []

        first_task = asyncio.create_task(
            sync_repo(
                tmp_path,
                summarizer=_BlockingSummarizer(started, release),
                embedder=FakeEmbedder(dim=32),
                index_config=IndexConfig(),
            )
        )
        await asyncio.wait_for(started.wait(), timeout=2)

        second_task = asyncio.create_task(
            sync_repo(
                tmp_path,
                summarizer=FakeSummarizer(),
                embedder=FakeEmbedder(dim=32),
                index_config=IndexConfig(),
                progress=second_progress.append,
            )
        )
        for _ in range(20):
            if any(message.startswith("sync: waiting") for message in second_progress):
                break
            await asyncio.sleep(0.01)

        assert any(message.startswith("sync: waiting") for message in second_progress)
        release.set()
        first = await asyncio.wait_for(first_task, timeout=5)
        second = await asyncio.wait_for(second_task, timeout=5)

        assert all(result.rebuilt for result in first)
        assert all(result.ok for result in second)
        assert all(not result.rebuilt for result in second)
        assert "sync: acquired sync lock" in second_progress
        assert sync_lock_path(tmp_path).exists()
        assert sync_lock_path(tmp_path).read_text(encoding="utf-8") == ""

    async def test_status_marks_changed_docs_stale(self, tmp_path: Path) -> None:
        _write_repo_docs(tmp_path)
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
            index_config=IndexConfig(),
        )

        (tmp_path / "README.md").write_text(
            "# Readme\n\nProject overview changed.\n", encoding="utf-8"
        )

        status = repo_status(tmp_path)
        readme = next(doc for doc in status.documents if doc.id == "readme")
        assert readme.state == "stale"
        assert readme.source_file_hash != readme.indexed_source_file_hash

    async def test_orphaned_status_hashes_relative_source_from_repo_root(
        self, tmp_path: Path
    ) -> None:
        _write_repo_docs(tmp_path)
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
            index_config=IndexConfig(),
        )
        indexed = repo_status(tmp_path)
        readme_hash = next(
            doc for doc in indexed.documents if doc.id == "readme"
        ).source_file_hash
        (tmp_path / ".cairn" / "config.toml").write_text(
            "\n".join(
                [
                    'documents_dir = "documents"',
                    "enable_markitdown = false",
                    'include = ["docs/guide.md"]',
                    "exclude = []",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        status = repo_status(tmp_path)

        orphaned = next(doc for doc in status.documents if doc.id == "readme")
        assert orphaned.state == "orphaned"
        assert orphaned.indexed_source_file_hash == readme_hash

    async def test_search_repo_documents_reports_stale_sources(
        self, tmp_path: Path
    ) -> None:
        _write_repo_docs(tmp_path)
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        (tmp_path / "README.md").write_text(
            "# Readme\n\nProject overview changed.\n", encoding="utf-8"
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="project overview",
            k=4,
        )

        assert "readme" in result["data"]["stale_documents"]

    async def test_sync_continues_when_one_document_fails(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text(
            "# Readme\n\nProject overview.\n", encoding="utf-8"
        )
        (tmp_path / "broken.pdf").write_bytes(b"not a real pdf")
        write_default_config(tmp_path)
        (tmp_path / ".cairn" / "config.toml").write_text(
            "\n".join(
                [
                    'documents_dir = "documents"',
                    'primary_doc = "readme"',
                    'include = ["README.md", "broken.pdf"]',
                    'exclude = []',
                    "",
                ]
            ),
            encoding="utf-8",
        )

        results = await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
            index_config=IndexConfig(),
        )

        assert {result.id for result in results} == {"readme", "broken"}
        assert next(result for result in results if result.id == "readme").ok is True
        broken = next(result for result in results if result.id == "broken")
        assert broken.ok is False
        assert broken.error
        status = repo_status(tmp_path)
        assert status.indexed_count == 1
        assert status.error_count == 1


class TestRepoSearch:
    def test_source_locale_recognizes_script_and_region_segments(self) -> None:
        assert repo_search_module._source_locale("docs/zh-hant/index.md") == "zh"
        assert repo_search_module._source_locale("docs/pt-br/index.md") == "pt"
        assert repo_search_module._source_locale("docs/en-us/index.md") == "en"

    def test_graph_scores_do_not_inflate_missing_shortlist_neighbors(self) -> None:
        first = repo_search_module._RepoSectionRecord(
            doc_id="doc",
            source="doc.md",
            index=cast(Any, None),
            section_id="first",
            title="First",
            body="",
            synopsis="",
            vector=(),
            haystacks=("", "", "", "", ""),
            token_counts={},
            token_count=0,
        )
        second = repo_search_module._RepoSectionRecord(
            doc_id="doc",
            source="doc.md",
            index=cast(Any, None),
            section_id="second",
            title="Second",
            body="",
            synopsis="",
            vector=(),
            haystacks=("", "", "", "", ""),
            token_counts={},
            token_count=0,
        )
        cache = repo_search_module._RepoSearchCache(
            signature=(),
            records=(first, second),
            skipped=(),
            doc_dims={},
            df={},
            avg_token_count=0.0,
            graph_neighbors={
                ("doc", "first"): (
                    (("doc", "second"), 1.0),
                    (("doc", "missing"), 1.0),
                )
            },
            record_index_by_key={("doc", "first"): 0, ("doc", "second"): 1},
            vector_matrices={},
            vector_record_indices={},
        )
        hits = [
            repo_search_module._RepoScoredHit(
                record=first,
                score=0.0,
                vector_score=0.0,
                lexical_score=0.0,
                sparse_score=0.0,
                graph_score=0.0,
                base_score=0.0,
                rank_factor=1.0,
                identity_bonus=0.0,
            ),
            repo_search_module._RepoScoredHit(
                record=second,
                score=1.0,
                vector_score=1.0,
                lexical_score=0.0,
                sparse_score=0.0,
                graph_score=0.0,
                base_score=1.0,
                rank_factor=1.0,
                identity_bonus=0.0,
            ),
        ]

        repo_search_module._apply_graph_scores(hits, cache)

        assert hits[0].graph_score == 0.5

    async def test_search_repo_documents_merges_hits(self, tmp_path: Path) -> None:
        _write_repo_docs(tmp_path)
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="detailed docs",
            k=4,
        )

        hits = result["data"]["hits"]
        assert hits
        assert any(hit["doc"] == "docs-guide" for hit in hits)
        assert all({"doc", "source", "id", "anchor"} <= set(hit) for hit in hits)
        explanation = hits[0]["explanation"]
        assert explanation["dominant_signal"] in {
            "vector",
            "lexical",
            "sparse",
            "graph",
        }
        assert {"vector", "lexical", "sparse", "graph"} <= set(
            explanation["signals"]
        )
        assert isinstance(explanation["matched_terms"], list)

    async def test_search_repo_documents_handles_complex_repo(
        self, tmp_path: Path
    ) -> None:
        _write_complex_repo_docs(tmp_path)
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="where is vector data stored",
            k=5,
        )

        hits = result["data"]["hits"]
        assert hits[0]["doc"] == "docs-specs-storage"
        assert hits[0]["lexical_score"] > 0
        assert "vector_score" in hits[0]
        assert hits[0]["explanation"]["dominant_signal"] in {
            "lexical",
            "sparse",
            "vector",
            "graph",
        }
        assert "vector" in hits[0]["explanation"]["signals"]

    async def test_repo_context_returns_composite_context(
        self, tmp_path: Path
    ) -> None:
        _write_complex_repo_docs(tmp_path)
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await repo_context(
            tmp_path,
            embedder=embedder,
            query="where is vector data stored",
            k=2,
            related_k=2,
        )

        data = result["data"]
        assert data["context_sections"]
        assert data["relationship_map"]["nodes"]
        assert data["codegraph_bridge"]["status"] == "not_invoked"

    async def test_repo_graph_returns_relationship_map(self, tmp_path: Path) -> None:
        _write_complex_repo_docs(tmp_path)
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await repo_graph(tmp_path, doc="docs-specs-storage")

        data = result["data"]
        assert any(node["kind"] == "document" for node in data["nodes"])
        assert any(node["kind"] == "section" for node in data["nodes"])
        assert any(edge["kind"] == "contains" for edge in data["edges"])
        assert data["codegraph_bridge"]["status"] == "external"

    async def test_repo_impact_reports_section_surfaces(self, tmp_path: Path) -> None:
        _write_complex_repo_docs(tmp_path)
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await repo_impact(
            tmp_path,
            doc="docs-specs-storage",
            id="storage-spec",
        )

        data = result["data"]
        assert data["scope"] == "section"
        assert data["doc"] == "docs-specs-storage"
        assert "repo_context" in data["affected_surfaces"]
        assert any("CodeGraph" in note for note in data["notes"])

    async def test_search_repo_documents_skips_incompatible_indexes(
        self, tmp_path: Path
    ) -> None:
        _write_repo_docs(tmp_path)
        write_default_config(tmp_path)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=FakeEmbedder(dim=64),
            query="detailed docs",
            k=4,
        )

        assert result["data"]["hits"] == []
        assert {item["doc"] for item in result["data"]["skipped_documents"]} == {
            "readme",
            "docs-guide",
        }
        assert result["data"]["embedding_mismatch"] == {
            "query_dim": 64,
            "index_dims": [32],
            "documents": ["docs-guide", "readme"],
        }

    async def test_search_repo_documents_diversifies_docs_by_default(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text(
            "# Alpha Root\n\nalpha topic overview.\n\n## Alpha Details\n\nalpha details.\n",
            encoding="utf-8",
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "# Alpha Guide\n\nalpha guide.\n", encoding="utf-8"
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        diversified = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="alpha",
            k=4,
        )
        expanded = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="alpha",
            k=4,
            sections_per_doc=2,
        )

        diversified_docs = [hit["doc"] for hit in diversified["data"]["hits"]]
        expanded_docs = [hit["doc"] for hit in expanded["data"]["hits"]]
        assert len(diversified_docs) == len(set(diversified_docs))
        assert expanded_docs.count("readme") >= 2

    async def test_search_repo_documents_prefers_doc_diversity_before_repeats(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text(
            "# Alpha Root\n\nalpha topic overview.\n\n## Alpha Details\n\nalpha details.\n",
            encoding="utf-8",
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "# Alpha Guide\n\nalpha guide.\n", encoding="utf-8"
        )
        (tmp_path / "docs" / "ops.md").write_text(
            "# Alpha Ops\n\nalpha operations.\n", encoding="utf-8"
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="alpha",
            k=4,
            sections_per_doc=2,
        )

        docs = [hit["doc"] for hit in result["data"]["hits"]]
        assert len(docs[:3]) == len(set(docs[:3]))
        assert len(docs) == 4

    async def test_search_repo_documents_uses_configured_default_sections_per_doc(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text(
            "# Alpha Root\n\nalpha topic overview.\n\n## Alpha Details\n\nalpha details.\n",
            encoding="utf-8",
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "# Alpha Guide\n\nalpha guide.\n", encoding="utf-8"
        )
        write_default_config(tmp_path)
        cfg_path = tmp_path / ".cairn" / "config.toml"
        cfg_path.write_text(
            cfg_path.read_text(encoding="utf-8").replace(
                "search_sections_per_doc = 1",
                "search_sections_per_doc = 2",
            ),
            encoding="utf-8",
        )
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="alpha",
            k=4,
        )

        hits = result["data"]["hits"]
        assert result["data"]["sections_per_doc"] == 2
        assert [hit["doc"] for hit in hits].count("readme") >= 2

    async def test_search_repo_documents_boosts_command_phrases(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "auth-cli.md").write_text(
            "\n".join(
                [
                    "# Auth CLI",
                    "",
                    "To add credentials for a service, run `uv auth login example.com`.",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_path / "docs" / "indexes.md").write_text(
            "\n".join(
                [
                    "# Package Indexes",
                    "",
                    "Alternative package indexes require authentication for packages.",
                ]
            ),
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="authenticate to package indexes with uv auth login",
            k=3,
        )

        assert result["data"]["hits"][0]["doc"] == "docs-auth-cli"

    async def test_search_repo_documents_boosts_eval_variants(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "AGENTS.md").write_text(
            "\n".join(
                [
                    "# Development Workflow",
                    "",
                    "Contributors write tests for agents and evaluate changes.",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "evals.md").write_text(
            "\n".join(
                [
                    "# Pydantic Evals",
                    "",
                    "Online evaluation lets teams measure agent behavior.",
                ]
            ),
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="evaluate agents and write tests",
            k=3,
        )

        assert result["data"]["hits"][0]["doc"] == "docs-evals"

    async def test_search_repo_documents_boosts_dependency_injection_variants(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "dependencies.md").write_text(
            "\n".join(
                [
                    "# Dependencies",
                    "",
                    "Dependency injection provides typed deps for agent runs.",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_path / "docs" / "multi-agent-applications.md").write_text(
            "\n".join(
                [
                    "# Multi-agent Applications",
                    "",
                    "Agents can hand off between agent runs in complex workflows.",
                ]
            ),
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="inject dependencies into agent runs",
            k=3,
        )

        assert result["data"]["hits"][0]["doc"] == "docs-dependencies"

    async def test_search_repo_documents_does_not_overtrust_sparse_hits(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "agent.md").write_text(
            "\n".join(
                [
                    "# Agent",
                    "",
                    "## Streaming Events and Final Output",
                    "",
                    "Stream structured responses and events from an agent run.",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_path / "docs" / "capabilities.md").write_text(
            "\n".join(
                [
                    "# Capabilities",
                    "",
                    "## Event stream hook",
                    "",
                    "The event stream hook observes stream events for API capabilities.",
                    "Event stream hook entries are useful for low-level integrations.",
                ]
            ),
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="stream structured responses and events from a run",
            k=3,
        )

        hits = result["data"]["hits"]
        assert hits[0]["doc"] == "docs-agent"
        assert hits[0]["sparse_score"] > 0
        assert "graph_score" in hits[0]

    async def test_search_repo_documents_prefers_overview_for_broad_queries(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "tools.md").write_text(
            "\n".join(
                [
                    "# Tools",
                    "",
                    "Tools let agents call Python functions during a run.",
                    "",
                    "## Registering tools",
                    "",
                    "Register function tools on an agent.",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_path / "docs" / "deferred-tools.md").write_text(
            "\n".join(
                [
                    "# Deferred Tools",
                    "",
                    "Deferred tools are specialized external tool execution hooks.",
                    "Use deferred tools when a workflow must pause for approval.",
                ]
            ),
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="how do tools work in agents",
            k=3,
        )

        assert result["data"]["hits"][0]["doc"] == "docs-tools"

    async def test_search_repo_documents_uses_doc_identity_for_topic_pages(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "mcp-server.md").write_text(
            "\n".join(
                [
                    "# MCP Server",
                    "",
                    "Expose a server endpoint for tools and resources.",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_path / "docs" / "mcp-client.md").write_text(
            "\n".join(
                [
                    "# MCP Client",
                    "",
                    "The client can connect to a remote MCP server.",
                    "Client configuration may mention server URLs many times.",
                ]
            ),
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="how to expose an MCP server",
            k=3,
        )

        assert result["data"]["hits"][0]["doc"] == "docs-mcp-server"

    async def test_search_repo_documents_shortlists_large_surfaces(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        for index in range(6):
            topic = "needle topic" if index == 5 else f"filler topic {index}"
            (tmp_path / "docs" / f"page-{index}.md").write_text(
                f"# Page {index}\n\n{topic} with reusable operations notes.\n",
                encoding="utf-8",
            )
        monkeypatch.setattr(repo_search_module, "_REPO_SEARCH_FULL_SCORE_LIMIT", 2)
        monkeypatch.setattr(repo_search_module, "_REPO_SEARCH_SHORTLIST_MIN", 2)
        monkeypatch.setattr(repo_search_module, "_REPO_SEARCH_SHORTLIST_PER_RESULT", 1)
        monkeypatch.setattr(
            repo_search_module,
            "_REPO_SEARCH_SHORTLIST_PER_DOC_RESULT",
            1,
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="needle topic",
            k=2,
        )

        assert result["data"]["hits"][0]["doc"] == "docs-page-5"
        ranker = result["data"]["ranker"]
        assert ranker["mode"] == "shortlist"
        assert ranker["scored_sections"] < ranker["compatible_sections"]

    async def test_search_repo_documents_gates_changelog_for_generic_queries(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "CHANGELOG.md").write_text(
            "\n".join(
                [
                    "# Changelog",
                    "",
                    "## 1.2.0",
                    "",
                    "Authentication authentication authentication release notes.",
                    "Authentication changes were mentioned in this version history.",
                ]
            ),
            encoding="utf-8",
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "authentication.md").write_text(
            "\n".join(
                [
                    "# Authentication",
                    "",
                    "Configure API keys and bearer token authentication.",
                ]
            ),
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        generic = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="authentication",
            k=3,
        )
        history = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="authentication release changes",
            k=3,
        )

        assert generic["data"]["hits"][0]["doc"] == "docs-authentication"
        assert history["data"]["hits"][0]["doc"] == "changelog"

    async def test_search_repo_documents_prefers_query_locale(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "docs" / "en").mkdir(parents=True)
        (tmp_path / "docs" / "de").mkdir(parents=True)
        body = "# Configuration\n\nConfigure runtime settings and application options."
        (tmp_path / "docs" / "en" / "configuration.md").write_text(
            body,
            encoding="utf-8",
        )
        (tmp_path / "docs" / "de" / "configuration.md").write_text(
            body,
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="configuration",
            k=2,
        )

        assert result["data"]["hits"][0]["doc"] == "docs-en-configuration"

    async def test_search_repo_documents_honors_configured_locale_preference(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# Root\n\nOverview.\n", encoding="utf-8")
        (tmp_path / "docs" / "en").mkdir(parents=True)
        (tmp_path / "docs" / "de").mkdir(parents=True)
        body = "# Configuration\n\nConfigure runtime settings and application options."
        (tmp_path / "docs" / "en" / "configuration.md").write_text(
            body,
            encoding="utf-8",
        )
        (tmp_path / "docs" / "de" / "configuration.md").write_text(
            body,
            encoding="utf-8",
        )
        write_default_config(tmp_path)
        cfg_path = tmp_path / ".cairn" / "config.toml"
        cfg_path.write_text(
            cfg_path.read_text(encoding="utf-8").replace(
                "preferred_locales = []",
                'preferred_locales = ["de"]',
            ),
            encoding="utf-8",
        )
        embedder = FakeEmbedder(dim=32)
        await sync_repo(
            tmp_path,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )

        result = await search_repo_documents(
            tmp_path,
            embedder=embedder,
            query="configuration",
            k=2,
        )

        assert result["data"]["hits"][0]["doc"] == "docs-de-configuration"
