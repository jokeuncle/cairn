"""XRefExtractor Protocol + intermediate ExtractionEdge type."""

from __future__ import annotations

from collections.abc import Awaitable, Iterable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from cairn.core.types import Document, Span, XRefKind
from cairn.index.entities import Entities


class ExtractionEdge(BaseModel):
    """One observed cross-reference, before deduplication.

    Spans use the same convention as :class:`cairn.entity.base.ExtractionHit`:
    offsets within the *source section's* ``raw_text``. Self-loops (``src ==
    dst``) are dropped by the :class:`cairn.index.xrefs.XRefBuilder`; do not
    emit them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    src: str
    dst: str
    kind: XRefKind
    confidence: float = Field(ge=0.0, le=1.0)
    span: Span


@runtime_checkable
class XRefExtractor(Protocol):
    """Pluggable cross-reference extractor.

    The default :class:`cairn.xref.heuristic.HeuristicXRefExtractor` accepts
    an optional ``Entities`` reader as a constructor argument; the Protocol
    itself only mandates the ``extract`` shape.
    """

    name: str

    def extract(
        self,
        document: Document,
        *,
        entities: Entities | None = None,
    ) -> Awaitable[Iterable[ExtractionEdge]]:
        """Return an iterable of cross-reference edges across ``document``."""
        ...
