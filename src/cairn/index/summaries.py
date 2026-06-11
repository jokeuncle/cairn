"""Summaries sub-index — per-section multi-granularity summaries.

``SummaryBuilder`` runs at indexing time and writes ``summaries.json``;
``Summaries`` loads that file and serves queries. Both honor the
:class:`cairn.core.types.SummarySet` contract.

The cache layer (``cairn.summarize.cache.SummaryCache``) is keyed by
``(summarizer.name, level, section_hash)``. Switching to a different
summarizer transparently invalidates prior cache entries; editing a section
invalidates only that section's entries.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.core.types import Document, SectionNode, SummarySet
from cairn.summarize.base import Summarizer, SummaryLevel
from cairn.summarize.cache import SummaryCache

SUMMARIES_FILENAME: Final = "summaries.json"
SUMMARIES_FORMAT_VERSION: Final = 1


def section_hash(node: SectionNode) -> str:
    """Cache-invalidating fingerprint of a section's content.

    Uses ``sha256(title || NUL || raw_text)``. Changes in either invalidate
    cached summaries for that section.
    """
    h = hashlib.sha256()
    h.update(node.title.encode("utf-8"))
    h.update(b"\x00")
    h.update(node.raw_text.encode("utf-8"))
    return h.hexdigest()


class SummaryBuilder:
    """Asynchronously generate and persist summaries for a Document."""

    def __init__(
        self,
        summarizer: Summarizer,
        *,
        cache: SummaryCache | None = None,
        concurrency: int = 4,
    ) -> None:
        if concurrency < 1:
            msg = f"concurrency must be ≥1; got {concurrency}"
            raise IndexBuildError(msg)
        self.summarizer = summarizer
        self.cache = cache
        self.concurrency = concurrency

    async def build(
        self,
        document: Document,
        *,
        out_dir: Path,
        levels: Sequence[SummaryLevel] = (SummaryLevel.GIST, SummaryLevel.SYNOPSIS),
    ) -> Path:
        """Summarize every section in ``document`` and write ``summaries.json``.

        Args:
            document: The parsed document.
            out_dir: Directory to write into. Created if absent.
            levels: Which granularity levels to generate. Order is preserved
                and duplicates are dropped. Defaults to (gist, synopsis) per
                the v0.1 scope.

        Returns:
            Path to the written ``summaries.json``.
        """
        ordered_levels = _dedupe_preserve_order(levels)
        if not ordered_levels:
            msg = "at least one SummaryLevel is required"
            raise IndexBuildError(msg)

        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / SUMMARIES_FILENAME
        now = datetime.now(UTC)
        semaphore = asyncio.Semaphore(self.concurrency)

        async def for_section(node: SectionNode) -> dict[str, Any]:
            return await self._summarize_section(node, ordered_levels, semaphore, now)

        records = await asyncio.gather(
            *(for_section(s) for s in document.sections)
        )

        payload: dict[str, Any] = {
            "format_version": SUMMARIES_FORMAT_VERSION,
            "doc_id": document.id,
            "model": self.summarizer.name,
            "levels": [lvl.value for lvl in ordered_levels],
            "generated_at": now.isoformat(),
            "summaries": list(records),
        }

        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return path

    async def _summarize_section(
        self,
        node: SectionNode,
        levels: Sequence[SummaryLevel],
        semaphore: asyncio.Semaphore,
        now: datetime,
    ) -> dict[str, Any]:
        sh = section_hash(node)
        results: dict[str, str] = {}

        for level in levels:
            cache_key: str | None = None
            cached: str | None = None
            if self.cache is not None:
                cache_key = SummaryCache.key(
                    model=self.summarizer.name,
                    level=level.value,
                    section_hash=sh,
                )
                cached = self.cache.get(cache_key)

            if cached is not None:
                results[level.value] = cached
                continue

            async with semaphore:
                text = await self.summarizer.summarize(
                    title=node.title,
                    body=node.raw_text,
                    level=level,
                )
            results[level.value] = text
            if self.cache is not None and cache_key is not None:
                self.cache.put(cache_key, text)

        return {
            "section_id": node.id,
            "section_hash": sh,
            "gist": results.get(SummaryLevel.GIST.value, ""),
            "synopsis": results.get(SummaryLevel.SYNOPSIS.value, ""),
            "digest": results.get(SummaryLevel.DIGEST.value),
            "model": self.summarizer.name,
            "generated_at": now.isoformat(),
        }


class Summaries:
    """Loaded summaries index. Read-only by section id."""

    def __init__(
        self,
        sets: tuple[SummarySet, ...],
        *,
        doc_id: str,
        model: str,
    ) -> None:
        self._by_id: dict[str, SummarySet] = {s.section_id: s for s in sets}
        self._all = sets
        self.doc_id = doc_id
        self.model = model

    @classmethod
    def load(cls, doc_dir: Path) -> Summaries:
        """Load ``summaries.json`` from a document directory."""
        path = doc_dir / SUMMARIES_FILENAME
        if not path.exists():
            msg = f"summaries.json not found in {doc_dir}"
            raise IndexNotFoundError(msg, details={"path": str(path)})

        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        version = payload.get("format_version")
        if version != SUMMARIES_FORMAT_VERSION:
            msg = (
                f"unsupported summaries format version: {version!r} "
                f"(expected {SUMMARIES_FORMAT_VERSION})"
            )
            raise IndexNotFoundError(msg, details={"path": str(path)})

        sets = tuple(
            SummarySet(
                section_id=record["section_id"],
                gist=record["gist"],
                synopsis=record["synopsis"],
                digest=record.get("digest"),
                model=record["model"],
                section_hash=record["section_hash"],
                generated_at=datetime.fromisoformat(record["generated_at"]),
            )
            for record in payload["summaries"]
        )
        return cls(sets, doc_id=payload["doc_id"], model=payload["model"])

    # -- queries -----------------------------------------------------------

    def get(self, section_id: str) -> SummarySet | None:
        return self._by_id.get(section_id)

    def require(self, section_id: str) -> SummarySet:
        s = self.get(section_id)
        if s is None:
            msg = f"summary not found for section: {section_id!r}"
            raise IndexNotFoundError(msg, details={"section_id": section_id})
        return s

    def __contains__(self, section_id: object) -> bool:
        return isinstance(section_id, str) and section_id in self._by_id

    def __len__(self) -> int:
        return len(self._all)

    def __iter__(self) -> Iterator[SummarySet]:
        return iter(self._all)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _dedupe_preserve_order(levels: Sequence[SummaryLevel]) -> list[SummaryLevel]:
    seen: set[SummaryLevel] = set()
    out: list[SummaryLevel] = []
    for lvl in levels:
        if lvl not in seen:
            seen.add(lvl)
            out.append(lvl)
    return out
