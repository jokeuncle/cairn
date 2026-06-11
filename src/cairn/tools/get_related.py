"""``get_related`` retrieval tool.

Spec: ``docs/specs/mcp-tools.md`` §7.

Returns neighbors of a section across two channels:

- the tree (``sibling`` / ``parent`` / ``child``)
- the cross-reference graph (``xref``)

Tree neighbors are returned with confidence ``1.0`` and ``relation: null``.
XRef neighbors carry the extractor's confidence and the edge's ``kind`` as
the ``relation`` field (``link``, ``textual``, or ``entity``).

Results are sorted by confidence descending, then by destination id, and
truncated to ``k``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens_of_payload

Kind = Literal["xref", "sibling", "parent", "child"]

_VALID_KINDS: frozenset[str] = frozenset({"xref", "sibling", "parent", "child"})


async def get_related(
    index: DocumentIndex,
    *,
    id: str,
    kinds: Sequence[Kind] = ("xref",),
    k: int = 8,
) -> ToolResponse:
    """Return up to ``k`` neighbors of section ``id`` across requested channels."""
    if k < 1 or k > 32:
        msg = f"k must be in [1, 32]; got {k}"
        raise ToolError(msg, details={"k": k})
    if not kinds:
        msg = "kinds must contain at least one entry"
        raise ToolError(msg)
    bad = [x for x in kinds if x not in _VALID_KINDS]
    if bad:
        msg = f"invalid kinds: {bad}"
        raise ToolError(msg, details={"invalid": bad})

    node = index.tree.get(id)
    if node is None:
        msg = f"section not found: {id!r}"
        raise IndexNotFoundError(msg, details={"section_id": id})

    kind_set = set(kinds)
    neighbors: list[dict[str, Any]] = []

    if "xref" in kind_set and index.xrefs is not None:
        for xref in index.xrefs.outgoing_from(id):
            neighbors.append(
                _neighbor(
                    index,
                    section_id=xref.dst,
                    kind="xref",
                    relation=xref.kind,
                    confidence=xref.confidence,
                )
            )

    if "child" in kind_set:
        for child in index.tree.children_of(id):
            neighbors.append(
                _neighbor(
                    index,
                    section_id=child.id,
                    kind="child",
                    relation=None,
                    confidence=1.0,
                )
            )

    if "parent" in kind_set and node.parent is not None:
        neighbors.append(
            _neighbor(
                index,
                section_id=node.parent,
                kind="parent",
                relation=None,
                confidence=1.0,
            )
        )

    if "sibling" in kind_set and node.parent is not None:
        for sibling in index.tree.children_of(node.parent):
            if sibling.id == id:
                continue
            neighbors.append(
                _neighbor(
                    index,
                    section_id=sibling.id,
                    kind="sibling",
                    relation=None,
                    confidence=1.0,
                )
            )

    neighbors.sort(key=lambda n: (-float(n["confidence"]), n["id"]))
    neighbors = neighbors[:k]

    payload: dict[str, Any] = {
        "id": id,
        "neighbors": neighbors,
    }
    return ToolResponse(
        data=payload,
        tokens_returned=estimate_tokens_of_payload(payload),
    )


def _neighbor(
    index: DocumentIndex,
    *,
    section_id: str,
    kind: str,
    relation: str | None,
    confidence: float,
) -> dict[str, Any]:
    node = index.tree.get(section_id)
    payload: dict[str, Any] = {
        "id": section_id,
        "title": node.title if node is not None else section_id,
        "kind": kind,
        "relation": relation,
        "confidence": confidence,
        "anchor": index.anchor(section_id),
    }
    summary = index.summaries.get(section_id)
    if summary is not None and summary.gist:
        payload["gist"] = summary.gist
    return payload
