"""Indexer — single entry point that builds all three v0.1 sub-indexes.

Parses a source document, runs ``TreeBuilder`` synchronously, then
``SummaryBuilder`` and ``VectorBuilder`` asynchronously, and finally writes
the top-level ``manifest.json`` that ties the artifacts together.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from cairn import __version__
from cairn.core.types import Document
from cairn.embed.base import Embedder
from cairn.engine.manifest import (
    MANIFEST_FORMAT_VERSION,
    Manifest,
    SubIndexEntry,
    write_manifest,
)
from cairn.index.summaries import (
    SUMMARIES_FILENAME,
    SUMMARIES_FORMAT_VERSION,
    SummaryBuilder,
)
from cairn.index.tree import TREE_FILENAME, TreeBuilder
from cairn.index.vectors import (
    VECTORS_FORMAT_VERSION,
    VECTORS_MANIFEST_FILENAME,
    VectorBuilder,
)
from cairn.ingest.base import Parser
from cairn.summarize.base import Summarizer, SummaryLevel
from cairn.summarize.cache import SummaryCache

_TREE_BUILDER_VERSION = 1


class Indexer:
    """Orchestrates the three v0.1 sub-index builders for one document."""

    def __init__(
        self,
        *,
        parser: Parser,
        summarizer: Summarizer,
        embedder: Embedder,
        summary_cache: SummaryCache | None = None,
        summary_concurrency: int = 4,
        embed_batch_size: int = 32,
    ) -> None:
        self.parser = parser
        self.summarizer = summarizer
        self.embedder = embedder
        self.summary_cache = summary_cache
        self.summary_concurrency = summary_concurrency
        self.embed_batch_size = embed_batch_size

    async def index_path(
        self,
        source: Path,
        *,
        out_dir: Path,
        doc_id: str | None = None,
        summary_levels: Sequence[SummaryLevel] = (
            SummaryLevel.GIST,
            SummaryLevel.SYNOPSIS,
        ),
    ) -> Path:
        """Parse a source file and build all sub-indexes. Returns manifest path."""
        document = self.parser.parse(source, doc_id=doc_id)
        return await self.index_document(
            document,
            out_dir=out_dir,
            summary_levels=summary_levels,
        )

    async def index_document(
        self,
        document: Document,
        *,
        out_dir: Path,
        summary_levels: Sequence[SummaryLevel] = (
            SummaryLevel.GIST,
            SummaryLevel.SYNOPSIS,
        ),
    ) -> Path:
        """Run the three builders against an already-parsed Document."""
        out_dir.mkdir(parents=True, exist_ok=True)

        TreeBuilder().build(document, out_dir=out_dir)
        await SummaryBuilder(
            self.summarizer,
            cache=self.summary_cache,
            concurrency=self.summary_concurrency,
        ).build(document, out_dir=out_dir, levels=summary_levels)
        await VectorBuilder(
            self.embedder, batch_size=self.embed_batch_size
        ).build(document, out_dir=out_dir)

        manifest = Manifest(
            format_version=MANIFEST_FORMAT_VERSION,
            doc_id=document.id,
            cairn_version=__version__,
            source_path=str(document.source_path),
            source_hash=document.source_hash,
            indexed_at=datetime.now(UTC),
            subindexes={
                "tree": SubIndexEntry(
                    path=TREE_FILENAME,
                    builder_version=_TREE_BUILDER_VERSION,
                ),
                "summaries": SubIndexEntry(
                    path=SUMMARIES_FILENAME,
                    builder_version=SUMMARIES_FORMAT_VERSION,
                    model=self.summarizer.name,
                    levels=[lvl.value for lvl in summary_levels],
                ),
                "vectors": SubIndexEntry(
                    path=VECTORS_MANIFEST_FILENAME,
                    builder_version=VECTORS_FORMAT_VERSION,
                    embedder=self.embedder.name,
                    dim=self.embedder.dim,
                ),
            },
        )
        return write_manifest(out_dir, manifest)
