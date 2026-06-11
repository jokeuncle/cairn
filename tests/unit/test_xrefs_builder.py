"""Tests for cairn.index.xrefs.XRefBuilder + XRefs reader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.index.xrefs import (
    XREFS_FILENAME,
    XREFS_FORMAT_VERSION,
    XRefBuilder,
    XRefs,
)
from cairn.ingest.markdown import MarkdownParser
from cairn.xref.fake import FakeXRefExtractor
from cairn.xref.heuristic import HeuristicXRefExtractor


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


class TestBuilder:
    async def test_writes_refs_json(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        doc = parser.parse("# A\n\nbody.\n\n# B\n\nbody.\n", doc_id="d")
        out = tmp_path / "doc"
        path = await XRefBuilder(FakeXRefExtractor()).build(doc, out_dir=out)
        assert path == out / XREFS_FILENAME
        assert path.exists()

    async def test_payload_format_version(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        doc = parser.parse("# A\n\nbody\n\n# B\n\nbody\n", doc_id="d")
        out = tmp_path / "doc"
        await XRefBuilder(FakeXRefExtractor()).build(doc, out_dir=out)
        payload = json.loads((out / XREFS_FILENAME).read_text())
        assert payload["format_version"] == XREFS_FORMAT_VERSION
        assert payload["extractor"] == "fake:linear"

    async def test_dedupe_keeps_highest_confidence(
        self, tmp_path: Path
    ) -> None:
        # Two extractor edges between the same pair + kind; keep higher conf.
        from cairn.core.types import Document, SectionNode, Span
        from cairn.xref.base import ExtractionEdge

        class DupExtractor:
            name = "dup"

            async def extract(self, document, *, entities=None):  # type: ignore[no-untyped-def]
                return [
                    ExtractionEdge(
                        src="a", dst="b", kind="link",
                        confidence=0.4, span=Span(start=0, end=1),
                    ),
                    ExtractionEdge(
                        src="a", dst="b", kind="link",
                        confidence=0.95, span=Span(start=10, end=11),
                    ),
                ]

        from datetime import UTC, datetime

        doc = Document(
            id="d",
            source_path=Path("/tmp/x.md"),
            source_hash="0" * 64,
            sections=(
                SectionNode(
                    id="a", title="A", level=1, parent=None, children=(),
                    span=Span(start=0, end=1), path=("A",), raw_text="",
                ),
                SectionNode(
                    id="b", title="B", level=1, parent=None, children=(),
                    span=Span(start=1, end=2), path=("B",), raw_text="",
                ),
            ),
            indexed_at=datetime.now(UTC),
            cairn_version="0.0.1",
        )
        out = tmp_path / "doc"
        await XRefBuilder(DupExtractor()).build(doc, out_dir=out)
        payload = json.loads((out / XREFS_FILENAME).read_text())
        assert len(payload["refs"]) == 1
        assert payload["refs"][0]["confidence"] == 0.95
        # And the span from the higher-confidence edge wins.
        assert payload["refs"][0]["span"]["start"] == 10

    async def test_self_loops_dropped(
        self, tmp_path: Path
    ) -> None:
        from datetime import UTC, datetime

        from cairn.core.types import Document, SectionNode, Span
        from cairn.xref.base import ExtractionEdge

        class SelfLooper:
            name = "selflooper"

            async def extract(self, document, *, entities=None):  # type: ignore[no-untyped-def]
                return [
                    ExtractionEdge(
                        src="a", dst="a", kind="link",
                        confidence=1.0, span=Span(start=0, end=1),
                    ),
                ]

        doc = Document(
            id="d",
            source_path=Path("/tmp/x.md"),
            source_hash="0" * 64,
            sections=(
                SectionNode(
                    id="a", title="A", level=1, parent=None, children=(),
                    span=Span(start=0, end=1), path=("A",), raw_text="",
                ),
            ),
            indexed_at=datetime.now(UTC),
            cairn_version="0.0.1",
        )
        out = tmp_path / "doc"
        await XRefBuilder(SelfLooper()).build(doc, out_dir=out)
        payload = json.loads((out / XREFS_FILENAME).read_text())
        assert payload["refs"] == []

    async def test_empty_endpoint_rejected(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from cairn.core.types import Document, SectionNode, Span
        from cairn.xref.base import ExtractionEdge

        class Broken:
            name = "broken"

            async def extract(self, document, *, entities=None):  # type: ignore[no-untyped-def]
                return [
                    ExtractionEdge(
                        src="", dst="b", kind="link",
                        confidence=1.0, span=Span(start=0, end=1),
                    ),
                ]

        doc = Document(
            id="d",
            source_path=Path("/tmp/x.md"),
            source_hash="0" * 64,
            sections=(
                SectionNode(
                    id="b", title="B", level=1, parent=None, children=(),
                    span=Span(start=0, end=1), path=("B",), raw_text="",
                ),
            ),
            indexed_at=datetime.now(UTC),
            cairn_version="0.0.1",
        )
        with pytest.raises(IndexBuildError):
            await XRefBuilder(Broken()).build(doc, out_dir=tmp_path)


class TestReader:
    async def _built(self, tmp_path: Path, parser: MarkdownParser) -> XRefs:
        md = (
            "# A\n\nSee [B](#b) and Section 3.\n\n"
            "# B\n\nstuff.\n\n"
            "# 3 Other\n\nthird.\n"
        )
        doc = parser.parse(md, doc_id="d")
        out = tmp_path / "doc"
        await XRefBuilder(HeuristicXRefExtractor()).build(doc, out_dir=out)
        return XRefs.load(out)

    async def test_round_trip(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        x = await self._built(tmp_path, parser)
        assert x.doc_id == "d"
        assert x.extractor == "heuristic:xref-v1"
        assert len(x) > 0

    async def test_load_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(IndexNotFoundError):
            XRefs.load(tmp_path / "ghost")

    async def test_outgoing_from(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        x = await self._built(tmp_path, parser)
        out = x.outgoing_from("a")
        # A has outgoing to B (link) and to the numeric "3" section (textual).
        dsts = {e.dst for e in out}
        assert "b" in dsts

    async def test_outgoing_sorted_by_confidence(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        x = await self._built(tmp_path, parser)
        out = x.outgoing_from("a")
        confs = [e.confidence for e in out]
        assert confs == sorted(confs, reverse=True)

    async def test_outgoing_with_kinds_filter(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        x = await self._built(tmp_path, parser)
        link_only = x.outgoing_from("a", kinds=("link",))
        assert all(e.kind == "link" for e in link_only)

    async def test_incoming_to(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        x = await self._built(tmp_path, parser)
        incoming = x.incoming_to("b")
        assert any(e.src == "a" for e in incoming)

    async def test_by_kind(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        x = await self._built(tmp_path, parser)
        links = x.by_kind("link")
        textuals = x.by_kind("textual")
        assert len(links) >= 1
        assert len(textuals) >= 1
