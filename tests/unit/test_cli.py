"""Tests for the typer CLI surface (cairn.cli.app)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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
