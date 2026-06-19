"""Tests for repository-level Cairn documentation workflow."""

from __future__ import annotations

from pathlib import Path

from cairn.cli.config import IndexConfig
from cairn.embed.fake import FakeEmbedder
from cairn.repo import (
    DEFAULT_EXCLUDE,
    RepoConfig,
    discover_documents,
    load_repo_config,
    load_repo_document_index,
    repo_status,
    search_repo_documents,
    sync_repo,
    write_default_config,
)
from cairn.summarize.fake import FakeSummarizer


def _write_repo_docs(root: Path) -> None:
    (root / "README.md").write_text("# Readme\n\nProject overview.\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text(
        "# Guide\n\nDetailed docs.\n", encoding="utf-8"
    )


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
