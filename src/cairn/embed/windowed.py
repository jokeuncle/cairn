"""Explicit, lossless input windowing for embedding providers with short contexts."""

from __future__ import annotations

import math

import structlog

from cairn.core.errors import IndexBuildError
from cairn.embed.base import Embedder, embed_query_texts

_log = structlog.get_logger(__name__)


def utf8_windows(text: str, max_bytes: int) -> list[str]:
    """Partition text without dropping bytes or splitting Unicode code points."""
    if max_bytes < 4:
        raise ValueError("max_bytes must be at least 4")
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return [text]
    windows = []
    start = 0
    while start < len(raw):
        end = min(len(raw), start + max_bytes)
        while end < len(raw) and raw[end] & 0xC0 == 0x80:
            end -= 1
        if end < len(raw):
            for separator in (b"\n\n", b"\n", b" "):
                boundary = raw.rfind(separator, start + max_bytes // 2, end)
                if boundary >= 0:
                    end = boundary + len(separator)
                    break
        windows.append(raw[start:end].decode("utf-8"))
        start = end
    return windows


class WindowedEmbedder:
    """Pool all windows into one section vector; enable explicitly at indexing/serving.

    This byte budget is an input bound, not a provider token limit. Leave room
    for provider task prefixes/special tokens. Pooling can dilute localized
    information and adds embedding work; original section bodies stay intact.
    """

    def __init__(
        self, delegate: Embedder, *, max_input_bytes: int = 1500, batch_size: int = 32
    ) -> None:
        if max_input_bytes < 4 or batch_size < 1:
            raise ValueError("max_input_bytes must be >=4 and batch_size must be >=1")
        self.delegate = delegate
        self.max_input_bytes = max_input_bytes
        self.batch_size = batch_size
        self.dim = delegate.dim
        self.name = f"{delegate.name}:utf8-window-v1:{max_input_bytes}:weighted-unit-mean"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, query=False)

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, query=True)

    async def _embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        if not texts:
            return []
        groups = [utf8_windows(text, self.max_input_bytes) for text in texts]
        windows = [window for group in groups for window in group]
        if len(windows) > len(texts):
            _log.info(
                "embedding_window_pooling",
                inputs=len(texts),
                windows=len(windows),
                max_input_bytes=self.max_input_bytes,
            )
        vectors: list[list[float]] = []
        for start in range(0, len(windows), self.batch_size):
            batch = windows[start : start + self.batch_size]
            embedded = (
                await embed_query_texts(self.delegate, batch)
                if query
                else await self.delegate.embed(batch)
            )
            if len(embedded) != len(batch):
                raise IndexBuildError("window embedder returned an incorrect vector count")
            for vector in embedded:
                if len(vector) != self.dim or not all(math.isfinite(value) for value in vector):
                    raise IndexBuildError(
                        "window embedder returned invalid vector dimensions/values"
                    )
            vectors.extend(embedded)
        result = []
        offset = 0
        for group in groups:
            group_vectors = vectors[offset : offset + len(group)]
            offset += len(group)
            if len(group) == 1:
                result.append(group_vectors[0])
                continue
            pooled = [0.0] * self.dim
            for window, vector in zip(group, group_vectors, strict=True):
                norm = math.hypot(*vector)
                weight = len(window.encode("utf-8"))
                if norm:
                    for axis, value in enumerate(vector):
                        pooled[axis] += value / norm * weight
            norm = math.hypot(*pooled)
            result.append([value / norm for value in pooled] if norm else pooled)
        return result
