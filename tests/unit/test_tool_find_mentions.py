"""Tests for cairn.tools.find_mentions."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.embed.fake import FakeEmbedder
from cairn.entity.heuristic import HeuristicExtractor
from cairn.index.entities import EntityBuilder
from cairn.index.summaries import SummaryBuilder
from cairn.index.tree import TreeBuilder
from cairn.index.vectors import VectorBuilder
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.fake import FakeSummarizer
from cairn.tools.base import DocumentIndex
from cairn.tools.find_mentions import find_mentions


@pytest.fixture
async def index_with_entities(tmp_path: Path) -> DocumentIndex:
    md = (
        "# Intro\n\nUses `Widget` and **Concept**.\n\n"
        "## Sub\n\nMore on `Widget`.\n\n"
        "# Other\n\nUnrelated body.\n"
    )
    doc = MarkdownParser().parse(md, doc_id="d")
    TreeBuilder().build(doc, out_dir=tmp_path)
    await SummaryBuilder(FakeSummarizer()).build(doc, out_dir=tmp_path)
    await VectorBuilder(FakeEmbedder(dim=32)).build(doc, out_dir=tmp_path)
    await EntityBuilder(HeuristicExtractor()).build(doc, out_dir=tmp_path)
    return DocumentIndex.load(tmp_path)


@pytest.fixture
async def index_without_entities(tmp_path: Path) -> DocumentIndex:
    md = "# Intro\n\nbody.\n"
    doc = MarkdownParser().parse(md, doc_id="d")
    TreeBuilder().build(doc, out_dir=tmp_path)
    await SummaryBuilder(FakeSummarizer()).build(doc, out_dir=tmp_path)
    await VectorBuilder(FakeEmbedder(dim=32)).build(doc, out_dir=tmp_path)
    return DocumentIndex.load(tmp_path)


class TestPreconditions:
    async def test_missing_entities_raises_not_found(
        self, index_without_entities: DocumentIndex
    ) -> None:
        with pytest.raises(IndexNotFoundError):
            await find_mentions(index_without_entities, entity="anything")

    async def test_empty_entity_rejected(
        self, index_with_entities: DocumentIndex
    ) -> None:
        with pytest.raises(ToolError):
            await find_mentions(index_with_entities, entity="  ")


class TestLookup:
    async def test_finds_code_entity_across_sections(
        self, index_with_entities: DocumentIndex
    ) -> None:
        resp = await find_mentions(index_with_entities, entity="Widget")
        assert resp.data["canonical"] == "Widget"
        assert resp.data["kind"] == "code"
        sections = {m["section_id"] for m in resp.data["mentions"]}
        assert sections == {"intro", "intro/sub"}

    async def test_anchors_carry_doc_namespace(
        self, index_with_entities: DocumentIndex
    ) -> None:
        resp = await find_mentions(index_with_entities, entity="Widget")
        for m in resp.data["mentions"]:
            assert m["anchor"].startswith("cairn://d/")

    async def test_kinds_filter(
        self, index_with_entities: DocumentIndex
    ) -> None:
        # "Concept" exists as defined; searching with kinds=["code"] returns empty.
        resp = await find_mentions(
            index_with_entities, entity="Concept", kinds=("code",)
        )
        assert resp.data["mentions"] == []
        # With kinds=["defined"] we get the hit.
        resp = await find_mentions(
            index_with_entities, entity="Concept", kinds=("defined",)
        )
        assert resp.data["kind"] == "defined"
        assert len(resp.data["mentions"]) == 1

    async def test_unknown_entity_returns_empty_not_error(
        self, index_with_entities: DocumentIndex
    ) -> None:
        resp = await find_mentions(index_with_entities, entity="Xenophon")
        assert resp.data["canonical"] is None
        assert resp.data["mentions"] == []
        assert resp.tokens_returned == 0


class TestScope:
    async def test_scope_restricts_mentions(
        self, index_with_entities: DocumentIndex
    ) -> None:
        resp = await find_mentions(
            index_with_entities, entity="Widget", scope="intro/sub"
        )
        ids = {m["section_id"] for m in resp.data["mentions"]}
        assert ids == {"intro/sub"}

    async def test_scope_can_eliminate_all_mentions(
        self, index_with_entities: DocumentIndex
    ) -> None:
        resp = await find_mentions(
            index_with_entities, entity="Widget", scope="other"
        )
        assert resp.data["mentions"] == []
        # But canonical is still resolved.
        assert resp.data["canonical"] == "Widget"
