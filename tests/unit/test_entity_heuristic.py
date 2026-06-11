"""Tests for cairn.entity.heuristic.HeuristicExtractor."""

from __future__ import annotations

import pytest

from cairn.entity.heuristic import HeuristicExtractor
from cairn.ingest.markdown import MarkdownParser


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


@pytest.fixture
def extractor() -> HeuristicExtractor:
    return HeuristicExtractor()


def _all_hits(hits: object) -> list:
    return list(hits)  # type: ignore[arg-type]


class TestCodeExtraction:
    async def test_identifiers_in_fenced_block(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = (
            "# Section\n\n"
            "Body text.\n\n"
            "```python\n"
            "class Document:\n"
            "    sections: list[SectionNode]\n"
            "```\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        names = {h.canonical for h in hits}
        assert "Document" in names
        assert "SectionNode" in names

    async def test_python_keywords_filtered(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = (
            "# Section\n\n"
            "```python\n"
            "import os\n"
            "from x import Y\n"
            "def foo(): return None\n"
            "```\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        names = {h.canonical for h in hits}
        # Keywords gone:
        assert "import" not in names
        assert "from" not in names
        assert "def" not in names
        assert "return" not in names
        assert "None" not in names
        # But real identifiers preserved:
        assert "foo" in names

    async def test_inline_code_extracted(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = "# Section\n\nWe expose `MarkdownParser` for ingestion.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        names = {h.canonical for h in hits}
        assert "MarkdownParser" in names

    async def test_inline_inside_fence_not_double_scanned(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        # An identifier inside a fenced block must be extracted exactly once
        # per occurrence, even when it's wrapped in backticks (which would
        # normally trigger the inline-code path).
        md = (
            "# Section\n\n"
            "Outside: `Apple`.\n\n"  # 1 inline hit
            "```\n"
            "# `Apple` inside fence\n"  # 1 fence-body hit; inline skipped
            "```\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        apples = [h for h in hits if h.canonical == "Apple"]
        # Two distinct occurrences: one outside (inline), one inside (fence).
        # If the inline regex weren't suppressed inside fences, we'd see 3.
        assert len(apples) == 2
        spans = {(h.span.start, h.span.end) for h in apples}
        assert len(spans) == 2

    async def test_short_identifiers_skipped(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = "# S\n\n```\na = 1\nbb = 2\n```\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        names = {h.canonical for h in hits}
        assert "a" not in names
        assert "bb" not in names


class TestDefinedExtraction:
    async def test_bold_terms_extracted(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = (
            "# Section\n\n"
            "A **Cairn** marks a trail. The **BookIndex** is its core.\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        names = {(h.canonical, h.kind) for h in hits}
        assert ("Cairn", "defined") in names
        assert ("BookIndex", "defined") in names

    async def test_bold_with_sentence_punctuation_skipped(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = "# S\n\n**This is, in fact, prose.** Just narrative.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        defined = [h for h in hits if h.kind == "defined"]
        assert defined == []

    async def test_long_bold_skipped(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = f"# S\n\n**{'verylongterm' * 10}** in bold.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        defined = [h for h in hits if h.kind == "defined"]
        assert defined == []


class TestSpanAndSection:
    async def test_section_id_attached(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = (
            "# Intro\n\nBody.\n\n## Sub\n\nUses `Tree` here.\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        tree_hits = [h for h in hits if h.canonical == "Tree"]
        assert len(tree_hits) == 1
        assert tree_hits[0].section_id == "intro/sub"

    async def test_span_within_raw_text_bounds(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = "# S\n\nWe use `Widget` here.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        widget = next(h for h in hits if h.canonical == "Widget")
        section = doc.sections[0]
        assert widget.span.start >= 0
        assert widget.span.end <= len(section.raw_text)
        # And the span actually points at the identifier.
        assert section.raw_text[widget.span.start : widget.span.end] == "Widget"
