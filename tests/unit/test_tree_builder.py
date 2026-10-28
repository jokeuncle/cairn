"""Unit tests for cairn.index.tree."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.core.types import Document, SectionNode, Span
from cairn.index.tree import TREE_FILENAME, TREE_FORMAT_VERSION, Tree, TreeBuilder
from cairn.ingest.markdown import MarkdownParser


@pytest.fixture
def parsed_simple(simple_md: str) -> Document:
    return MarkdownParser().parse(simple_md, doc_id="simple")


@pytest.fixture
def built_dir(tmp_path: Path, parsed_simple: Document) -> Path:
    out = tmp_path / "simple"
    TreeBuilder().build(parsed_simple, out_dir=out)
    return out


# -- Build ------------------------------------------------------------------


class TestTreeBuilder:
    def test_build_writes_tree_json(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "doc"
        path = TreeBuilder().build(parsed_simple, out_dir=out)
        assert path == out / TREE_FILENAME
        assert path.exists()

    def test_build_creates_missing_directory(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        out = tmp_path / "a" / "b" / "c"
        TreeBuilder().build(parsed_simple, out_dir=out)
        assert (out / TREE_FILENAME).exists()

    def test_payload_carries_format_version(
        self, built_dir: Path
    ) -> None:
        payload = json.loads((built_dir / TREE_FILENAME).read_text())
        assert payload["format_version"] == TREE_FORMAT_VERSION

    def test_payload_preserves_section_order(
        self, built_dir: Path, parsed_simple: Document
    ) -> None:
        payload = json.loads((built_dir / TREE_FILENAME).read_text())
        loaded_ids = [s["id"] for s in payload["sections"]]
        assert loaded_ids == [s.id for s in parsed_simple.sections]

    def test_build_is_deterministic_for_same_input(
        self, tmp_path: Path, parsed_simple: Document
    ) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        TreeBuilder().build(parsed_simple, out_dir=a)
        TreeBuilder().build(parsed_simple, out_dir=b)
        assert (a / TREE_FILENAME).read_text() == (b / TREE_FILENAME).read_text()


# -- Validation -------------------------------------------------------------


def _make_doc(sections: tuple[SectionNode, ...]) -> Document:
    return Document(
        id="t",
        source_path=Path("/tmp/x.md"),
        source_hash="0" * 64,
        sections=sections,
        indexed_at=datetime.now(UTC),
        cairn_version="0.0.1",
    )


def _node(
    *,
    id: str,
    parent: str | None = None,
    children: tuple[str, ...] = (),
    level: int = 1,
) -> SectionNode:
    return SectionNode(
        id=id,
        title=id,
        level=level,
        parent=parent,
        children=children,
        span=Span(start=0, end=1),
        path=(id,),
        raw_text="",
    )


class TestTreeValidation:
    def test_rejects_duplicate_ids(self, tmp_path: Path) -> None:
        doc = _make_doc((_node(id="a"), _node(id="a")))
        with pytest.raises(IndexBuildError):
            TreeBuilder().build(doc, out_dir=tmp_path)

    def test_rejects_unknown_parent(self, tmp_path: Path) -> None:
        doc = _make_doc((_node(id="a", parent="ghost"),))
        with pytest.raises(IndexBuildError):
            TreeBuilder().build(doc, out_dir=tmp_path)

    def test_rejects_unknown_child(self, tmp_path: Path) -> None:
        doc = _make_doc((_node(id="a", children=("ghost",)),))
        with pytest.raises(IndexBuildError):
            TreeBuilder().build(doc, out_dir=tmp_path)


# -- Tree (read-side) -------------------------------------------------------


class TestTreeQueries:
    def test_load_round_trip(
        self, built_dir: Path, parsed_simple: Document
    ) -> None:
        tree = Tree.load(built_dir)
        assert len(tree) == len(parsed_simple.sections)
        for original in parsed_simple.sections:
            loaded = tree.require(original.id)
            assert loaded == original

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(IndexNotFoundError):
            Tree.load(tmp_path / "missing")

    def test_get_returns_none_for_missing(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        assert tree.get("nope") is None

    def test_require_raises_for_missing(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        with pytest.raises(IndexNotFoundError):
            tree.require("nope")

    def test_contains(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        assert "introduction" in tree
        assert "nope" not in tree

    def test_roots_only_top_level(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        assert tuple(r.id for r in tree.roots()) == ("introduction", "reference")

    def test_children_of(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        kids = tree.children_of("introduction")
        assert tuple(k.id for k in kids) == (
            "introduction/quickstart",
            "introduction/configuration",
        )

    def test_descendants_of_dfs(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        ids = [s.id for s in tree.descendants_of("introduction")]
        assert ids == [
            "introduction/quickstart",
            "introduction/configuration",
        ]

    def test_ancestors_of(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        ids = [s.id for s in tree.ancestors_of("reference/api")]
        assert ids == ["reference"]


class TestOutline:
    def test_outline_default_depth(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        outline = tree.outline()
        assert [n["id"] for n in outline] == ["introduction", "reference"]
        assert [c["id"] for c in outline[0]["children"]] == [
            "introduction/quickstart",
            "introduction/configuration",
        ]

    def test_outline_depth_one_omits_children(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        outline = tree.outline(depth=1)
        # All children must be truncated since simple.md has H2 under H1.
        assert all(n["children"] == [] for n in outline)
        assert all(n.get("truncated") is True for n in outline)

    def test_outline_focus_restricts_to_subtree(self, built_dir: Path) -> None:
        tree = Tree.load(built_dir)
        outline = tree.outline(depth=2, focus="introduction")
        assert len(outline) == 1
        assert outline[0]["id"] == "introduction"
        assert [c["id"] for c in outline[0]["children"]] == [
            "introduction/quickstart",
            "introduction/configuration",
        ]
