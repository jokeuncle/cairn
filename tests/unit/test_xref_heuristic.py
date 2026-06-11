"""Tests for cairn.xref.heuristic.HeuristicXRefExtractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.entity.heuristic import HeuristicExtractor
from cairn.index.entities import Entities, EntityBuilder
from cairn.ingest.markdown import MarkdownParser
from cairn.xref.heuristic import HeuristicXRefExtractor


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


@pytest.fixture
def xrefext() -> HeuristicXRefExtractor:
    return HeuristicXRefExtractor()


def _all(edges: object) -> list:
    return list(edges)  # type: ignore[arg-type]


# -- Anchor-link extraction -------------------------------------------------


class TestLinkExtraction:
    async def test_anchor_link_resolved(
        self, parser: MarkdownParser, xrefext: HeuristicXRefExtractor
    ) -> None:
        md = (
            "# Intro\n\nSee [the API](#api) for details.\n\n"
            "# API\n\nThe API.\n"
        )
        doc = parser.parse(md, doc_id="d")
        edges = _all(await xrefext.extract(doc))
        links = [e for e in edges if e.kind == "link"]
        assert len(links) == 1
        assert links[0].src == "intro"
        assert links[0].dst == "api"
        assert links[0].confidence == 0.95

    async def test_unknown_anchor_skipped(
        self, parser: MarkdownParser, xrefext: HeuristicXRefExtractor
    ) -> None:
        md = "# Intro\n\nSee [missing](#nope).\n"
        doc = parser.parse(md, doc_id="d")
        edges = _all(await xrefext.extract(doc))
        assert [e for e in edges if e.kind == "link"] == []

    async def test_ambiguous_anchor_lower_confidence(
        self, parser: MarkdownParser, xrefext: HeuristicXRefExtractor
    ) -> None:
        # Two H1 headings produce the same final slug → ambiguous anchor.
        md = (
            "# Setup\n\nFirst Setup body.\n\n## Detail\n\nstuff.\n\n"
            "# Other\n\n## Setup\n\nLink [here](#setup).\n"
        )
        doc = parser.parse(md, doc_id="d")
        edges = _all(await xrefext.extract(doc))
        links = [e for e in edges if e.kind == "link"]
        assert links  # at least one
        assert all(e.confidence == 0.75 for e in links)


# -- Textual reference extraction -------------------------------------------


class TestTextualExtraction:
    async def test_section_number_resolved(
        self, parser: MarkdownParser, xrefext: HeuristicXRefExtractor
    ) -> None:
        md = (
            "# 1. Overview\n\nSee Section 2.1 for details.\n\n"
            "# 2. Details\n\n## 2.1 Subdetail\n\nThe sub.\n"
        )
        doc = parser.parse(md, doc_id="d")
        edges = _all(await xrefext.extract(doc))
        textual = [e for e in edges if e.kind == "textual"]
        assert any(e.src == "1-overview" and "2-details" in e.dst for e in textual)

    async def test_section_symbol(
        self, parser: MarkdownParser, xrefext: HeuristicXRefExtractor
    ) -> None:
        md = (
            "# 1. Overview\n\nSee § 2 for the next.\n\n"
            "# 2. Next\n\nStuff.\n"
        )
        doc = parser.parse(md, doc_id="d")
        edges = _all(await xrefext.extract(doc))
        textual = [e for e in edges if e.kind == "textual"]
        assert any(e.src == "1-overview" and e.dst == "2-next" for e in textual)

    async def test_unknown_number_skipped(
        self, parser: MarkdownParser, xrefext: HeuristicXRefExtractor
    ) -> None:
        md = "# 1. Solo\n\nSee Section 99 (does not exist).\n"
        doc = parser.parse(md, doc_id="d")
        edges = _all(await xrefext.extract(doc))
        textual = [e for e in edges if e.kind == "textual"]
        assert textual == []


# -- Entity-mediated extraction --------------------------------------------


class TestEntityMediated:
    async def test_shared_defined_entity_creates_edge(
        self,
        tmp_path: Path,
        parser: MarkdownParser,
        xrefext: HeuristicXRefExtractor,
    ) -> None:
        md = (
            "# Alpha\n\nThe **Widget** does X.\n\n"
            "# Beta\n\nThe **Widget** does Y too.\n\n"
            "# Gamma\n\nUnrelated body.\n"
        )
        doc = parser.parse(md, doc_id="d")
        await EntityBuilder(HeuristicExtractor()).build(doc, out_dir=tmp_path)
        entities = Entities.load(tmp_path)

        edges = _all(await xrefext.extract(doc, entities=entities))
        ent_edges = [e for e in edges if e.kind == "entity"]
        # Bidirectional: alpha↔beta, not connecting gamma.
        pairs = {(e.src, e.dst) for e in ent_edges}
        assert ("alpha", "beta") in pairs
        assert ("beta", "alpha") in pairs
        for src, dst in pairs:
            assert {src, dst} != {"gamma"}
        # All confidences in expected band: 1 shared → 0.5.
        assert all(0.5 <= e.confidence <= 0.8 for e in ent_edges)

    async def test_no_entities_means_no_entity_edges(
        self, parser: MarkdownParser, xrefext: HeuristicXRefExtractor
    ) -> None:
        md = "# A\n\nbody\n\n# B\n\nbody\n"
        doc = parser.parse(md, doc_id="d")
        edges = _all(await xrefext.extract(doc))
        assert [e for e in edges if e.kind == "entity"] == []


# -- Self-loop filtering ----------------------------------------------------


class TestSelfLoops:
    async def test_no_self_loops_from_anchor(
        self, parser: MarkdownParser, xrefext: HeuristicXRefExtractor
    ) -> None:
        md = "# Foo\n\nSee [self](#foo) for self-reference.\n"
        doc = parser.parse(md, doc_id="d")
        edges = _all(await xrefext.extract(doc))
        assert all(e.src != e.dst for e in edges)
