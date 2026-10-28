"""HeuristicXRefExtractor — regex + entity-graph derivation, no model needed.

Combines three sources into one extractor (per ARCHITECTURE.md §2.4):

- **link**: explicit anchor links. ``[text](#anchor)`` resolves to a section
  whose ``id`` ends in ``anchor``. Confidence 0.95 when unique, 0.75 when
  multiple candidates exist.
- **textual**: numeric references like ``§ 2.5`` or ``Section 3.1``. Mapped
  to a section whose ``title`` starts with the same numeric prefix.
  Confidence 0.7.
- **entity**: pairs of sections that share a high-signal *defined* entity.
  Confidence scales with the number of shared entities, capped at 0.8.
  Computed only when an :class:`~cairn.index.entities.Entities` reader is
  supplied.

Self-loops are filtered. Duplicate ``(src, dst, kind)`` triples are
deduplicated by the :class:`~cairn.index.xrefs.XRefBuilder`; this layer just
emits ``ExtractionEdge`` records.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Final

from cairn.core.types import Document, SectionNode, Span
from cairn.index.entities import Entities
from cairn.xref.base import ExtractionEdge

# Markdown anchor link: [text](#anchor) — anchor uses kebab/slug form.
_ANCHOR_LINK = re.compile(r"\[[^\]]+\]\(#([^)\s]+)\)")

# Section reference: "§ 2.5", "Section 3.1", "Chapter 4.2". Captures the
# numeric prefix only.
_SECTION_REF = re.compile(
    r"(?:§\s*|(?:Section|Chapter|§)\s+)(\d+(?:\.\d+)*)\b",
    re.IGNORECASE,
)


# Confidence scores per ARCHITECTURE.md §2.4.
_LINK_CONF_UNIQUE: Final = 0.95
_LINK_CONF_AMBIGUOUS: Final = 0.75
_TEXTUAL_CONF: Final = 0.7
_ENTITY_CONF_BASE: Final = 0.3
_ENTITY_CONF_STEP: Final = 0.2
_ENTITY_CONF_CAP: Final = 0.8


class HeuristicXRefExtractor:
    """Regex + entity-graph cross-reference extractor."""

    name = "heuristic:xref-v1"

    async def extract(
        self,
        document: Document,
        *,
        entities: Entities | None = None,
    ) -> Iterable[ExtractionEdge]:
        sections = document.sections
        if not sections:
            return []

        # Pre-build lookups used by link + textual extractors.
        anchor_to_ids = _build_anchor_index(sections)
        prefix_to_id = _build_prefix_index(sections)

        edges: list[ExtractionEdge] = []
        for section in sections:
            edges.extend(_scan_links(section, anchor_to_ids))
            edges.extend(_scan_textual(section, prefix_to_id))

        if entities is not None:
            edges.extend(_entity_mediated(sections, entities))

        return edges


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------


def _build_anchor_index(sections: tuple[SectionNode, ...]) -> dict[str, list[str]]:
    """Map heading-anchor → list of section_ids whose last slug equals it."""
    index: dict[str, list[str]] = {}
    for section in sections:
        last = section.id.rsplit("/", 1)[-1]
        index.setdefault(last, []).append(section.id)
    return index


def _scan_links(
    section: SectionNode,
    anchor_to_ids: dict[str, list[str]],
) -> Iterator[ExtractionEdge]:
    for match in _ANCHOR_LINK.finditer(section.raw_text):
        anchor = match.group(1).lower()
        candidates = anchor_to_ids.get(anchor, ())
        if not candidates:
            continue
        unique = len(candidates) == 1
        conf = _LINK_CONF_UNIQUE if unique else _LINK_CONF_AMBIGUOUS
        for dst in candidates:
            if dst == section.id:
                continue
            yield ExtractionEdge(
                src=section.id,
                dst=dst,
                kind="link",
                confidence=conf,
                span=Span(start=match.start(1), end=match.end(1)),
            )


# ---------------------------------------------------------------------------
# Textual extraction
# ---------------------------------------------------------------------------


def _build_prefix_index(sections: tuple[SectionNode, ...]) -> dict[str, str]:
    """Map numeric title prefix (``"2.5"``) → section_id.

    Only sections whose title starts with a digit-sequence are indexed.
    First-seen wins on collision.
    """
    index: dict[str, str] = {}
    for section in sections:
        prefix = _numeric_prefix(section.title)
        if prefix and prefix not in index:
            index[prefix] = section.id
    return index


_TITLE_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)*)\b")


def _numeric_prefix(title: str) -> str | None:
    m = _TITLE_PREFIX.match(title)
    return m.group(1) if m else None


def _scan_textual(
    section: SectionNode,
    prefix_to_id: dict[str, str],
) -> Iterator[ExtractionEdge]:
    for match in _SECTION_REF.finditer(section.raw_text):
        number = match.group(1)
        dst = prefix_to_id.get(number)
        if dst is None or dst == section.id:
            continue
        yield ExtractionEdge(
            src=section.id,
            dst=dst,
            kind="textual",
            confidence=_TEXTUAL_CONF,
            span=Span(start=match.start(1), end=match.end(1)),
        )


# ---------------------------------------------------------------------------
# Entity-mediated extraction
# ---------------------------------------------------------------------------


def _entity_mediated(
    sections: tuple[SectionNode, ...],
    entities: Entities,
) -> Iterator[ExtractionEdge]:
    """Emit edges between sections that share defined entities.

    For each defined entity that appears in 2+ sections, every ordered
    section pair contributes one (or one extra) shared count. Confidence
    rises with the count: 1 → 0.5, 2 → 0.7, 3+ → 0.8 (cap).
    """
    # shared_counts[(src, dst)] = number of distinct defined entities in common
    shared: dict[tuple[str, str], int] = {}
    sample_span: dict[tuple[str, str], Span] = {}

    for ent in entities.by_kind("defined"):
        mention_sections = {m.section_id for m in ent.mentions}
        if len(mention_sections) < 2:
            continue
        ordered = sorted(mention_sections)
        for i, src in enumerate(ordered):
            for dst in ordered[i + 1 :]:
                shared[(src, dst)] = shared.get((src, dst), 0) + 1
                shared[(dst, src)] = shared.get((dst, src), 0) + 1
                # Pick *some* span — the first mention in the src section.
                if (src, dst) not in sample_span:
                    for m in ent.mentions:
                        if m.section_id == src:
                            sample_span[(src, dst)] = m.span
                            break
                if (dst, src) not in sample_span:
                    for m in ent.mentions:
                        if m.section_id == dst:
                            sample_span[(dst, src)] = m.span
                            break

    for (src, dst), count in shared.items():
        if src == dst:
            continue
        conf = min(
            _ENTITY_CONF_CAP,
            _ENTITY_CONF_BASE + _ENTITY_CONF_STEP * count,
        )
        span = sample_span.get((src, dst), Span(start=0, end=0))
        yield ExtractionEdge(
            src=src,
            dst=dst,
            kind="entity",
            confidence=conf,
            span=span,
        )
