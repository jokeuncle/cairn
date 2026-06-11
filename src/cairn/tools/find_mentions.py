"""``find_mentions`` retrieval tool.

Spec: ``docs/specs/mcp-tools.md`` §6.

Returns every section where a named entity occurs, with stable anchors back
into the source. When the entity is unknown to the index, returns a
successful envelope with an empty ``mentions`` array — "no mentions" is a
valid answer, not an error condition.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from cairn.core.errors import IndexNotFoundError, ToolError
from cairn.core.types import EntityKind
from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens_of_payload

Kind = Literal["term", "code", "proper", "defined"]


async def find_mentions(
    index: DocumentIndex,
    *,
    entity: str,
    scope: str | None = None,
    kinds: Sequence[Kind] | None = None,
) -> ToolResponse:
    """Locate every section that mentions ``entity``.

    The lookup matches by canonical form first, then by registered surface
    forms. When ``kinds`` is supplied, only entities of those kinds are
    considered.
    """
    if not entity.strip():
        msg = "entity must be a non-empty string"
        raise ToolError(msg)

    if index.entities is None:
        msg = (
            "entities sub-index not built for this document; "
            "re-index with v0.2 to enable find_mentions"
        )
        raise IndexNotFoundError(msg, details={"missing": "entities"})

    kinds_tuple: tuple[EntityKind, ...] | None = None
    if kinds is not None:
        kinds_tuple = tuple(kinds)

    ent = index.entities.lookup(entity, kinds=kinds_tuple)
    if ent is None:
        return ToolResponse(
            data={
                "entity": entity,
                "canonical": None,
                "kind": None,
                "mentions": [],
            },
            tokens_returned=0,
        )

    mentions: list[dict[str, Any]] = []
    for m in ent.mentions:
        if scope is not None and not _matches_scope(m.section_id, scope):
            continue
        node = index.tree.get(m.section_id)
        if node is None:
            # Stale extractor output — skip rather than fail the whole call.
            continue
        mentions.append(
            {
                "section_id": m.section_id,
                "title": node.title,
                "anchor": index.anchor(m.section_id),
                "span": [m.span.start, m.span.end],
            }
        )

    payload: dict[str, Any] = {
        "entity": entity,
        "canonical": ent.canonical,
        "kind": ent.kind,
        "mentions": mentions,
    }
    return ToolResponse(
        data=payload,
        tokens_returned=estimate_tokens_of_payload(payload),
    )


def _matches_scope(section_id: str, scope: str) -> bool:
    return section_id == scope or section_id.startswith(scope + "/")
