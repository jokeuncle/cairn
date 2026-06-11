"""``get_section`` and ``expand`` retrieval tools.

Spec: ``docs/specs/mcp-tools.md`` §2 and §3.
"""

from __future__ import annotations

from typing import Any, Literal

from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens

Level = Literal["gist", "synopsis", "digest", "full"]

_LEVEL_ORDER: dict[str, int] = {"gist": 0, "synopsis": 1, "digest": 2, "full": 3}


async def get_section(
    index: DocumentIndex,
    *,
    id: str,
    level: Level = "synopsis",
    include_children: bool = False,
) -> ToolResponse:
    """Fetch one section at the chosen summary level.

    `include_children` is reserved for v0.2 — passing ``True`` raises
    :class:`cairn.core.errors.ToolError`.
    """
    if include_children:
        msg = "include_children is reserved for v0.2; pass False in v0.1"
        raise ToolError(msg, details={"feature": "include_children"})

    node = index.tree.get(id)
    if node is None:
        msg = f"section not found: {id!r}"
        raise IndexNotFoundError(msg, details={"section_id": id})

    content = _content_at_level(index, id, level, node.raw_text)

    next_levels = _levels_deeper_than(level, index, id)

    payload: dict[str, Any] = {
        "doc": index.doc_id,
        "id": node.id,
        "title": node.title,
        "level": level,
        "content": content,
        "anchor": index.anchor(node.id),
        "path": list(node.path),
        "has_children": bool(node.children),
        "next_levels_available": next_levels,
    }
    return ToolResponse(
        data=payload,
        tokens_returned=estimate_tokens(content),
    )


async def expand(
    index: DocumentIndex,
    *,
    id: str,
    to: Literal["synopsis", "digest", "full"],
) -> ToolResponse:
    """Move from a shallower summary to a deeper one. Convenience over ``get_section``.

    Behaves exactly like ``get_section(id, level=to)`` and exists to make
    the progressive-disclosure idiom explicit in agent prompts.
    """
    return await get_section(index, id=id, level=to)


def _content_at_level(
    index: DocumentIndex,
    section_id: str,
    level: str,
    raw_text: str,
) -> str:
    if level == "full":
        return raw_text

    summary = index.summaries.get(section_id)
    if summary is None:
        msg = (
            f"section {section_id!r} has no summary set; "
            "the Summaries index may not have been built"
        )
        raise IndexNotFoundError(msg, details={"section_id": section_id})

    if level == "gist":
        return summary.gist
    if level == "synopsis":
        return summary.synopsis
    if level == "digest":
        if summary.digest is None:
            msg = (
                f"digest not available for {section_id!r}; "
                "v0.1 generates only gist + synopsis"
            )
            raise IndexNotFoundError(
                msg,
                details={"section_id": section_id, "level": level},
            )
        return summary.digest

    msg = f"unknown level: {level!r}"
    raise ToolError(msg, details={"level": level})


def _levels_deeper_than(
    current: str,
    index: DocumentIndex,
    section_id: str,
) -> list[str]:
    current_rank = _LEVEL_ORDER[current]
    deeper = [
        name for name, rank in _LEVEL_ORDER.items() if rank > current_rank
    ]
    # Filter to what is actually available.
    summary = index.summaries.get(section_id)
    available: list[str] = []
    for level in deeper:
        if level == "full":
            available.append(level)
        elif summary is not None and level == "digest" and summary.digest is None:
            continue
        else:
            available.append(level)
    return available
