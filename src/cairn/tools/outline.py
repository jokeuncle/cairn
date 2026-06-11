"""``outline`` retrieval tool — the cheapest, called first.

Spec: ``docs/specs/mcp-tools.md`` §1.
"""

from __future__ import annotations

from collections.abc import Container, Sequence
from typing import Any, Literal

from cairn.core.errors import ToolError
from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens_of_payload

IncludeLevel = Literal["gist", "synopsis"]

_VALID_INCLUDE: frozenset[str] = frozenset({"gist", "synopsis"})


async def outline(
    index: DocumentIndex,
    *,
    depth: int = 2,
    focus: str | None = None,
    include: Sequence[IncludeLevel] = ("gist",),
) -> ToolResponse:
    """Return a truncated outline tree of the document.

    See docs/specs/mcp-tools.md §1 for full semantics.
    """
    if depth < 1 or depth > 6:
        msg = f"depth must be in [1, 6]; got {depth}"
        raise ToolError(msg, details={"depth": depth})

    if not include:
        msg = "include must contain at least one summary level"
        raise ToolError(msg)

    bad = [x for x in include if x not in _VALID_INCLUDE]
    if bad:
        msg = f"invalid include values: {bad}"
        raise ToolError(msg, details={"invalid": bad})

    forest = index.tree.outline(depth=depth, focus=focus)
    include_set = set(include)
    _attach_summaries(forest, index, include_set)

    payload: dict[str, Any] = {
        "doc": index.doc_id,
        "depth": depth,
        "focus": focus,
        "tree": forest,
    }
    return ToolResponse(
        data=payload,
        tokens_returned=estimate_tokens_of_payload(payload),
    )


def _attach_summaries(
    nodes: list[dict[str, Any]],
    index: DocumentIndex,
    include: Container[str],
) -> None:
    """Mutate the outline forest to add gist/synopsis where requested."""
    for node in nodes:
        sid = node["id"]
        summary = index.summaries.get(sid)
        if summary is not None:
            if "gist" in include and summary.gist:
                node["gist"] = summary.gist
            if "synopsis" in include and summary.synopsis:
                node["synopsis"] = summary.synopsis
        children = node.get("children", [])
        if children:
            _attach_summaries(children, index, include)
