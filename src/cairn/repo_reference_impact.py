"""Deterministic, bounded analysis of an explicit cached document-link graph."""

from __future__ import annotations

from collections import deque
from itertools import pairwise
from typing import Any

from cairn.core.errors import IndexNotFoundError


def _reachable(adjacency: dict[str, set[str]], origin: str, removed: str | None = None) -> set[str]:
    seen: set[str] = set()
    pending = [origin]
    while pending:
        node = pending.pop()
        if node == removed or node in seen:
            continue
        seen.add(node)
        pending.extend(adjacency[node] - seen)
    return seen


def reference_impact(
    graph: dict[str, Any],
    *,
    doc: str,
    entry: str | None,
    max_hops: int,
    max_results: int,
    max_witnesses: int,
) -> dict[str, Any]:
    """Analyze only the supplied graph and disclose every bounded projection.

    Reverse BFS plus decreasing-distance greedy traversal gives shortest paths
    with lexicographic whole-path ties. Two reachability sets give the SCC;
    deleting a vertex and comparing entry reachability gives disconnections.
    """
    names = {node["id"]: node["source"] for node in graph["nodes"]}
    by_source = {node["source"]: node for node in graph["nodes"]}
    by_doc = {node["doc"]: node for node in graph["nodes"]}

    def resolve(selector: str) -> str:
        node = by_doc.get(selector) or by_source.get(selector)
        if node is None:
            raise IndexNotFoundError(
                f"document is not in the selected reference graph: {selector!r}",
                details={"doc": selector, "graph_complete": graph["complete"]},
            )
        return str(node["source"])

    target = resolve(doc)
    origin = resolve(entry) if entry is not None else None
    edges = {(names[e["source"]], names[e["target"]]): e for e in graph["edges"]}
    adjacency: dict[str, set[str]] = {source: set() for source in by_source}
    incoming: dict[str, set[str]] = {source: set() for source in by_source}
    for source, destination in edges:
        adjacency[source].add(destination)
        incoming[destination].add(source)
    distance = {target: 0}
    pending = deque([target])
    while pending:
        node = pending.popleft()
        for parent in sorted(incoming[node]):
            if parent not in distance:
                distance[parent] = distance[node] + 1
                pending.append(parent)
    eligible = sorted(
        (source for source, hops in distance.items() if 0 < hops <= max_hops),
        key=lambda source: (distance[source], source),
    )
    paths: list[dict[str, Any]] = []
    used: set[tuple[str, str]] = set()
    for source in eligible[:max_results]:
        path = [source]
        while path[-1] != target:
            node = path[-1]
            path.append(
                min(child for child in adjacency[node] if distance.get(child) == distance[node] - 1)
            )
        paths.append({"source": source, "distance": distance[source], "path": path})
        used.update(pairwise(path))
    paths.sort(key=lambda item: item["source"])
    component = _reachable(adjacency, target) & distance.keys()
    used.update((a, b) for a, b in edges if a in component and b in component)
    disconnected = (
        sorted(_reachable(adjacency, origin) - _reachable(adjacency, origin, target) - {target})
        if origin is not None
        else None
    )
    proofs = [
        {
            "source": a,
            "target": b,
            "href": edges[a, b]["href"],
            "source_anchor": edges[a, b]["source_anchor"],
        }
        for a, b in sorted(used)[:max_witnesses]
    ]
    counts = {
        "direct_referrers": len(incoming[target]),
        "reverse_references": len(eligible),
        "strongly_connected_documents": len(component),
        "disconnected_documents": len(disconnected) if disconnected is not None else None,
        "witnesses": len(used),
    }
    truncated = any(
        count is not None and count > (max_witnesses if key == "witnesses" else max_results)
        for key, count in counts.items()
    )
    return {
        "view": "references",
        "doc": by_source[target]["doc"],
        "source": target,
        "entry": origin,
        "max_hops": max_hops,
        "direct_referrers": sorted(incoming[target])[:max_results],
        "reverse_references": paths,
        "strongly_connected_documents": sorted(component)[:max_results],
        "disconnected_documents": disconnected[:max_results] if disconnected is not None else None,
        "witnesses": proofs,
        "stats": {"total": counts, "truncated": truncated, "source_graph": graph["stats"]},
        "complete": graph["complete"] and not truncated,
        "scope": graph["scope"],
        "stale_documents": graph["stale_documents"],
        "skipped_documents": graph["skipped_documents"],
        "unavailable_documents": graph["unavailable_documents"],
        "limits": {
            "documents": 500,
            "document_pairs": 2000,
            "results_per_collection": max_results,
            "witnesses": max_witnesses,
        },
    }
