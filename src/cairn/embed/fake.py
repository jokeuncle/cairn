"""Deterministic, network-free embedder for tests and offline development.

Implementation is a sparse bag-of-words hash projection: each word in the
input lowers onto exactly one dimension (chosen by sha256 hash mod dim).
Vectors are similarity-respecting — two texts that share words land near
each other in cosine space — but the embedder has no semantic understanding.
Suitable for unit tests and pipeline plumbing checks; never for production.
"""

from __future__ import annotations

import hashlib


class FakeEmbedder:
    """Bag-of-words hash embedder. Deterministic; no network."""

    name = "fake:bow-hash"

    def __init__(self, dim: int = 64) -> None:
        if dim < 1:
            msg = f"dim must be >= 1; got {dim}"
            raise ValueError(msg)
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = text.lower().split() or ["__empty__"]
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:8], "big") % self.dim
            vec[idx] += 1.0
        return vec
