"""Embedder protocol.

An ``Embedder`` turns a list of texts into a list of dense vectors. Batching
is the responsibility of the implementation — callers pass a list and may
assume the implementation chooses an efficient batching strategy.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """A pluggable text-embedding model.

    The ``name`` attribute encodes both the implementation family and the
    model identifier (e.g. ``"openai-compat:nomic-embed-text"``) so that
    consumers can use it as a cache-invalidation key and a manifest marker.

    Vectors returned by ``embed`` MUST have length ``dim`` for every text;
    consumers may rely on this invariant when constructing typed vector
    stores. Empty input must return an empty list (not raise).
    """

    name: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed each text in ``texts`` to a ``dim``-dimensional vector."""
        ...
