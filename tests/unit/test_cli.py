"""Tests for the typer CLI surface (cairn.cli.app)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from typer import Typer
from typer.testing import CliRunner

from cairn import __version__
from cairn.cli.app import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def indexed_dir(tmp_path: Path, fixture_dir: Path, runner: CliRunner) -> Path:
    out = tmp_path / "doc"
    result = runner.invoke(
        app,
        [
            "index",
            str(fixture_dir / "simple.md"),
            "--out",
            str(out),
            "--fake",
        ],
    )
    assert result.exit_code == 0, result.output
    return out


class TestVersion:
    def test_package_level_app_import_is_typer_app(self) -> None:
        from cairn.cli import app as package_app

        assert isinstance(package_app, Typer)

    def test_prints_version(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestIndex:
    def test_index_writes_manifest(
        self, indexed_dir: Path
    ) -> None:
        assert (indexed_dir / "manifest.json").exists()
        assert (indexed_dir / "tree.json").exists()
        assert (indexed_dir / "summaries.json").exists()
        assert (indexed_dir / "vectors_manifest.json").exists()

    def test_index_reports_output_path(
        self, tmp_path: Path, fixture_dir: Path, runner: CliRunner
    ) -> None:
        out = tmp_path / "report"
        result = runner.invoke(
            app,
            [
                "index",
                str(fixture_dir / "simple.md"),
                "--out",
                str(out),
                "--fake",
            ],
        )
        assert result.exit_code == 0
        assert "indexed:" in result.output

    def test_second_index_reports_no_op(
        self, tmp_path: Path, fixture_dir: Path, runner: CliRunner
    ) -> None:
        out = tmp_path / "noop"
        args = ["index", str(fixture_dir / "simple.md"), "--out", str(out), "--fake"]
        first = runner.invoke(app, args)
        assert first.exit_code == 0
        assert "indexed:" in first.output
        second = runner.invoke(app, args)
        assert second.exit_code == 0
        assert "already up to date" in second.output

    def test_force_overrides_noop(
        self, tmp_path: Path, fixture_dir: Path, runner: CliRunner
    ) -> None:
        out = tmp_path / "forced"
        args = ["index", str(fixture_dir / "simple.md"), "--out", str(out), "--fake"]
        runner.invoke(app, args)
        result = runner.invoke(app, [*args, "--force"])
        assert result.exit_code == 0
        assert "indexed:" in result.output

    def test_missing_source_file_fails(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["index", "/no/such/file.md", "--fake"])
        assert result.exit_code != 0


class TestOutline:
    def test_outline_prints_json(
        self, indexed_dir: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["outline", str(indexed_dir)])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["doc"] == "simple"
        assert "tree" in payload

    def test_outline_respects_focus(
        self, indexed_dir: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            ["outline", str(indexed_dir), "--focus", "introduction"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["tree"][0]["id"] == "introduction"


class TestQuery:
    def test_semantic_query_runs_with_fake(
        self, indexed_dir: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            [
                "query",
                "semantic",
                str(indexed_dir),
                "intro body lines",
                "--fake",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "hits" in payload

    def test_keyword_query(
        self, indexed_dir: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            ["query", "keyword", str(indexed_dir), "pip"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        ids = [h["id"] for h in payload["hits"]]
        assert "introduction/quickstart" in ids

    def test_keyword_invalid_mode_rejected(
        self, indexed_dir: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            [
                "query",
                "keyword",
                str(indexed_dir),
                "pip",
                "--mode",
                "bogus",
            ],
        )
        assert result.exit_code != 0


class TestInspect:
    def test_inspect_writes_html(
        self, indexed_dir: Path, tmp_path: Path, runner: CliRunner
    ) -> None:
        out = tmp_path / "inspect.html"
        result = runner.invoke(app, ["inspect", str(indexed_dir), "--out", str(out)])
        assert result.exit_code == 0, result.output
        assert "inspector:" in result.output
        text = out.read_text(encoding="utf-8")
        assert "Cairn Inspector" in text
        assert "simple" in text


class TestRepoCommands:
    def test_init_can_enable_markitdown(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, runner: CliRunner
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init", "-y", "--markitdown"])

        assert result.exit_code == 0, result.output
        config = (tmp_path / ".cairn" / "config.toml").read_text(encoding="utf-8")
        assert "enable_markitdown = true" in config
        assert '"docs/**/*.html"' in config

    def test_init_sync_status_and_repo_inspect(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, runner: CliRunner
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "README.md").write_text(
            "# Readme\n\nProject overview.\n", encoding="utf-8"
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "# Guide\n\nDetailed docs.\n", encoding="utf-8"
        )

        init_result = runner.invoke(app, ["init", "-y"])
        assert init_result.exit_code == 0, init_result.output
        assert (tmp_path / ".cairn" / "config.toml").exists()

        sync_result = runner.invoke(app, ["sync", "--fake"])
        assert sync_result.exit_code == 0, sync_result.output
        assert "synced: 2/2 documents" in sync_result.output
        assert (
            tmp_path / ".cairn" / "documents" / "readme" / "manifest.json"
        ).exists()

        status_result = runner.invoke(app, ["status"])
        assert status_result.exit_code == 0, status_result.output
        assert "`readme`" in status_result.output
        assert "`docs-guide`" in status_result.output

        doctor_result = runner.invoke(app, ["doctor"])
        assert doctor_result.exit_code == 0, doctor_result.output
        assert "Cairn doctor: ok" in doctor_result.output

        mcp_result = runner.invoke(app, ["mcp", "config", "--client", "claude"])
        assert mcp_result.exit_code == 0, mcp_result.output
        mcp_payload = json.loads(mcp_result.output)
        assert mcp_payload["mcpServers"]["cairn"]["args"][:2] == [
            "serve",
            "--repo",
        ]
        assert str(tmp_path) in mcp_payload["mcpServers"]["cairn"]["args"]

        codex_result = runner.invoke(app, ["mcp", "config", "--client", "codex"])
        assert codex_result.exit_code == 0, codex_result.output
        assert "[mcp_servers.cairn]" in codex_result.output
        assert "--repo" in codex_result.output

        inspect_result = runner.invoke(
            app, ["inspect", "--out", "repo-inspector.html"]
        )
        assert inspect_result.exit_code == 0, inspect_result.output
        assert (tmp_path / "repo-inspector.html").exists()

    def test_doctor_reports_missing_repo_config(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, runner: CliRunner
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 1
        assert "cairn init -y" in result.output
