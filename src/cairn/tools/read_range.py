"""``read_range`` retrieval tool.

Spec: ``docs/specs/mcp-tools.md`` §8.

Reads continuous text across consecutive sections in document order. The
agent gives ``start_id`` and ``end_id``; the tool concatenates each section
as ``"## {title}\\n\\n{raw_text}"`` separated by blank lines, truncating at
the ``max_tokens`` budget. When truncated, ``next_id`` points at the first
section that wasn't included so the agent can continue.
"""

from __future__ import annotations

from typing import Any

from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens


async def read_range(
    index: DocumentIndex,
    *,
    start_id: str,
    end_id: str,
    max_tokens: int = 4000,
) -> ToolResponse:
    """Read continuous content from ``start_id`` through ``end_id``."""
    if max_tokens < 1:
        msg = f"max_tokens must be >= 1; got {max_tokens}"
        raise ToolError(msg, details={"max_tokens": max_tokens})

    sections = list(index.tree)
    ids = [s.id for s in sections]

    try:
        start_idx = ids.index(start_id)
    except ValueError as exc:
        msg = f"start_id not found: {start_id!r}"
        raise IndexNotFoundError(msg, details={"section_id": start_id}) from exc

    try:
        end_idx = ids.index(end_id)
    except ValueError as exc:
        msg = f"end_id not found: {end_id!r}"
        raise IndexNotFoundError(msg, details={"section_id": end_id}) from exc

    if start_idx > end_idx:
        msg = (
            f"start_id {start_id!r} must come before end_id {end_id!r} "
            "in document order"
        )
        raise ToolError(
            msg,
            details={"start_id": start_id, "end_id": end_id},
        )

    parts: list[str] = []
    tokens_so_far = 0
    next_id: str | None = None

    for section in sections[start_idx : end_idx + 1]:
        rendered = _render_section(section.title, section.raw_text)
        part_tokens = estimate_tokens(rendered)
        # Allow the first section even if it alone exceeds the budget — the
        # agent asked for it, and returning nothing is worse than returning
        # a single oversized chunk.
        if parts and tokens_so_far + part_tokens > max_tokens:
            next_id = section.id
            break
        parts.append(rendered)
        tokens_so_far += part_tokens

    content = "\n\n".join(parts)

    payload: dict[str, Any] = {
        "doc": index.doc_id,
        "start_id": start_id,
        "end_id": end_id,
        "content": content,
        "anchor_start": index.anchor(start_id),
        "anchor_end": index.anchor(end_id),
        "truncated": next_id is not None,
        "next_id": next_id,
    }
    return ToolResponse(
        data=payload,
        tokens_returned=tokens_so_far,
    )


def _render_section(title: str, body: str) -> str:
    if body.strip():
        return f"## {title}\n\n{body}"
    return f"## {title}"
