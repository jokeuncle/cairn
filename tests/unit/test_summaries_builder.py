"""Tests for cairn.index.summaries.SummaryBuilder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, Final

import pytest

from cairn.core.errors import IndexBuildError
from cairn.core.types import Document
from cairn.index.summaries import (
    SUMMARIES_FILENAME,
    SUMMARIES_FORMAT_VERSION,
    Summaries,
    SummaryBuilder,
    section_hash,
)
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.base import SummaryLevel
from cairn.summarize.cache import SummaryCache
from cairn.summarize.fake import FakeSummarizer


@pytest.fixture
def parsed_simple(simple_md: str) -> Document:
    return MarkdownParser().parse(simple_md, doc_id="simple")


# -- A counting wrapper around FakeSummarizer for cache verification --------


class CountingSummarizer:
    """Wraps a FakeSummarizer and counts invocations for test assertions."""

    name: Final = "fake:counted"

    _inner: ClassVar[FakeSummarizer]

    def __init__(self) -> None:
        self._inner = FakeSummarizer()
        self.calls = 0

    async def summarize(
        self,
        *,
        title: str,
        body: str,
        level: SummaryLevel,
    ) -> str:
        self.calls += 1
        return await self._inner.summarize(title=title, body=body, level=level)


# -- Build ------------------------------------------------------------------


class TestSummaryBuilder:
    async def test_writes_summaries_json(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        path = await SummaryBuilder(FakeSummarizer()).build(parsed_simple, out_dir=out)
        assert path == out / SUMMARIES_FILENAME
        assert path.exists()

    async def test_payload_carries_format_version(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await SummaryBuilder(FakeSummarizer()).build(parsed_simple, out_dir=out)
        payload = json.loads((out / SUMMARIES_FILENAME).read_text())
        assert payload["format_version"] == SUMMARIES_FORMAT_VERSION

    async def test_one_record_per_section(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await SummaryBuilder(FakeSummarizer()).build(parsed_simple, out_dir=out)
        payload = json.loads((out / SUMMARIES_FILENAME).read_text())
        ids_in = [s.id for s in parsed_simple.sections]
        ids_out = [r["section_id"] for r in payload["summaries"]]
        assert ids_out == ids_in

    async def test_digest_is_none_when_not_requested(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await SummaryBuilder(FakeSummarizer()).build(
            parsed_simple,
            out_dir=out,
            levels=(SummaryLevel.GIST, SummaryLevel.SYNOPSIS),
        )
        payload = json.loads((out / SUMMARIES_FILENAME).read_text())
        assert all(r["digest"] is None for r in payload["summaries"])

    async def test_digest_populated_when_requested(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await SummaryBuilder(FakeSummarizer()).build(
            parsed_simple,
            out_dir=out,
            levels=(SummaryLevel.GIST, SummaryLevel.SYNOPSIS, SummaryLevel.DIGEST),
        )
        payload = json.loads((out / SUMMARIES_FILENAME).read_text())
        assert all(r["digest"] is not None for r in payload["summaries"])

    async def test_section_hash_recorded(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await SummaryBuilder(FakeSummarizer()).build(parsed_simple, out_dir=out)
        payload = json.loads((out / SUMMARIES_FILENAME).read_text())
        for record, section in zip(
            payload["summaries"], parsed_simple.sections, strict=True
        ):
            assert record["section_hash"] == section_hash(section)

    async def test_levels_deduplicated_preserving_order(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        await SummaryBuilder(FakeSummarizer()).build(
            parsed_simple,
            out_dir=out,
            levels=(SummaryLevel.SYNOPSIS, SummaryLevel.GIST, SummaryLevel.SYNOPSIS),
        )
        payload = json.loads((out / SUMMARIES_FILENAME).read_text())
        assert payload["levels"] == ["synopsis", "gist"]

    async def test_empty_levels_rejected(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        with pytest.raises(IndexBuildError):
            await SummaryBuilder(FakeSummarizer()).build(
                parsed_simple, out_dir=tmp_path, levels=()
            )

    def test_concurrency_zero_rejected(self) -> None:
        with pytest.raises(IndexBuildError):
            SummaryBuilder(FakeSummarizer(), concurrency=0)


# -- Cache integration ------------------------------------------------------


class TestSummaryBuilderCache:
    async def test_cache_persists_results_across_runs(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        cache = SummaryCache(tmp_path / "cache")
        counter = CountingSummarizer()
        out_a = tmp_path / "a"
        out_b = tmp_path / "b"

        await SummaryBuilder(counter, cache=cache).build(parsed_simple, out_dir=out_a)
        first_calls = counter.calls

        # Second build with same input + cache should be all cache hits.
        await SummaryBuilder(counter, cache=cache).build(parsed_simple, out_dir=out_b)
        assert counter.calls == first_calls  # zero additional calls

    async def test_cache_invalidates_when_section_changes(
        self, tmp_path: Path
    ) -> None:
        # Two docs that differ ONLY in the Introduction's body. Sibling
        # sections must be byte-identical so their raw_text (and thus
        # section_hash) is unchanged.
        original_md = (
            "# Introduction\n\n"
            "Original intro body.\n\n"
            "## Quickstart\n\n"
            "Quickstart body unchanged.\n\n"
            "## Configuration\n\n"
            "Config body unchanged.\n"
        )
        modified_md = (
            "# Introduction\n\n"
            "NEW intro body.\n\n"
            "## Quickstart\n\n"
            "Quickstart body unchanged.\n\n"
            "## Configuration\n\n"
            "Config body unchanged.\n"
        )
        parser = MarkdownParser()
        original = parser.parse(original_md, doc_id="d")
        modified = parser.parse(modified_md, doc_id="d")

        cache = SummaryCache(tmp_path / "cache")
        counter = CountingSummarizer()
        await SummaryBuilder(counter, cache=cache).build(
            original, out_dir=tmp_path / "out"
        )
        first_calls = counter.calls
        # 3 sections x 3 levels (default since v0.2.4 includes digest).
        assert first_calls == 3 * 3

        await SummaryBuilder(counter, cache=cache).build(
            modified, out_dir=tmp_path / "out2"
        )
        # Only Introduction's section_hash differs → 3 new calls (one per level).
        assert counter.calls == first_calls + 3

    async def test_no_cache_means_every_section_is_called(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        counter = CountingSummarizer()
        await SummaryBuilder(counter).build(
            parsed_simple,
            out_dir=tmp_path / "out",
            levels=(SummaryLevel.GIST, SummaryLevel.SYNOPSIS),
        )
        # 5 sections x 2 levels = 10 calls.
        assert counter.calls == len(parsed_simple.sections) * 2


# -- Determinism (modulo timestamps) ---------------------------------------


class TestDeterminism:
    async def test_two_builds_produce_same_summary_content(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"

        await SummaryBuilder(FakeSummarizer()).build(parsed_simple, out_dir=a_dir)
        await SummaryBuilder(FakeSummarizer()).build(parsed_simple, out_dir=b_dir)

        a_summaries = Summaries.load(a_dir)
        b_summaries = Summaries.load(b_dir)

        assert len(a_summaries) == len(b_summaries)
        for a, b in zip(a_summaries, b_summaries, strict=True):
            assert a.section_id == b.section_id
            assert a.gist == b.gist
            assert a.synopsis == b.synopsis
            assert a.section_hash == b.section_hash
