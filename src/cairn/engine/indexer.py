"""Indexer — single entry point that builds all three v0.1 sub-indexes.

Parses a source document, runs ``TreeBuilder`` synchronously, then
``SummaryBuilder`` and ``VectorBuilder`` asynchronously, and finally writes
the top-level ``manifest.json`` that ties the artifacts together.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cairn import __version__
from cairn.core.errors import IndexNotFoundError
from cairn.core.types import Document
from cairn.embed.base import Embedder
from cairn.engine.manifest import (
    MANIFEST_FILENAME,
    MANIFEST_FORMAT_VERSION,
    Manifest,
    SubIndexEntry,
    read_manifest,
    write_manifest,
)
from cairn.entity.base import EntityExtractor
from cairn.index.entities import (
    ENTITIES_FILENAME,
    ENTITIES_FORMAT_VERSION,
    Entities,
    EntityBuilder,
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
from cairn.index.xrefs import (
    XREFS_FILENAME,
    XREFS_FORMAT_VERSION,
    XRefBuilder,
)
from cairn.ingest.base import Parser
from cairn.summarize.base import Summarizer, SummaryLevel
from cairn.summarize.cache import SummaryCache
from cairn.xref.base import XRefExtractor

_TREE_BUILDER_VERSION = 1


@dataclass(frozen=True)
class IndexResult:
    """Outcome of an :meth:`Indexer.index_path` call.

    ``rebuilt`` is ``False`` when the source's hash matched the previous
    build's manifest and the existing index was kept as-is (a no-op).
    """

    manifest_path: Path
    rebuilt: bool


class Indexer:
    """Orchestrates the sub-index builders for one document.

    Tree + Summaries + Vectors are always built. The Entities sub-index is
    built when ``entity_extractor`` is supplied (default since v0.2).
    """

    def __init__(
        self,
        *,
        parser: Parser,
        summarizer: Summarizer,
        embedder: Embedder,
        entity_extractor: EntityExtractor | None = None,
        xref_extractor: XRefExtractor | None = None,
        summary_cache: SummaryCache | None = None,
        summary_concurrency: int = 4,
        embed_batch_size: int = 32,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.parser = parser
        self.summarizer = summarizer
        self.embedder = embedder
        self.entity_extractor = entity_extractor
        self.xref_extractor = xref_extractor
        self.summary_cache = summary_cache
        self.summary_concurrency = summary_concurrency
        self.embed_batch_size = embed_batch_size
        self.progress = progress

    async def index_path(
        self,
        source: Path,
        *,
        out_dir: Path,
        doc_id: str | None = None,
        summary_levels: Sequence[SummaryLevel] = (
            SummaryLevel.GIST,
            SummaryLevel.SYNOPSIS,
            SummaryLevel.DIGEST,
        ),
        force: bool = False,
    ) -> IndexResult:
        """Parse a source file and build all sub-indexes.

        When ``force`` is ``False`` (default), the indexer first checks
        whether ``out_dir`` already contains a manifest whose source_hash
        matches the new source. If so, the existing index is left untouched
        and ``IndexResult.rebuilt`` is ``False``. Pass ``force=True`` to
        always rebuild.
        """
        document = self.parser.parse(source, doc_id=doc_id)

        if not force and _existing_matches(out_dir, document.source_hash):
            return IndexResult(
                manifest_path=out_dir / MANIFEST_FILENAME,
                rebuilt=False,
            )

        manifest_path = await self.index_document(
            document,
            out_dir=out_dir,
            summary_levels=summary_levels,
        )
        return IndexResult(manifest_path=manifest_path, rebuilt=True)

    async def index_document(
        self,
        document: Document,
        *,
        out_dir: Path,
        summary_levels: Sequence[SummaryLevel] = (
            SummaryLevel.GIST,
            SummaryLevel.SYNOPSIS,
            SummaryLevel.DIGEST,
        ),
    ) -> Path:
        """Run every configured builder against an already-parsed Document."""
        out_dir.mkdir(parents=True, exist_ok=True)

        self._emit("tree: writing")
        TreeBuilder().build(document, out_dir=out_dir)
        self._emit("tree: done")
        self._emit("summaries: starting")
        await SummaryBuilder(
            self.summarizer,
            cache=self.summary_cache,
            concurrency=self.summary_concurrency,
            progress=lambda done, total: self._emit(f"summaries: {done}/{total}"),
        ).build(document, out_dir=out_dir, levels=summary_levels)
        self._emit("summaries: done")
        self._emit("vectors: starting")
        await VectorBuilder(
            self.embedder, batch_size=self.embed_batch_size
        ).build(document, out_dir=out_dir)
        self._emit("vectors: done")

        subindexes: dict[str, SubIndexEntry] = {
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
        }

        entities_reader: Entities | None = None
        if self.entity_extractor is not None:
            self._emit("entities: starting")
            await EntityBuilder(self.entity_extractor).build(
                document, out_dir=out_dir
            )
            self._emit("entities: done")
            subindexes["entities"] = SubIndexEntry(
                path=ENTITIES_FILENAME,
                builder_version=ENTITIES_FORMAT_VERSION,
                extractor=self.entity_extractor.name,
            )
            # Reload from disk so the xref extractor can use the canonical
            # form of the just-built Entities sub-index.
            entities_reader = Entities.load(out_dir)

        if self.xref_extractor is not None:
            self._emit("xrefs: starting")
            await XRefBuilder(self.xref_extractor).build(
                document, out_dir=out_dir, entities=entities_reader
            )
            self._emit("xrefs: done")
            subindexes["xrefs"] = SubIndexEntry(
                path=XREFS_FILENAME,
                builder_version=XREFS_FORMAT_VERSION,
                extractor=self.xref_extractor.name,
            )

        manifest = Manifest(
            format_version=MANIFEST_FORMAT_VERSION,
            doc_id=document.id,
            cairn_version=__version__,
            source_path=str(document.source_path),
            source_hash=document.source_hash,
            indexed_at=datetime.now(UTC),
            subindexes=subindexes,
        )
        self._emit("manifest: writing")
        path = write_manifest(out_dir, manifest)
        self._emit("manifest: done")
        return path

    def _emit(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)


def _existing_matches(out_dir: Path, source_hash: str) -> bool:
    """Return ``True`` when ``out_dir`` holds an index for the same source bytes."""
    if not (out_dir / MANIFEST_FILENAME).exists():
        return False
    try:
        existing = read_manifest(out_dir)
    except IndexNotFoundError:
        return False
    return existing.source_hash == source_hash
