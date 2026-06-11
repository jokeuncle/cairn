"""``search_keyword`` retrieval tool.

Spec: ``docs/specs/mcp-tools.md`` §5.

v0.1 uses a linear scan over loaded sections. For documents up to a few
thousand sections this comfortably stays under the spec's latency target.
A proper inverted index is a v0.2+ optimization.
"""

from __future__ import annotations

from typing import Any, Literal

from cairn.core.errors import ToolError
from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens_of_payload

Mode = Literal["any", "all"]

_HEAD_CHARS: int = 200


async def search_keyword(
    index: DocumentIndex,
    *,
    terms: list[str],
    scope: str | None = None,
    k: int = 12,
    mode: Mode = "any",
) -> ToolResponse:
    """Exact (case-insensitive) lexical search across the document."""
    if not 1 <= len(terms) <= 8:
        msg = f"terms must contain 1-8 entries; got {len(terms)}"
        raise ToolError(msg, details={"count": len(terms)})
    if any(not t.strip() for t in terms):
        msg = "terms must be non-empty strings"
        raise ToolError(msg)
    if k < 1 or k > 32:
        msg = f"k must be in [1, 32]; got {k}"
        raise ToolError(msg, details={"k": k})
    if mode not in ("any", "all"):
        msg = f"mode must be 'any' or 'all'; got {mode!r}"
        raise ToolError(msg, details={"mode": mode})

    lc_terms = [t.lower() for t in terms]

    scored: list[tuple[int, dict[str, Any]]] = []
    for node in index.tree:
        if scope is not None and not _matches_scope(node.id, scope):
            continue

        text_lc = (node.title + "\n" + node.raw_text).lower()
        matches: list[dict[str, Any]] = []
        total_score = 0
        for orig, lc in zip(terms, lc_terms, strict=True):
            count = text_lc.count(lc)
            if count > 0:
                matches.append({"term": orig, "count": count})
                total_score += count * len(orig)

        if not matches:
            continue
        if mode == "all" and len(matches) != len(terms):
            continue

        scored.append(
            (
                total_score,
                {
                    "id": node.id,
                    "title": node.title,
                    "score": total_score,
                    "anchor": index.anchor(node.id),
                    "matches": matches,
                    "head": node.raw_text[:_HEAD_CHARS],
                },
            )
        )

    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    top = [d for _, d in scored[:k]]

    payload: dict[str, Any] = {
        "terms": terms,
        "mode": mode,
        "hits": top,
    }
    return ToolResponse(
        data=payload,
        tokens_returned=estimate_tokens_of_payload(payload),
    )


def _matches_scope(section_id: str, scope: str) -> bool:
    return section_id == scope or section_id.startswith(scope + "/")
