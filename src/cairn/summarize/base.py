"""Summarizer protocol and level enum.

A `Summarizer` produces a single summary string for a section at a given
granularity level. Pre-computed during indexing; never invoked at query time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class SummaryLevel(StrEnum):
    """The three granularity levels Cairn supports.

    - ``GIST``: ≤ 20 words. The "scent" in IFT terms; used by ``outline``.
    - ``SYNOPSIS``: ≤ 80 words. Used by ``get_section`` (default) and search hits.
    - ``DIGEST``: ≤ 300 words. Used by ``expand`` and ``get_section(level="digest")``.
    """

    GIST = "gist"
    SYNOPSIS = "synopsis"
    DIGEST = "digest"


@dataclass(frozen=True)
class SummaryRequest:
    """One section summary request.

    Batch-capable summarizers receive a sequence of these requests and must
    return one summary per item in the same order.
    """

    title: str
    body: str
    level: SummaryLevel


@runtime_checkable
class Summarizer(Protocol):
    """A pluggable summarizer.

    Implementations should be deterministic for ``(title, body, level)`` when
    possible — use ``temperature=0`` and fixed prompts. The ``name`` attribute
    must encode both the implementation family and the model identifier so
    cache keys correctly invalidate when either changes.

    Examples of valid ``name`` values::

        "fake:words"
        "openai-compat:gpt-4o-mini"
        "openai-compat:llama3.2:3b"
    """

    name: str

    async def summarize(
        self,
        *,
        title: str,
        body: str,
        level: SummaryLevel,
    ) -> str:
        """Produce a summary of ``body`` (titled ``title``) at ``level``.

        Implementations must enforce the level's word budget on the output
        (see ``cairn.summarize.prompts.WORD_BUDGETS``).
        """
        ...


@runtime_checkable
class BatchSummarizer(Summarizer, Protocol):
    """Optional summarizer extension for prompt-level request batching."""

    async def summarize_many(
        self,
        requests: Sequence[SummaryRequest],
    ) -> list[str]:
        """Produce summaries for ``requests`` in order."""
        ...
