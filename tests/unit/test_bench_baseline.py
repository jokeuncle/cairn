"""Tests for cairn.bench.baseline (chunker, section assignment, NaiveRAG)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.bench.baseline import (
    NaiveRAG,
    assign_section,
    chunk_text,
)
from cairn.core.types import SectionNode, Span
from cairn.embed.fake import FakeEmbedder
from cairn.ingest.markdown import MarkdownParser


class TestChunker:
    def test_empty_text(self) -> None:
        assert chunk_text("", chunk_size_words=10) == []

    def test_single_chunk(self) -> None:
        chunks = chunk_text("one two three", chunk_size_words=10)
        assert len(chunks) == 1
        start, end, text = chunks[0]
        assert text == "one two three"
        assert start == 0
        assert end == len("one two three")

    def test_multiple_chunks(self) -> None:
        text = " ".join(f"w{i}" for i in range(25))
        chunks = chunk_text(text, chunk_size_words=10)
        assert len(chunks) == 3  # 10 + 10 + 5
        # Last chunk ends at the source end
        assert chunks[-1][1] == len(text)

    def test_invalid_chunk_size_rejected(self) -> None:
        with pytest.raises(ValueError):
            chunk_text("any", chunk_size_words=0)


class TestAssignSection:
    def _node(self, sid: str, start: int, end: int, level: int = 1) -> SectionNode:
        return SectionNode(
            id=sid,
            title=sid,
            level=level,
            parent=None,
            children=(),
            span=Span(start=start, end=end),
            path=(sid,),
            raw_text="",
        )

    def test_midpoint_inside_single_section(self) -> None:
        sections = [self._node("a", 0, 100)]
        sid = assign_section(20, 40, sections)
        assert sid == "a"

    def test_midpoint_outside_all_sections(self) -> None:
        sections = [self._node("a", 0, 10)]
        sid = assign_section(50, 60, sections)
        assert sid is None

    def test_deepest_section_wins(self) -> None:
        sections = [
            self._node("parent", 0, 100, level=1),
            self._node("child", 30, 60, level=2),
        ]
        sid = assign_section(40, 50, sections)
        assert sid == "child"


class TestNaiveRAGRoundTrip:
    async def test_index_then_retrieve(self, tmp_path: Path) -> None:
        md = (
            "# Intro\n\nIntro body talks about apples and bananas.\n\n"
            "# Other\n\nOther body discusses oranges and grapes.\n"
        )
        doc = MarkdownParser().parse(md, doc_id="d")
        embedder = FakeEmbedder(dim=32)
        rag = NaiveRAG(embedder, chunk_size_words=4)
        await rag.index(doc, md, out_dir=tmp_path)

        hits = await rag.retrieve("apples bananas", out_dir=tmp_path, k=3)
        assert len(hits) > 0
        # The chunks containing apples/bananas should rank in the top results.
        assert any("apples" in h.text or "bananas" in h.text for h in hits)

    async def test_empty_document(self, tmp_path: Path) -> None:
        md = "# Empty\n\n\n"
        doc = MarkdownParser().parse(md, doc_id="d")
        rag = NaiveRAG(FakeEmbedder(dim=16), chunk_size_words=4)
        # Should not raise even when there's effectively no body content.
        await rag.index(doc, md, out_dir=tmp_path)

    async def test_invalid_batch_size_rejected(self) -> None:
        with pytest.raises(ValueError):
            NaiveRAG(FakeEmbedder(dim=8), batch_size=0)
