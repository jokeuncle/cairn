"""EntityExtractor protocol + intermediate extraction hit type.

Extractors emit a sequence of :class:`ExtractionHit` — one per *occurrence*.
The :class:`cairn.index.entities.EntityBuilder` deduplicates hits by
``(canonical, kind)`` into :class:`cairn.core.types.Entity` records.
"""

from __future__ import annotations

from collections.abc import Awaitable, Iterable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from cairn.core.types import Document, EntityKind, Span


class ExtractionHit(BaseModel):
    """One observed occurrence of a candidate entity.

    Spans are offsets *within the section's ``raw_text``*, not into the
    source document. The Entities sub-index stores spans in the same
    coordinate space, so consumers do not need to know about section
    territory boundaries to interpret them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: str
    canonical: str
    surface_form: str
    kind: EntityKind
    span: Span


@runtime_checkable
class EntityExtractor(Protocol):
    """A pluggable extractor.

    Implementations may be sync (heuristic, regex-based) or async (LLM-backed).
    The protocol uses an async signature; sync implementations return an
    already-resolved awaitable.
    """

    name: str

    def extract(
        self,
        document: Document,
    ) -> Awaitable[Iterable[ExtractionHit]]:
        """Return an iterable of extraction hits across ``document``."""
        ...
