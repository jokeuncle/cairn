"""Embedding layer — pluggable text → vector encoders.

Used by the index layer (`cairn.index.vectors.VectorBuilder`) at indexing time.
Never invoked at query time except for embedding the user's query string.
"""

from cairn.embed.base import Embedder
from cairn.embed.doubao import DoubaoVisionEmbedder
from cairn.embed.fake import FakeEmbedder
from cairn.embed.openai_compatible import OpenAICompatibleEmbedder

__all__ = [
    "DoubaoVisionEmbedder",
    "Embedder",
    "FakeEmbedder",
    "OpenAICompatibleEmbedder",
]
