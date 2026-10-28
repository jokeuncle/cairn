"""Independent graph-math checks and actual cached/offline impact dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pytest import MonkeyPatch

from cairn.core.config import IndexConfig
from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.dispatch import dispatch_repo_tool
from cairn.embed.fake import FakeEmbedder
from cairn.index.vectors import Vectors
from cairn.repo import repo_impact, sync_repo, write_default_config
from cairn.repo_reference_impact import reference_impact
from cairn.summarize.fake import FakeSummarizer


def _graph(pairs: set[tuple[str, str]], *, complete: bool = True) -> dict[str, Any]:
    names = "abcdef"
    return {
        "nodes": [{"id": f"doc:{n}", "doc": n, "source": n + ".md"} for n in names],
        "edges": [
            {
                "source": f"doc:{a}",
                "target": f"doc:{b}",
                "href": b + ".md",
                "source_anchor": f"cairn://{a}/links",
            }
            for a, b in sorted(pairs)
        ],
        "stats": {"documents": 6, "edges": len(pairs), "truncated": not complete},
        "complete": complete,
        "scope": {"impact": "references only"},
        "stale_documents": [] if complete else ["a"],
        "skipped_documents": [],
        "unavailable_documents": [],
    }


def _analyze(pairs: set[tuple[str, str]], **options: Any) -> dict[str, Any]:
    args: dict[str, Any] = dict(doc="d", entry="a", max_hops=3, max_results=24, max_witnesses=200)
    args.update(options)
    return reference_impact(_graph(pairs), **args)


def test_shortest_path_whole_sequence_ties_cycles_and_vertex_deletion() -> None:
    pairs = {("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e"), ("e", "d"), ("e", "f")}
    result = _analyze(pairs)
    assert result["reverse_references"] == [
        {"source": "a.md", "distance": 2, "path": ["a.md", "b.md", "d.md"]},
        {"source": "b.md", "distance": 1, "path": ["b.md", "d.md"]},
        {"source": "c.md", "distance": 1, "path": ["c.md", "d.md"]},
        {"source": "e.md", "distance": 1, "path": ["e.md", "d.md"]},
    ]
    assert result["strongly_connected_documents"] == ["d.md", "e.md"]
    assert result["disconnected_documents"] == ["e.md", "f.md"]
    assert ("a.md", "c.md") not in {(e["source"], e["target"]) for e in result["witnesses"]}
    assert ("d.md", "e.md") in {(e["source"], e["target"]) for e in result["witnesses"]}


def test_hop_boundary_is_inclusive_and_target_not_its_own_reverse_reference() -> None:
    pairs = {("a", "b"), ("b", "c"), ("c", "d")}
    assert len(_analyze(pairs, max_hops=2)["reverse_references"]) == 2
    assert _analyze(pairs)["reverse_references"][0]["distance"] == 3
    assert _analyze(pairs, doc="d.md")["source"] == "d.md"


def test_isolated_node_no_entry_and_entry_equal_deleted_target() -> None:
    isolated = _analyze(set(), entry=None)
    assert isolated["strongly_connected_documents"] == ["d.md"]
    assert isolated["disconnected_documents"] is None
    assert isolated["reverse_references"] == isolated["witnesses"] == []
    assert _analyze({("d", "e"), ("e", "f")}, entry="d")["disconnected_documents"] == [
        "e.md",
        "f.md",
    ]


def test_collection_and_proof_limits_never_claim_complete() -> None:
    pairs = {("a", "d"), ("b", "d"), ("c", "d"), ("d", "a")}
    limited = _analyze(pairs, max_results=1, max_witnesses=1)
    assert not limited["complete"] and limited["stats"]["truncated"]
    assert limited["stats"]["total"]["direct_referrers"] == 3
    assert len(limited["reverse_references"]) == len(limited["witnesses"]) == 1
    assert limited["stats"]["total"]["strongly_connected_documents"] == 2
    partial = reference_impact(
        _graph(pairs, complete=False),
        doc="d",
        entry=None,
        max_hops=3,
        max_results=24,
        max_witnesses=200,
    )
    assert not partial["complete"] and partial["stale_documents"] == ["a"]


@given(st.sets(st.tuples(st.sampled_from("abcdef"), st.sampled_from("abcdef")), max_size=25))
def test_generated_graphs_match_exhaustive_paths_and_transitive_closure(
    pairs: set[tuple[str, str]],
) -> None:
    pairs = {(a, b) for a, b in pairs if a != b}
    actual = _analyze(pairs)
    expected = []
    for source in "abcef":
        paths = [[source]]
        choices: list[list[str]] = []
        for _ in range(3):
            paths = [
                [*path, b] for path in paths for a, b in pairs if a == path[-1] and b not in path
            ]
            choices.extend(path for path in paths if path[-1] == "d")
        if choices:
            path = min(choices, key=lambda path: (len(path), path))
            expected.append(
                {
                    "source": source + ".md",
                    "distance": len(path) - 1,
                    "path": [n + ".md" for n in path],
                }
            )
    assert actual["reverse_references"] == expected
    full = {(a, b): a == b or (a, b) in pairs for a in "abcdef" for b in "abcdef"}
    remaining = "abcef"
    after = {(a, b): a == b or (a, b) in pairs for a in remaining for b in remaining}
    for nodes, table in [("abcdef", full), (remaining, after)]:
        for via in nodes:
            for a in nodes:
                for b in nodes:
                    table[a, b] |= table[a, via] and table[via, b]
    assert actual["strongly_connected_documents"] == [
        n + ".md" for n in "abcdef" if full["d", n] and full[n, "d"]
    ]
    assert actual["disconnected_documents"] == [
        n + ".md" for n in remaining if full["a", n] and not after["a", n]
    ]


@pytest.fixture
async def impact_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    for a, body in [("a", "[b](b.md)"), ("b", "[c](c.md)"), ("c", "[b](b.md)")]:
        (tmp_path / f"docs/{a}.md").write_text(f"# {a}\n\n{body}\n")
    write_default_config(tmp_path)
    await sync_repo(
        tmp_path,
        summarizer=FakeSummarizer(),
        embedder=FakeEmbedder(dim=64),
        index_config=IndexConfig(),
    )
    return tmp_path


async def test_real_dispatch_source_selectors_cached_stale_content_and_no_vectors(
    impact_repo: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("reference analysis must not read vectors")

    monkeypatch.setattr(Vectors, "entries", forbidden)
    args: dict[str, Any] = {"view": "references", "doc": "docs/b.md", "entry": "docs/a.md"}
    before = await dispatch_repo_tool("repo_impact", args, impact_repo, None)
    assert before["ok"] and before["data"]["complete"]
    assert before["data"]["disconnected_documents"] == ["docs/c.md"]
    assert "analyze_document_references" in [s["name"] for s in before["trace"]["steps"]]
    (impact_repo / "docs/a.md").write_text("# a\n\nLink removed from current source.\n")
    after = (await repo_impact(impact_repo, **args))["data"]
    assert not after["complete"] and after["stale_documents"] == ["docs-a"]
    assert after["reverse_references"] == before["data"]["reverse_references"]
    with pytest.raises(IndexNotFoundError):
        await repo_impact(impact_repo, view="references", doc="docs/absent.md")
    with pytest.raises(IndexNotFoundError):
        await repo_impact(impact_repo, view="references", doc="docs/b.md", entry="absent")


@pytest.mark.parametrize(
    "options",
    [
        {"max_hops": 0},
        {"max_witnesses": 2001},
        {"view": "bad"},
        {"view": "references", "id": "section"},
        {"entry": "docs/a.md"},
    ],
)
async def test_impact_invalid_modes_and_limits_fail_explicitly(
    impact_repo: Path,
    options: dict[str, Any],
) -> None:
    with pytest.raises(ToolError):
        await repo_impact(impact_repo, doc="docs-b", **options)


async def test_default_artifact_impact_is_unchanged(impact_repo: Path) -> None:
    assert await repo_impact(impact_repo, doc="docs-b") == await repo_impact(
        impact_repo, doc="docs-b", view="artifacts"
    )
