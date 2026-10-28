"""XRefs sub-index — cross-references (X), the document graph.

The :class:`XRefBuilder` runs an :class:`cairn.xref.base.XRefExtractor`
over a Document (plus an optional Entities reader), deduplicates
``(src, dst, kind)`` triples by keeping the highest-confidence span, and
writes ``refs.json``.

The :class:`XRefs` reader exposes outgoing/incoming/by-kind queries. Edges
are directed; a backward edge between two sections is its own record.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.core.types import Document, Span, XRef, XRefKind
from cairn.index.entities import Entities
from cairn.xref.base import ExtractionEdge, XRefExtractor

XREFS_FILENAME: Final = "refs.json"
XREFS_FORMAT_VERSION: Final = 1


class XRefBuilder:
    """Run an extractor, aggregate edges, persist ``refs.json``."""

    def __init__(self, extractor: XRefExtractor) -> None:
        self.extractor = extractor

    async def build(
        self,
        document: Document,
        *,
        out_dir: Path,
        entities: Entities | None = None,
    ) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / XREFS_FILENAME

        edges = await self.extractor.extract(document, entities=entities)
        refs = _aggregate(edges)
        now = datetime.now(UTC)

        payload: dict[str, Any] = {
            "format_version": XREFS_FORMAT_VERSION,
            "doc_id": document.id,
            "extractor": self.extractor.name,
            "generated_at": now.isoformat(),
            "refs": [_xref_to_dict(r) for r in refs],
        }

        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return path


class XRefs:
    """Loaded cross-references sub-index. Read-only queries."""

    def __init__(
        self,
        refs: tuple[XRef, ...],
        *,
        doc_id: str,
        extractor: str,
    ) -> None:
        self._all = refs
        self.doc_id = doc_id
        self.extractor = extractor

        self._outgoing: dict[str, list[XRef]] = defaultdict(list)
        self._incoming: dict[str, list[XRef]] = defaultdict(list)
        for ref in refs:
            self._outgoing[ref.src].append(ref)
            self._incoming[ref.dst].append(ref)

    @classmethod
    def load(cls, doc_dir: Path) -> XRefs:
        path = doc_dir / XREFS_FILENAME
        if not path.exists():
            msg = f"refs.json not found in {doc_dir}"
            raise IndexNotFoundError(msg, details={"path": str(path)})

        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        version = payload.get("format_version")
        if version != XREFS_FORMAT_VERSION:
            msg = (
                f"unsupported refs format version: {version!r} "
                f"(expected {XREFS_FORMAT_VERSION})"
            )
            raise IndexNotFoundError(msg, details={"path": str(path)})

        refs = tuple(_xref_from_dict(d) for d in payload["refs"])
        return cls(refs, doc_id=payload["doc_id"], extractor=payload["extractor"])

    # -- queries -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._all)

    def __iter__(self) -> Iterator[XRef]:
        return iter(self._all)

    def outgoing_from(
        self, section_id: str, *, kinds: tuple[XRefKind, ...] | None = None
    ) -> list[XRef]:
        """Outgoing edges sorted by confidence descending."""
        edges = self._outgoing.get(section_id, ())
        if kinds is not None:
            edges = [e for e in edges if e.kind in kinds]
        return sorted(edges, key=lambda r: (-r.confidence, r.dst))

    def incoming_to(
        self, section_id: str, *, kinds: tuple[XRefKind, ...] | None = None
    ) -> list[XRef]:
        edges = self._incoming.get(section_id, ())
        if kinds is not None:
            edges = [e for e in edges if e.kind in kinds]
        return sorted(edges, key=lambda r: (-r.confidence, r.src))

    def by_kind(self, kind: XRefKind) -> list[XRef]:
        return [r for r in self._all if r.kind == kind]


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate(edges: Iterable[ExtractionEdge]) -> list[XRef]:
    """Deduplicate ``(src, dst, kind)``; keep highest-confidence span."""
    by_key: dict[tuple[str, str, str], XRef] = {}
    insertion_order: list[tuple[str, str, str]] = []

    for edge in edges:
        if edge.src == edge.dst:
            continue
        if not edge.src or not edge.dst:
            msg = "extractor emitted an edge with empty endpoint id"
            raise IndexBuildError(msg)
        key = (edge.src, edge.dst, edge.kind)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = XRef(
                src=edge.src,
                dst=edge.dst,
                kind=edge.kind,
                confidence=edge.confidence,
                span=edge.span,
            )
            insertion_order.append(key)
        elif edge.confidence > existing.confidence:
            by_key[key] = XRef(
                src=edge.src,
                dst=edge.dst,
                kind=edge.kind,
                confidence=edge.confidence,
                span=edge.span,
            )

    return [by_key[key] for key in insertion_order]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _xref_to_dict(r: XRef) -> dict[str, Any]:
    return {
        "src": r.src,
        "dst": r.dst,
        "kind": r.kind,
        "confidence": r.confidence,
        "span": {"start": r.span.start, "end": r.span.end},
    }


def _xref_from_dict(d: dict[str, Any]) -> XRef:
    return XRef(
        src=d["src"],
        dst=d["dst"],
        kind=d["kind"],
        confidence=d["confidence"],
        span=Span(start=d["span"]["start"], end=d["span"]["end"]),
    )
