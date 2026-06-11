"""``search_semantic`` retrieval tool.

Spec: ``docs/specs/mcp-tools.md`` §4.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from cairn.core.errors import ToolError
from cairn.embed.base import Embedder
from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens_of_payload

IncludeField = Literal["synopsis", "head"]

_HEAD_CHARS: int = 200
_VALID_INCLUDE: frozenset[str] = frozenset({"synopsis", "head"})


async def search_semantic(
    index: DocumentIndex,
    *,
    embedder: Embedder,
    query: str,
    scope: str | None = None,
    k: int = 8,
    include: Sequence[IncludeField] = ("synopsis", "head"),
) -> ToolResponse:
    """Dense vector search across the document.

    The MCP server passes an :class:`Embedder` instance; tools receive it as
    a typed dependency so they can be unit-tested with a fake.
    """
    if k < 1 or k > 32:
        msg = f"k must be in [1, 32]; got {k}"
        raise ToolError(msg, details={"k": k})
    if not query.strip():
        msg = "query must not be empty"
        raise ToolError(msg)
    bad = [x for x in include if x not in _VALID_INCLUDE]
    if bad:
        msg = f"invalid include values: {bad}"
        raise ToolError(msg, details={"invalid": bad})

    vectors = await embedder.embed([query])
    if not vectors:
        msg = "embedder returned no vector for query"
        raise ToolError(msg)
    query_vec = vectors[0]
    if len(query_vec) != index.vectors.dim:
        msg = (
            f"query embedding dim {len(query_vec)} != "
            f"index dim {index.vectors.dim}"
        )
        raise ToolError(msg)

    hits = await index.vectors.search(query_vec, k=k, scope_prefix=scope)

    include_set = set(include)
    results: list[dict[str, Any]] = []
    for hit in hits:
        node = index.tree.get(hit.id)
        if node is None:
            # Stale vector index entry: skip rather than fail the whole call.
            continue
        summary = index.summaries.get(hit.id)
        result: dict[str, Any] = {
            "id": hit.id,
            "title": node.title,
            "score": hit.score,
            "anchor": index.anchor(hit.id),
        }
        if "synopsis" in include_set and summary is not None and summary.synopsis:
            result["synopsis"] = summary.synopsis
        if "head" in include_set:
            result["head"] = node.raw_text[:_HEAD_CHARS]
        results.append(result)

    payload: dict[str, Any] = {
        "query": query,
        "scope": scope,
        "hits": results,
        "cursor": None,
    }
    return ToolResponse(
        data=payload,
        tokens_returned=estimate_tokens_of_payload(payload),
    )
