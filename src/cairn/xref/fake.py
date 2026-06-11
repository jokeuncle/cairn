"""Deterministic cross-reference extractor for tests.

Emits one edge between each consecutive pair of sections (in document
order). Kind is always ``link``. Useful for tests that exercise builder /
reader / tool behavior without coupling to extraction heuristics.
"""

from __future__ import annotations

from collections.abc import Iterable

from cairn.core.types import Document, Span
from cairn.index.entities import Entities
from cairn.xref.base import ExtractionEdge


class FakeXRefExtractor:
    """Linear edge between consecutive sections."""

    name = "fake:linear"

    async def extract(
        self,
        document: Document,
        *,
        entities: Entities | None = None,
    ) -> Iterable[ExtractionEdge]:
        edges: list[ExtractionEdge] = []
        sections = document.sections
        for i in range(len(sections) - 1):
            edges.append(
                ExtractionEdge(
                    src=sections[i].id,
                    dst=sections[i + 1].id,
                    kind="link",
                    confidence=1.0,
                    span=Span(start=0, end=0),
                )
            )
        return edges
