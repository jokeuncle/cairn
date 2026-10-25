"""Explicit, fingerprinted document/query instructions for embedding models."""

from __future__ import annotations

import hashlib
import json

from cairn.embed.base import Embedder, embed_query_texts


class TaskPrefixEmbedder:
    """Add configured task instructions without changing stored source bodies.

    Place inside WindowedEmbedder so every physical model input receives its
    instruction. Configure only when the model/server expects textual prefixes.
    """

    def __init__(
        self, delegate: Embedder, *, document_prefix: str = "", query_prefix: str = ""
    ) -> None:
        self.delegate = delegate
        self.document_prefix = document_prefix
        self.query_prefix = query_prefix
        self.dim = delegate.dim
        self.name = delegate.name
        if document_prefix or query_prefix:
            policy = json.dumps([document_prefix, query_prefix], ensure_ascii=False).encode("utf-8")
            fingerprint = hashlib.sha256(policy).hexdigest()[:24]
            self.name += f":task-prefix-v1:{fingerprint}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self.delegate.embed([self.document_prefix + text for text in texts])

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return await embed_query_texts(self.delegate, [self.query_prefix + text for text in texts])
