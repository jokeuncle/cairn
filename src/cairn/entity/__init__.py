"""Entity extraction — pluggable extractors that mine entities from a Document.

Used by ``cairn.index.entities.EntityBuilder`` at indexing time. The
heuristic extractor is the v0.2.0 default; an LLM-backed extractor for
``term`` and ``proper`` kinds is planned for v0.2.1.

Per ARCHITECTURE.md §2.3, entities come in four kinds — ``term``, ``code``,
``proper``, ``defined``. The heuristic extractor covers ``code`` and
``defined`` without any model dependency.
"""

from cairn.entity.base import EntityExtractor, ExtractionHit
from cairn.entity.fake import FakeEntityExtractor
from cairn.entity.heuristic import HeuristicExtractor

__all__ = [
    "EntityExtractor",
    "ExtractionHit",
    "FakeEntityExtractor",
    "HeuristicExtractor",
]
