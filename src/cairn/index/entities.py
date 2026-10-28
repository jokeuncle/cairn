"""Entities sub-index — extractor outputs, deduplicated and persisted.

The :class:`EntityBuilder` runs an :class:`cairn.entity.base.EntityExtractor`
over a Document, aggregates ``ExtractionHit`` records by ``(canonical, kind)``
into :class:`cairn.core.types.Entity`, and writes ``entities.json``.

The :class:`Entities` reader exposes lookup by canonical / surface form /
section, with optional ``kind`` filtering — exactly what the
``find_mentions`` retrieval tool needs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.core.types import Document, Entity, EntityKind, Mention, Span
from cairn.entity.base import EntityExtractor, ExtractionHit

ENTITIES_FILENAME: Final = "entities.json"
ENTITIES_FORMAT_VERSION: Final = 1


class EntityBuilder:
    """Run an extractor, aggregate hits, persist ``entities.json``."""

    def __init__(self, extractor: EntityExtractor) -> None:
        self.extractor = extractor

    async def build(self, document: Document, *, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / ENTITIES_FILENAME

        hits = await self.extractor.extract(document)
        entities = _aggregate(hits)
        now = datetime.now(UTC)

        payload: dict[str, Any] = {
            "format_version": ENTITIES_FORMAT_VERSION,
            "doc_id": document.id,
            "extractor": self.extractor.name,
            "generated_at": now.isoformat(),
            "entities": [_entity_to_dict(e) for e in entities],
        }

        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return path


class Entities:
    """Loaded entities sub-index. Read-only queries."""

    def __init__(
        self,
        entities: tuple[Entity, ...],
        *,
        doc_id: str,
        extractor: str,
    ) -> None:
        self._all = entities
        self.doc_id = doc_id
        self.extractor = extractor

        # Indexes
        self._by_canonical: dict[tuple[str, str], Entity] = {
            (e.canonical, e.kind): e for e in entities
        }
        self._by_surface: dict[str, list[Entity]] = defaultdict(list)
        self._by_section: dict[str, list[Entity]] = defaultdict(list)
        for ent in entities:
            for sf in ent.surface_forms:
                self._by_surface[sf].append(ent)
            for mention in ent.mentions:
                self._by_section[mention.section_id].append(ent)

    @classmethod
    def load(cls, doc_dir: Path) -> Entities:
        path = doc_dir / ENTITIES_FILENAME
        if not path.exists():
            msg = f"entities.json not found in {doc_dir}"
            raise IndexNotFoundError(msg, details={"path": str(path)})

        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        version = payload.get("format_version")
        if version != ENTITIES_FORMAT_VERSION:
            msg = (
                f"unsupported entities format version: {version!r} "
                f"(expected {ENTITIES_FORMAT_VERSION})"
            )
            raise IndexNotFoundError(msg, details={"path": str(path)})

        entities = tuple(_entity_from_dict(d) for d in payload["entities"])
        return cls(
            entities,
            doc_id=payload["doc_id"],
            extractor=payload["extractor"],
        )

    # -- queries -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._all)

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._all)

    def lookup(
        self,
        name: str,
        *,
        kinds: tuple[EntityKind, ...] | None = None,
    ) -> Entity | None:
        """Return the first matching entity by canonical or any surface form.

        Precedence: canonical match before surface-form match. When ``kinds``
        is supplied, only entities of those kinds are considered.
        """
        for ent in self._candidates(name):
            if kinds is None or ent.kind in kinds:
                return ent
        return None

    def lookup_all(
        self,
        name: str,
        *,
        kinds: tuple[EntityKind, ...] | None = None,
    ) -> list[Entity]:
        """Return every matching entity (across kinds) for ``name``."""
        seen: set[tuple[str, str]] = set()
        out: list[Entity] = []
        for ent in self._candidates(name):
            key = (ent.canonical, ent.kind)
            if key in seen:
                continue
            if kinds is None or ent.kind in kinds:
                out.append(ent)
                seen.add(key)
        return out

    def by_section(self, section_id: str) -> list[Entity]:
        return list(self._by_section.get(section_id, ()))

    def by_kind(self, kind: EntityKind) -> list[Entity]:
        return [e for e in self._all if e.kind == kind]

    def _candidates(self, name: str) -> Iterator[Entity]:
        # Canonical hits first, across all kinds, in extractor order.
        for ent in self._all:
            if ent.canonical == name:
                yield ent
        # Then surface-form matches.
        for ent in self._by_surface.get(name, ()):
            if ent.canonical != name:
                yield ent


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate(hits: Iterable[ExtractionHit]) -> list[Entity]:
    """Fold ``ExtractionHit`` stream into a flat list of :class:`Entity`."""
    by_key: dict[tuple[str, str], _Acc] = {}
    insertion_order: list[tuple[str, str]] = []

    for hit in hits:
        if not hit.canonical:
            msg = "extractor emitted an empty canonical"
            raise IndexBuildError(msg)
        key = (hit.canonical, hit.kind)
        acc = by_key.get(key)
        if acc is None:
            acc = _Acc(canonical=hit.canonical, kind=hit.kind)
            by_key[key] = acc
            insertion_order.append(key)
        acc.surface_forms[hit.surface_form] = None
        acc.mentions.append(Mention(section_id=hit.section_id, span=hit.span))

    return [by_key[key].freeze() for key in insertion_order]


class _Acc:
    __slots__ = ("canonical", "kind", "mentions", "surface_forms")

    def __init__(self, *, canonical: str, kind: EntityKind) -> None:
        self.canonical = canonical
        self.kind = kind
        # dict[str, None] is the cheapest insertion-ordered set in Python.
        self.surface_forms: dict[str, None] = {}
        self.mentions: list[Mention] = []

    def freeze(self) -> Entity:
        return Entity(
            canonical=self.canonical,
            surface_forms=tuple(self.surface_forms.keys()),
            kind=self.kind,
            mentions=tuple(self.mentions),
        )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _entity_to_dict(e: Entity) -> dict[str, Any]:
    return {
        "canonical": e.canonical,
        "surface_forms": list(e.surface_forms),
        "kind": e.kind,
        "mentions": [
            {
                "section_id": m.section_id,
                "span": {"start": m.span.start, "end": m.span.end},
            }
            for m in e.mentions
        ],
    }


def _entity_from_dict(d: dict[str, Any]) -> Entity:
    return Entity(
        canonical=d["canonical"],
        surface_forms=tuple(d["surface_forms"]),
        kind=d["kind"],
        mentions=tuple(
            Mention(
                section_id=m["section_id"],
                span=Span(start=m["span"]["start"], end=m["span"]["end"]),
            )
            for m in d["mentions"]
        ),
    )
