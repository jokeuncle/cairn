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
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.core.types import Document, SectionNode, SummarySet
from cairn.summarize.base import BatchSummarizer, Summarizer, SummaryLevel, SummaryRequest
from cairn.summarize.cache import SummaryCache

SUMMARIES_FILENAME: Final = "summaries.json"
SUMMARIES_FORMAT_VERSION: Final = 1


@dataclass(frozen=True)
class _PendingSummary:
    node: SectionNode
    level: SummaryLevel
    cache_key: str | None


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
        batch_size: int = 1,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        if concurrency < 1:
            msg = f"concurrency must be ≥1; got {concurrency}"
            raise IndexBuildError(msg)
        if batch_size < 1:
            msg = f"batch_size must be ≥1; got {batch_size}"
            raise IndexBuildError(msg)
        self.summarizer = summarizer
        self.cache = cache
        self.concurrency = concurrency
        self.batch_size = batch_size
        self.progress = progress

    async def build(
        self,
        document: Document,
        *,
        out_dir: Path,
        levels: Sequence[SummaryLevel] = (
            SummaryLevel.GIST,
            SummaryLevel.SYNOPSIS,
            SummaryLevel.DIGEST,
        ),
    ) -> Path:
        """Summarize every section in ``document`` and write ``summaries.json``.

        Args:
            document: The parsed document.
            out_dir: Directory to write into. Created if absent.
            levels: Which granularity levels to generate. Order is preserved
                and duplicates are dropped. Defaults to all three levels
                (gist, synopsis, digest) since v0.2.4.

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
        progress_lock = asyncio.Lock()
        completed = 0
        total = len(document.sections) * len(ordered_levels)
        section_hashes = {node.id: section_hash(node) for node in document.sections}
        results: dict[str, dict[str, str]] = {
            node.id: {} for node in document.sections
        }

        async def mark_progress() -> None:
            nonlocal completed
            async with progress_lock:
                completed += 1
                if self.progress is None:
                    return
                step = max(5, total // 20)
                if completed != 1 and completed != total and completed % step != 0:
                    return
                self.progress(completed, total)

        for level in ordered_levels:
            pending: list[_PendingSummary] = []
            for node in document.sections:
                cache_key: str | None = None
                cached: str | None = None
                if self.cache is not None:
                    cache_key = SummaryCache.key(
                        model=self.summarizer.name,
                        level=level.value,
                        section_hash=section_hashes[node.id],
                    )
                    cached = self.cache.get(cache_key)

                if cached is not None:
                    results[node.id][level.value] = cached
                    await mark_progress()
                    continue
                pending.append(_PendingSummary(node=node, level=level, cache_key=cache_key))

            chunks = [
                pending[i : i + self.batch_size]
                for i in range(0, len(pending), self.batch_size)
            ]

            async def process_chunk(chunk: list[_PendingSummary]) -> None:
                async with semaphore:
                    texts = await self._summarize_uncached_batch(chunk)
                for item, text in zip(chunk, texts, strict=True):
                    results[item.node.id][item.level.value] = text
                    if self.cache is not None and item.cache_key is not None:
                        self.cache.put(item.cache_key, text)
                    await mark_progress()

            await asyncio.gather(*(process_chunk(chunk) for chunk in chunks))

        records = [
            {
                "section_id": node.id,
                "section_hash": section_hashes[node.id],
                "gist": results[node.id].get(SummaryLevel.GIST.value, ""),
                "synopsis": results[node.id].get(SummaryLevel.SYNOPSIS.value, ""),
                "digest": results[node.id].get(SummaryLevel.DIGEST.value),
                "model": self.summarizer.name,
                "generated_at": now.isoformat(),
            }
            for node in document.sections
        ]

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

    async def _summarize_uncached_batch(
        self,
        chunk: Sequence[_PendingSummary],
    ) -> list[str]:
        if not chunk:
            return []
        if len(chunk) > 1 and isinstance(self.summarizer, BatchSummarizer):
            requests = [
                SummaryRequest(
                    title=item.node.title,
                    body=item.node.raw_text,
                    level=item.level,
                )
                for item in chunk
            ]
            texts = await self.summarizer.summarize_many(requests)
            if len(texts) != len(chunk):
                msg = (
                    f"batch summarizer returned {len(texts)} summaries for "
                    f"{len(chunk)} requests"
                )
                raise IndexBuildError(msg)
            return texts
        return [
            await self.summarizer.summarize(
                title=item.node.title,
                body=item.node.raw_text,
                level=item.level,
            )
            for item in chunk
        ]


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
