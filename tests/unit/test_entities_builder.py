"""Tests for cairn.index.entities.EntityBuilder + Entities reader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.entity.fake import FakeEntityExtractor
from cairn.entity.heuristic import HeuristicExtractor
from cairn.index.entities import (
    ENTITIES_FILENAME,
    ENTITIES_FORMAT_VERSION,
    Entities,
    EntityBuilder,
)
from cairn.ingest.markdown import MarkdownParser


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


# -- Build ------------------------------------------------------------------


class TestEntityBuilder:
    async def test_writes_entities_json(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        doc = parser.parse("# S\n\nWith `Foo` mentioned.\n", doc_id="d")
        out = tmp_path / "doc"
        path = await EntityBuilder(HeuristicExtractor()).build(doc, out_dir=out)
        assert path == out / ENTITIES_FILENAME
        assert path.exists()

    async def test_payload_carries_format_version(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        doc = parser.parse("# S\n\n`Foo`", doc_id="d")
        out = tmp_path / "doc"
        await EntityBuilder(HeuristicExtractor()).build(doc, out_dir=out)
        payload = json.loads((out / ENTITIES_FILENAME).read_text())
        assert payload["format_version"] == ENTITIES_FORMAT_VERSION
        assert payload["extractor"] == "heuristic:regex-v2"

    async def test_aggregation_dedupes_by_canonical_kind(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        md = (
            "# A\n\nUses `Widget` once.\n\n"
            "# B\n\nUses `Widget` twice: `Widget` `Widget`.\n"
        )
        doc = parser.parse(md, doc_id="d")
        out = tmp_path / "doc"
        await EntityBuilder(HeuristicExtractor()).build(doc, out_dir=out)
        payload = json.loads((out / ENTITIES_FILENAME).read_text())

        widgets = [e for e in payload["entities"] if e["canonical"] == "Widget"]
        assert len(widgets) == 1
        # 1 mention in A + 3 in B = 4 total
        assert len(widgets[0]["mentions"]) == 4
        section_ids = {m["section_id"] for m in widgets[0]["mentions"]}
        assert section_ids == {"a", "b"}

    async def test_empty_canonical_rejected(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        # Construct an extractor that emits a bad hit.
        from cairn.core.types import Span
        from cairn.entity.base import ExtractionHit

        class BrokenExtractor:
            name = "broken"

            async def extract(self, document):  # type: ignore[no-untyped-def]
                return [
                    ExtractionHit(
                        section_id="a",
                        canonical="",
                        surface_form="",
                        kind="code",
                        span=Span(start=0, end=0),
                    )
                ]

        doc = parser.parse("# A\n\nbody\n", doc_id="d")
        with pytest.raises(IndexBuildError):
            await EntityBuilder(BrokenExtractor()).build(doc, out_dir=tmp_path)


# -- Load ------------------------------------------------------------------


class TestEntitiesReader:
    async def _built(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> tuple[Path, Entities]:
        md = (
            "# A\n\nMentions `Apple` and **Foo**.\n\n"
            "# B\n\nMentions `Apple` again. **Bar** is bold.\n"
        )
        doc = parser.parse(md, doc_id="d")
        out = tmp_path / "doc"
        await EntityBuilder(HeuristicExtractor()).build(doc, out_dir=out)
        return out, Entities.load(out)

    async def test_round_trip(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        _, ents = await self._built(tmp_path, parser)
        assert len(ents) > 0
        assert ents.doc_id == "d"
        assert ents.extractor == "heuristic:regex-v2"

    async def test_load_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(IndexNotFoundError):
            Entities.load(tmp_path / "ghost")

    async def test_lookup_by_canonical(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        _, ents = await self._built(tmp_path, parser)
        apple = ents.lookup("Apple")
        assert apple is not None
        assert apple.canonical == "Apple"
        assert apple.kind == "code"
        sections = {m.section_id for m in apple.mentions}
        assert sections == {"a", "b"}

    async def test_lookup_with_kinds_filter(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        _, ents = await self._built(tmp_path, parser)
        # "Foo" exists only as defined; filter to code → nothing
        none = ents.lookup("Foo", kinds=("code",))
        assert none is None
        defined = ents.lookup("Foo", kinds=("defined",))
        assert defined is not None
        assert defined.kind == "defined"

    async def test_by_section(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        _, ents = await self._built(tmp_path, parser)
        in_a = [e.canonical for e in ents.by_section("a")]
        assert "Apple" in in_a
        assert "Foo" in in_a

    async def test_by_kind(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        _, ents = await self._built(tmp_path, parser)
        defined = [e.canonical for e in ents.by_kind("defined")]
        assert "Foo" in defined
        assert "Bar" in defined
        # No code entities in the defined list.
        code = [e for e in ents.by_kind("code") if e.canonical in defined]
        assert code == []

    async def test_iteration(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        _, ents = await self._built(tmp_path, parser)
        canonicals = [e.canonical for e in ents]
        assert "Apple" in canonicals


# -- Fake extractor end-to-end ---------------------------------------------


class TestFakeExtractor:
    async def test_one_entity_per_section(
        self, tmp_path: Path, parser: MarkdownParser
    ) -> None:
        doc = parser.parse("# Alpha\n\na\n\n# Beta\n\nb\n", doc_id="d")
        out = tmp_path / "doc"
        await EntityBuilder(FakeEntityExtractor()).build(doc, out_dir=out)
        ents = Entities.load(out)
        assert len(ents) == 2
        assert ents.extractor == "fake:per-section"
