"""Vectors sub-index — dense embeddings over LanceDB.

Storage layout::

    <doc_dir>/
    ├── vectors.lance/            # LanceDB connect root
    │   └── data.lance/           # table holding (id, vector)
    └── vectors_manifest.json     # embedder name, dim, build metadata

LanceDB is the v0.1 default per ARCHITECTURE.md §7. We use the sync API and
wrap blocking calls in ``asyncio.to_thread`` to satisfy our async-by-default
public surface without adopting LanceDB's still-evolving native async API.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import lancedb
import pyarrow as pa
from pydantic import BaseModel, ConfigDict, Field

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.core.types import Document, SectionNode
from cairn.embed.base import Embedder

VECTORS_DB_DIRNAME: Final = "vectors.lance"
VECTORS_TABLE_NAME: Final = "data"
VECTORS_MANIFEST_FILENAME: Final = "vectors_manifest.json"
VECTORS_FORMAT_VERSION: Final = 1

_SCOPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_/-]*$")


class VectorHit(BaseModel):
    """One result row from a vector search."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    score: float = Field(ge=0.0, le=1.0)


def embedding_text(node: SectionNode) -> str:
    """Compose the text we embed for a section.

    Includes the title so heading information enters the embedding, and falls
    back to title alone for sections with empty bodies.
    """
    body = node.raw_text.strip()
    if not body:
        return node.title
    return f"{node.title}\n\n{body}"


def l2_normalize(vec: list[float]) -> list[float]:
    """Return the L2-normalized copy of ``vec``. Zero vectors are returned unchanged."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return list(vec)
    return [x / norm for x in vec]


class VectorBuilder:
    """Embed and persist section-level vectors for a Document."""

    def __init__(
        self,
        embedder: Embedder,
        *,
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            msg = f"batch_size must be >= 1; got {batch_size}"
            raise IndexBuildError(msg)
        self.embedder = embedder
        self.batch_size = batch_size

    async def build(self, document: Document, *, out_dir: Path) -> Path:
        """Embed every section and write ``vectors.lance/`` + manifest.

        Returns the path to the manifest file.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        db_dir = out_dir / VECTORS_DB_DIRNAME
        manifest_path = out_dir / VECTORS_MANIFEST_FILENAME

        ids = [s.id for s in document.sections]
        texts = [embedding_text(s) for s in document.sections]

        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            raw = await self.embedder.embed(batch)
            if len(raw) != len(batch):
                msg = (
                    f"embedder returned {len(raw)} vectors for batch of "
                    f"{len(batch)}"
                )
                raise IndexBuildError(msg)
            for vec in raw:
                if len(vec) != self.embedder.dim:
                    msg = (
                        f"embedder returned dim={len(vec)} but expected "
                        f"dim={self.embedder.dim}"
                    )
                    raise IndexBuildError(msg)
                vectors.append(l2_normalize(vec))

        await asyncio.to_thread(self._write_table, db_dir, ids, vectors)

        now = datetime.now(UTC)
        manifest = {
            "format_version": VECTORS_FORMAT_VERSION,
            "doc_id": document.id,
            "embedder": self.embedder.name,
            "dim": self.embedder.dim,
            "section_count": len(ids),
            "generated_at": now.isoformat(),
        }
        with manifest_path.open("w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return manifest_path

    def _write_table(
        self,
        db_dir: Path,
        ids: list[str],
        vectors: list[list[float]],
    ) -> None:
        # Full rebuild: clear any previous table data for a clean schema state.
        if db_dir.exists():
            shutil.rmtree(db_dir)

        db = lancedb.connect(str(db_dir))
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.embedder.dim)),
            ]
        )
        table = db.create_table(VECTORS_TABLE_NAME, schema=schema)
        if ids:
            records = [
                {"id": sid, "vector": vec} for sid, vec in zip(ids, vectors, strict=True)
            ]
            table.add(records)


class Vectors:
    """Loaded vectors index. Cosine-similarity search via LanceDB."""

    def __init__(
        self,
        table: Any,
        *,
        doc_id: str,
        embedder: str,
        dim: int,
    ) -> None:
        self._table = table
        self.doc_id = doc_id
        self.embedder = embedder
        self.dim = dim

    @classmethod
    def load(cls, doc_dir: Path) -> Vectors:
        """Load vectors index from a document directory."""
        manifest_path = doc_dir / VECTORS_MANIFEST_FILENAME
        db_dir = doc_dir / VECTORS_DB_DIRNAME
        if not manifest_path.exists():
            msg = f"vectors manifest not found in {doc_dir}"
            raise IndexNotFoundError(msg, details={"path": str(manifest_path)})
        if not db_dir.exists():
            msg = f"vectors.lance directory not found in {doc_dir}"
            raise IndexNotFoundError(msg, details={"path": str(db_dir)})

        with manifest_path.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)

        version = manifest.get("format_version")
        if version != VECTORS_FORMAT_VERSION:
            msg = (
                f"unsupported vectors format version: {version!r} "
                f"(expected {VECTORS_FORMAT_VERSION})"
            )
            raise IndexNotFoundError(msg, details={"path": str(manifest_path)})

        db = lancedb.connect(str(db_dir))
        table = db.open_table(VECTORS_TABLE_NAME)
        return cls(
            table,
            doc_id=manifest["doc_id"],
            embedder=manifest["embedder"],
            dim=manifest["dim"],
        )

    async def search(
        self,
        query: list[float],
        *,
        k: int = 8,
        scope_prefix: str | None = None,
    ) -> list[VectorHit]:
        """Return up to ``k`` nearest sections by cosine similarity.

        When ``scope_prefix`` is given, results are restricted to sections
        whose id equals the prefix or begins with ``f"{prefix}/"``.
        """
        if k < 1:
            msg = f"k must be >= 1; got {k}"
            raise IndexBuildError(msg)
        if len(query) != self.dim:
            msg = f"query dim {len(query)} != index dim {self.dim}"
            raise IndexBuildError(msg)
        if scope_prefix is not None and not _SCOPE_PATTERN.match(scope_prefix):
            msg = (
                f"invalid scope_prefix {scope_prefix!r}; only lowercase "
                "alphanumeric, '-', '_', '/' allowed"
            )
            raise IndexBuildError(msg)

        normalized = l2_normalize(query)
        return await asyncio.to_thread(
            self._sync_search, normalized, k, scope_prefix
        )

    def _sync_search(
        self,
        vec: list[float],
        k: int,
        scope_prefix: str | None,
    ) -> list[VectorHit]:
        q = self._table.search(vec).distance_type("cosine")
        if scope_prefix is not None:
            predicate = (
                f"id = '{scope_prefix}' OR id LIKE '{scope_prefix}/%'"
            )
            q = q.where(predicate, prefilter=True)
        rows = q.limit(k).to_list()

        hits: list[VectorHit] = []
        for row in rows:
            distance = float(row["_distance"])
            score = max(0.0, min(1.0, 1.0 - distance))
            hits.append(VectorHit(id=str(row["id"]), score=score))
        return hits

    async def count(self) -> int:
        """Total number of indexed sections."""
        return await asyncio.to_thread(self._table.count_rows)
