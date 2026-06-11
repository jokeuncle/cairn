"""Tests for cairn.index.summaries.Summaries (read-side)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairn.core.errors import IndexNotFoundError
from cairn.core.types import Document
from cairn.index.summaries import SUMMARIES_FILENAME, Summaries, SummaryBuilder
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.fake import FakeSummarizer


@pytest.fixture
def parsed_simple(simple_md: str) -> Document:
    return MarkdownParser().parse(simple_md, doc_id="simple")


@pytest.fixture
async def built_dir(tmp_path: Path, parsed_simple: Document) -> Path:
    out = tmp_path / "simple"
    await SummaryBuilder(FakeSummarizer()).build(parsed_simple, out_dir=out)
    return out


class TestLoad:
    async def test_round_trip_preserves_records(
        self, built_dir: Path, parsed_simple: Document
    ) -> None:
        summaries = Summaries.load(built_dir)
        assert len(summaries) == len(parsed_simple.sections)
        for section in parsed_simple.sections:
            s = summaries.require(section.id)
            assert s.section_id == section.id
            assert s.model == "fake:words"
            assert s.gist  # non-empty
            assert s.synopsis  # non-empty
            # Since v0.2.4 the default includes digest.
            assert s.digest

    async def test_load_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(IndexNotFoundError):
            Summaries.load(tmp_path / "missing")

    async def test_unsupported_version_raises(self, tmp_path: Path) -> None:
        path = tmp_path / SUMMARIES_FILENAME
        path.write_text(
            json.dumps(
                {
                    "format_version": 99999,
                    "doc_id": "x",
                    "model": "m",
                    "summaries": [],
                }
            )
        )
        with pytest.raises(IndexNotFoundError):
            Summaries.load(tmp_path)


class TestQueries:
    async def test_get_returns_none_for_missing(self, built_dir: Path) -> None:
        summaries = Summaries.load(built_dir)
        assert summaries.get("nope") is None

    async def test_require_raises_for_missing(self, built_dir: Path) -> None:
        summaries = Summaries.load(built_dir)
        with pytest.raises(IndexNotFoundError):
            summaries.require("nope")

    async def test_contains(self, built_dir: Path) -> None:
        summaries = Summaries.load(built_dir)
        assert "introduction" in summaries
        assert "nope" not in summaries

    async def test_iter_yields_all(
        self, built_dir: Path, parsed_simple: Document
    ) -> None:
        summaries = Summaries.load(built_dir)
        ids = [s.section_id for s in summaries]
        assert ids == [s.id for s in parsed_simple.sections]

    async def test_doc_id_and_model_exposed(self, built_dir: Path) -> None:
        summaries = Summaries.load(built_dir)
        assert summaries.doc_id == "simple"
        assert summaries.model == "fake:words"
