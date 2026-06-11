"""Shared types and helpers for retrieval tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.index.entities import Entities
from cairn.index.summaries import Summaries
from cairn.index.tree import Tree
from cairn.index.vectors import Vectors


class DocumentIndex:
    """All sub-indexes loaded for a single document.

    Holds Tree, Summaries, Vectors, and (since v0.2) Entities. The Entities
    sub-index is optional — older v0.1 indexes don't have it, and tools that
    need it must check ``index.entities is not None``.
    """

    def __init__(
        self,
        *,
        tree: Tree,
        summaries: Summaries,
        vectors: Vectors,
        entities: Entities | None = None,
    ) -> None:
        doc_ids = {
            "tree": tree.doc_id,
            "summaries": summaries.doc_id,
            "vectors": vectors.doc_id,
        }
        if entities is not None:
            doc_ids["entities"] = entities.doc_id
        if len(set(doc_ids.values())) > 1:
            msg = "sub-index doc_id mismatch: " + ", ".join(
                f"{k}={v!r}" for k, v in doc_ids.items()
            )
            raise IndexBuildError(msg, details=doc_ids)

        self.tree = tree
        self.summaries = summaries
        self.vectors = vectors
        self.entities = entities
        self.doc_id = tree.doc_id

    @classmethod
    def load(cls, doc_dir: Path) -> DocumentIndex:
        """Load all sub-indexes from a single document directory.

        Entities is optional: v0.1 indexes don't have it, and we degrade
        gracefully rather than refuse to load.
        """
        entities: Entities | None
        try:
            entities = Entities.load(doc_dir)
        except IndexNotFoundError:
            entities = None
        return cls(
            tree=Tree.load(doc_dir),
            summaries=Summaries.load(doc_dir),
            vectors=Vectors.load(doc_dir),
            entities=entities,
        )

    def anchor(self, section_id: str) -> str:
        """Build the canonical ``cairn://`` anchor for a section."""
        return f"cairn://{self.doc_id}/{section_id}"


class ToolResponse(BaseModel):
    """Successful result of a tool invocation.

    Errors are signaled by raising :class:`cairn.core.errors.CairnError` from
    the tool function; the MCP server wraps them in the structured envelope
    documented in ``docs/specs/mcp-tools.md`` §0.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    data: dict[str, Any]
    tokens_returned: int = Field(ge=0)


def estimate_tokens(text: str) -> int:
    """Estimate the token cost of a text payload.

    Approximation: 1.3 tokens per whitespace-separated word, which tracks
    common English tokenizers within ~10%. Good enough for budget reporting;
    not a substitute for a real tokenizer.
    """
    if not text:
        return 0
    return max(1, int(len(text.split()) * 1.3))


def estimate_tokens_of_payload(payload: Any) -> int:
    """Estimate token cost of every string anywhere in ``payload``."""
    return estimate_tokens(_flatten_text(payload))


def _flatten_text(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_flatten_text(v) for v in obj.values())
    if isinstance(obj, list | tuple):
        return " ".join(_flatten_text(item) for item in obj)
    return ""
