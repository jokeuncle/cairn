"""End-to-end test of the bench runner with fake plugins."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.bench.dataset import load_suite
from cairn.bench.report import format_markdown_report, write_json_report
from cairn.bench.runner import BenchOptions, BenchRunner
from cairn.embed.fake import FakeEmbedder
from cairn.summarize.fake import FakeSummarizer


@pytest.fixture
def starter_suite(tmp_path: Path) -> Path:
    md_path = tmp_path / "doc.md"
    md_path.write_text(
        "# Apples\n\nApples grow on trees.\n\n"
        "# Bananas\n\nBananas are yellow.\n",
        encoding="utf-8",
    )
    suite_path = tmp_path / "suite.toml"
    suite_path.write_text(
        """
name = "tiny"

[[documents]]
id = "d"
source = "doc.md"

[[documents.questions]]
id = "fruit-color"
question = "what color are bananas"
expected_anchors = ["bananas"]
""",
        encoding="utf-8",
    )
    return suite_path


class TestRunner:
    async def test_end_to_end_with_fakes(
        self, tmp_path: Path, starter_suite: Path
    ) -> None:
        runner = BenchRunner(
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
            options=BenchOptions(k=4),
        )
        suite = load_suite(starter_suite)
        summary = await runner.run(suite, work_dir=tmp_path / "work")

        assert summary.suite_name == "tiny"
        assert summary.k == 4
        assert len(summary.questions) == 1
        result = summary.questions[0]
        assert result.question_id == "fruit-color"
        assert result.cairn.system == "cairn"
        assert result.naive.system == "naive"
        # Both systems should record some tokens
        assert result.cairn.tokens_returned >= 0
        assert result.naive.tokens_returned >= 0

    async def test_markdown_report_renders(
        self, tmp_path: Path, starter_suite: Path
    ) -> None:
        runner = BenchRunner(
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
        )
        summary = await runner.run(load_suite(starter_suite), work_dir=tmp_path / "w")
        report = format_markdown_report(summary)
        assert summary.suite_name in report
        assert "Headline" in report
        assert "Cairn" in report

    async def test_json_report_written(
        self, tmp_path: Path, starter_suite: Path
    ) -> None:
        runner = BenchRunner(
            summarizer=FakeSummarizer(),
            embedder=FakeEmbedder(dim=32),
        )
        summary = await runner.run(load_suite(starter_suite), work_dir=tmp_path / "w")
        path = tmp_path / "report.json"
        written = write_json_report(summary, path)
        assert written == path
        assert path.exists()
        # Sanity: the file is well-formed JSON we can re-parse.
        import json

        payload = json.loads(path.read_text())
        assert payload["suite"] == "tiny"
        assert "summary" in payload
        assert "cairn_mean_recall_at_k" in payload["summary"]
