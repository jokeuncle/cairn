"""Naive RAG baseline.

Splits the source text into fixed N-word chunks, embeds each chunk into a
LanceDB table, and serves cosine-similarity retrieval. **Crucially, the
chunker is structure-blind** — chunks straddle headings, paragraphs, and
section boundaries. This is the failure mode Cairn is built to fix; the
baseline lets us measure the cost of that failure.

For comparable recall reporting against Cairn (which returns section ids),
each chunk is mapped to "the section whose span contains the chunk's
midpoint byte" at index time. Deepest section wins on overlap.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from pydantic import BaseModel, ConfigDict

from cairn.core.types import Document, SectionNode
from cairn.embed.base import Embedder
from cairn.index.vectors import l2_normalize

_WORD = re.compile(r"\S+")


class _Chunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: int
    text: str
    byte_start: int
    byte_end: int
    section_id: str | None


class NaiveHit(BaseModel):
    """One retrieval result from the naive baseline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: int
    section_id: str | None
    text: str
    score: float


def chunk_text(text: str, *, chunk_size_words: int = 512) -> list[tuple[int, int, str]]:
    """Split ``text`` into chunks of approximately ``chunk_size_words`` words.

    Returns ``(byte_start, byte_end, chunk_text)`` for each chunk. Word
    boundaries are whitespace-delimited.
    """
    if chunk_size_words < 1:
        msg = f"chunk_size_words must be >= 1; got {chunk_size_words}"
        raise ValueError(msg)
    words = list(_WORD.finditer(text))
    if not words:
        return []
    chunks: list[tuple[int, int, str]] = []
    for i in range(0, len(words), chunk_size_words):
        start = words[i].start()
        end = words[min(i + chunk_size_words - 1, len(words) - 1)].end()
        chunks.append((start, end, text[start:end]))
    return chunks


def assign_section(
    chunk_start: int,
    chunk_end: int,
    sections: Sequence[SectionNode],
) -> str | None:
    """Return the deepest section whose ``span`` contains the chunk's midpoint."""
    midpoint = (chunk_start + chunk_end) // 2
    deepest: SectionNode | None = None
    for section in sections:
        if section.span.start <= midpoint < section.span.end and (
            deepest is None or section.level > deepest.level
        ):
            deepest = section
    return deepest.id if deepest is not None else None


class NaiveRAG:
    """Structure-blind chunk + vector search baseline."""

    name = "naive-rag"
    table_name = "chunks"

    def __init__(
        self,
        embedder: Embedder,
        *,
        chunk_size_words: int = 512,
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            msg = f"batch_size must be >= 1; got {batch_size}"
            raise ValueError(msg)
        self.embedder = embedder
        self.chunk_size_words = chunk_size_words
        self.batch_size = batch_size

    async def index(
        self,
        document: Document,
        source_text: str,
        *,
        out_dir: Path,
    ) -> None:
        chunks = self._build_chunks(document, source_text)
        if not chunks:
            await asyncio.to_thread(self._write_empty_table, out_dir)
            return

        vectors: list[list[float]] = []
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            raw = await self.embedder.embed([c.text for c in batch])
            vectors.extend(l2_normalize(v) for v in raw)

        await asyncio.to_thread(self._write_table, out_dir, chunks, vectors)

    def _build_chunks(self, document: Document, source_text: str) -> list[_Chunk]:
        sections = document.sections
        chunks: list[_Chunk] = []
        for chunk_id, (start, end, text) in enumerate(
            chunk_text(source_text, chunk_size_words=self.chunk_size_words)
        ):
            chunks.append(
                _Chunk(
                    chunk_id=chunk_id,
                    text=text,
                    byte_start=start,
                    byte_end=end,
                    section_id=assign_section(start, end, sections),
                )
            )
        return chunks

    def _write_table(
        self,
        out_dir: Path,
        chunks: list[_Chunk],
        vectors: list[list[float]],
    ) -> None:
        db_path = out_dir / "naive.lance"
        if db_path.exists():
            shutil.rmtree(db_path)
        db = lancedb.connect(str(db_path))
        schema = pa.schema(
            [
                pa.field("chunk_id", pa.int64()),
                pa.field("section_id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.embedder.dim)),
            ]
        )
        table = db.create_table(self.table_name, schema=schema)
        records: list[dict[str, Any]] = [
            {
                "chunk_id": c.chunk_id,
                "section_id": c.section_id or "",
                "text": c.text,
                "vector": v,
            }
            for c, v in zip(chunks, vectors, strict=True)
        ]
        table.add(records)

    def _write_empty_table(self, out_dir: Path) -> None:
        db_path = out_dir / "naive.lance"
        if db_path.exists():
            shutil.rmtree(db_path)
        db = lancedb.connect(str(db_path))
        schema = pa.schema(
            [
                pa.field("chunk_id", pa.int64()),
                pa.field("section_id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.embedder.dim)),
            ]
        )
        db.create_table(self.table_name, schema=schema)

    async def retrieve(
        self,
        query: str,
        *,
        out_dir: Path,
        k: int = 8,
    ) -> list[NaiveHit]:
        if k < 1:
            msg = f"k must be >= 1; got {k}"
            raise ValueError(msg)
        embedded = await self.embedder.embed([query])
        if not embedded:
            return []
        query_vec = l2_normalize(embedded[0])
        return await asyncio.to_thread(self._sync_retrieve, out_dir, query_vec, k)

    def _sync_retrieve(
        self,
        out_dir: Path,
        query_vec: list[float],
        k: int,
    ) -> list[NaiveHit]:
        db = lancedb.connect(str(out_dir / "naive.lance"))
        table = db.open_table(self.table_name)
        rows = (
            table.search(query_vec)
            .distance_type("cosine")
            .limit(k)
            .to_list()
        )
        hits: list[NaiveHit] = []
        for row in rows:
            distance = float(row["_distance"])
            score = max(0.0, min(1.0, 1.0 - distance))
            section_id = row.get("section_id") or None
            hits.append(
                NaiveHit(
                    chunk_id=int(row["chunk_id"]),
                    section_id=section_id,
                    text=str(row["text"]),
                    score=score,
                )
            )
        return hits
