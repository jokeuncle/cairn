"""Tests for cairn.tools.get_related."""

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
from cairn.index.xrefs import XRefBuilder
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.fake import FakeSummarizer
from cairn.tools.base import DocumentIndex
from cairn.tools.get_related import get_related
from cairn.xref.heuristic import HeuristicXRefExtractor


@pytest.fixture
async def index_with_xrefs(tmp_path: Path) -> DocumentIndex:
    md = (
        "# Intro\n\nSee [the API](#api) for details.\n\n"
        "## Quickstart\n\nFirst use Intro then read § 2.\n\n"
        "## Config\n\nConfig body.\n\n"
        "# API\n\nThe interface.\n\n"
        "# 2 Reference\n\nSecond ref.\n"
    )
    doc = MarkdownParser().parse(md, doc_id="d")
    TreeBuilder().build(doc, out_dir=tmp_path)
    await SummaryBuilder(FakeSummarizer()).build(doc, out_dir=tmp_path)
    await VectorBuilder(FakeEmbedder(dim=32)).build(doc, out_dir=tmp_path)
    await EntityBuilder(HeuristicExtractor()).build(doc, out_dir=tmp_path)
    from cairn.index.entities import Entities

    await XRefBuilder(HeuristicXRefExtractor()).build(
        doc, out_dir=tmp_path, entities=Entities.load(tmp_path)
    )
    return DocumentIndex.load(tmp_path)


@pytest.fixture
async def index_without_xrefs(tmp_path: Path) -> DocumentIndex:
    md = "# Intro\n\nbody.\n\n## Sub\n\nsub.\n"
    doc = MarkdownParser().parse(md, doc_id="d")
    TreeBuilder().build(doc, out_dir=tmp_path)
    await SummaryBuilder(FakeSummarizer()).build(doc, out_dir=tmp_path)
    await VectorBuilder(FakeEmbedder(dim=32)).build(doc, out_dir=tmp_path)
    return DocumentIndex.load(tmp_path)


class TestPreconditions:
    async def test_invalid_k_rejected(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        with pytest.raises(ToolError):
            await get_related(index_with_xrefs, id="intro", k=0)
        with pytest.raises(ToolError):
            await get_related(index_with_xrefs, id="intro", k=33)

    async def test_empty_kinds_rejected(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        with pytest.raises(ToolError):
            await get_related(index_with_xrefs, id="intro", kinds=())

    async def test_invalid_kind_rejected(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        with pytest.raises(ToolError):
            await get_related(
                index_with_xrefs,
                id="intro",
                kinds=("bogus",),  # type: ignore[arg-type]
            )

    async def test_unknown_section_id_raises(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        with pytest.raises(IndexNotFoundError):
            await get_related(index_with_xrefs, id="ghost")


class TestTreeChannels:
    async def test_children(self, index_with_xrefs: DocumentIndex) -> None:
        resp = await get_related(index_with_xrefs, id="intro", kinds=("child",))
        ids = {n["id"] for n in resp.data["neighbors"]}
        assert ids == {"intro/quickstart", "intro/config"}

    async def test_parent(self, index_with_xrefs: DocumentIndex) -> None:
        resp = await get_related(
            index_with_xrefs, id="intro/quickstart", kinds=("parent",)
        )
        ids = {n["id"] for n in resp.data["neighbors"]}
        assert ids == {"intro"}

    async def test_sibling_excludes_self(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        resp = await get_related(
            index_with_xrefs, id="intro/quickstart", kinds=("sibling",)
        )
        ids = {n["id"] for n in resp.data["neighbors"]}
        assert "intro/quickstart" not in ids
        assert "intro/config" in ids

    async def test_tree_relations_carry_unit_confidence(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        resp = await get_related(
            index_with_xrefs, id="intro", kinds=("child",)
        )
        assert all(n["confidence"] == 1.0 for n in resp.data["neighbors"])
        # Tree relations have no inner "relation" qualifier.
        assert all(n["relation"] is None for n in resp.data["neighbors"])


class TestXRefChannel:
    async def test_xref_link_appears(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        resp = await get_related(
            index_with_xrefs, id="intro", kinds=("xref",)
        )
        # The link from intro → api should appear.
        ids = {n["id"] for n in resp.data["neighbors"]}
        assert "api" in ids
        link = next(n for n in resp.data["neighbors"] if n["id"] == "api")
        assert link["relation"] == "link"

    async def test_xref_unavailable_returns_empty_not_error(
        self, index_without_xrefs: DocumentIndex
    ) -> None:
        resp = await get_related(
            index_without_xrefs, id="intro", kinds=("xref",)
        )
        # No xrefs sub-index → silently empty (tree relations still work).
        assert resp.data["neighbors"] == []


class TestCombinedAndLimits:
    async def test_results_sorted_by_confidence(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        resp = await get_related(
            index_with_xrefs,
            id="intro",
            kinds=("xref", "child"),
        )
        confs = [float(n["confidence"]) for n in resp.data["neighbors"]]
        assert confs == sorted(confs, reverse=True)

    async def test_k_truncates(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        resp = await get_related(
            index_with_xrefs,
            id="intro",
            kinds=("xref", "child", "sibling"),
            k=1,
        )
        assert len(resp.data["neighbors"]) == 1

    async def test_neighbors_carry_anchor_and_title(
        self, index_with_xrefs: DocumentIndex
    ) -> None:
        resp = await get_related(
            index_with_xrefs, id="intro", kinds=("child",)
        )
        for n in resp.data["neighbors"]:
            assert n["anchor"].startswith("cairn://d/")
            assert n["title"]
