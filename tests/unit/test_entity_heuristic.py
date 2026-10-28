"""Tests for cairn.entity.heuristic.HeuristicExtractor."""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cairn.entity.base import ExtractionHit
from cairn.entity.heuristic import HeuristicExtractor
from cairn.ingest.markdown import MarkdownParser


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


@pytest.fixture
def extractor() -> HeuristicExtractor:
    return HeuristicExtractor()


def _all_hits(hits: Iterable[ExtractionHit]) -> list[ExtractionHit]:
    return list(hits)


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
            "def fetch_user(): return None\n"
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
        # But real identifiers preserved (the underscore marks it as a symbol,
        # not a plain English word):
        assert "fetch_user" in names

    async def test_bare_lowercase_word_not_a_code_entity(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        # A lowercase token that reads as an ordinary English word (here `event`)
        # must NOT become a code entity, or it floods prose with false mentions.
        md = "# S\n\n```\nevent = 1\n```\n\nLater, an event occurs in prose.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        assert "event" not in {h.canonical for h in hits}

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


class TestHeadingDefined:
    async def test_glossary_heading_defines_a_term(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = (
            "# Glossary\n\n"
            "## Tenant\n\nAn isolated workspace. Every request names a Tenant.\n\n"
            "## Idempotency Key\n\nA client string. Pass an Idempotency Key once.\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        kinds = {(h.canonical, h.kind) for h in hits}
        assert ("Tenant", "defined") in kinds
        assert ("Idempotency Key", "defined") in kinds

    async def test_structural_headings_not_entities(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = (
            "# Overview\n\nProse.\n\n"
            "## Inputs\n\nMore prose.\n\n"
            "## Open Questions\n\nDeferred items.\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        names = {h.canonical for h in hits}
        assert "Overview" not in names
        assert "Inputs" not in names
        assert "Open Questions" not in names

    async def test_heading_term_found_across_sections(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        # "Tenant" is defined by a heading in one section and referenced in two
        # others — every body occurrence must be a mention.
        md = (
            "# Glossary\n\n## Tenant\n\nDefines the Tenant concept.\n\n"
            "# Billing\n\nBilling charges each Tenant monthly.\n\n"
            "# Ingestion\n\nIngestion rate-limits per Tenant.\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        tenant_sections = {
            h.section_id for h in hits if h.canonical == "Tenant"
        }
        assert tenant_sections == {"glossary/tenant", "billing", "ingestion"}


class TestProperNouns:
    async def test_multiword_proper_noun_in_prose(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        md = "# Doc\n\nThe Aurora Platform routes events through Auth Service.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        proper = {h.canonical for h in hits if h.kind == "proper"}
        assert "Aurora Platform" in proper
        assert "Auth Service" in proper

    async def test_leading_function_word_trimmed(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        # "The Aurora Platform" must register as "Aurora Platform", and a
        # capitalized sentence start with one real token is not a proper noun.
        md = "# Doc\n\nThe Aurora Platform ships. When Billing fails, retry.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        proper = {h.canonical for h in hits if h.kind == "proper"}
        assert "Aurora Platform" in proper
        assert "The Aurora Platform" not in proper
        assert "When Billing" not in proper


class TestMatchingPrecision:
    async def test_whole_word_only(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        # `Event` (code) must not match inside "Eventually".
        md = "# S\n\nUse `Event` now. Eventually it resolves.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        events = [h for h in hits if h.canonical == "Event"]
        assert len(events) == 1
        section = doc.sections[0]
        s = events[0].span
        assert section.raw_text[s.start : s.end] == "Event"

    async def test_case_sensitive_single_word_code(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        # The symbol `Event` should not match the common word "event".
        md = "# S\n\nUse `Event`. An event happened in the event loop.\n"
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        matched = [
            doc.sections[0].raw_text[h.span.start : h.span.end]
            for h in hits
            if h.canonical == "Event"
        ]
        assert matched == ["Event"]

    async def test_longest_match_wins(
        self, parser: MarkdownParser, extractor: HeuristicExtractor
    ) -> None:
        # With both "Auth" and "Auth Service" in the vocabulary, an occurrence
        # of "Auth Service" yields one proper hit, not a nested "Auth" hit.
        md = (
            "# Auth\n\n## Auth Service\n\n"
            "The Auth Service issues tokens for Auth Service callers.\n"
        )
        doc = parser.parse(md, doc_id="d")
        hits = _all_hits(await extractor.extract(doc))
        spans = [
            (h.span.start, h.span.end)
            for h in hits
            if h.canonical == "Auth Service"
        ]
        section = next(s for s in doc.sections if s.id == "auth/auth-service")
        for start, end in spans:
            assert section.raw_text[start:end].replace("\n", " ") == "Auth Service"
        # No hit should be a strict sub-span of an "Auth Service" hit.
        for h in hits:
            if h.canonical == "Auth Service":
                continue
            for start, end in spans:
                if h.section_id == section.id:
                    assert not (start <= h.span.start and h.span.end <= end)


class TestInvariants:
    @settings(max_examples=200)
    @given(
        body=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po"),
                max_codepoint=0x2FF,
            ),
            max_size=200,
        )
    )
    async def test_span_integrity_and_determinism(self, body: str) -> None:
        # Construct a document whose section body is arbitrary text; every hit's
        # span must slice back to exactly its surface form, and extraction must
        # be deterministic.
        parser = MarkdownParser()
        extractor = HeuristicExtractor()
        md = f"# Term One\n\n{body}\n"
        doc = parser.parse(md, doc_id="d")
        hits_a = _all_hits(await extractor.extract(doc))
        hits_b = _all_hits(await extractor.extract(doc))
        assert hits_a == hits_b  # deterministic
        by_section = {s.id: s.raw_text for s in doc.sections}
        for h in hits_a:
            assert h.canonical
            raw = by_section[h.section_id]
            assert 0 <= h.span.start <= h.span.end <= len(raw)
            assert raw[h.span.start : h.span.end] == h.surface_form
