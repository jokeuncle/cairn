"""Deterministic entity extractor for tests.

Returns a fixed catalogue of hits regardless of input. Used by tests that
care about the downstream builder/index/tool behavior, not the extraction
heuristics themselves.
"""

from __future__ import annotations

from collections.abc import Iterable

from cairn.core.types import Document, Span
from cairn.entity.base import ExtractionHit


class FakeEntityExtractor:
    """Returns one hit per section, kind=defined, canonical=<section_id>."""

    name = "fake:per-section"

    async def extract(self, document: Document) -> Iterable[ExtractionHit]:
        hits: list[ExtractionHit] = []
        for section in document.sections:
            canonical = section.id.split("/")[-1].replace("-", " ")
            hits.append(
                ExtractionHit(
                    section_id=section.id,
                    canonical=canonical,
                    surface_form=canonical,
                    kind="defined",
                    span=Span(start=0, end=min(len(canonical), len(section.raw_text))),
                )
            )
        return hits
