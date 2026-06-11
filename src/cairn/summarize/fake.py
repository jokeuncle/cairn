"""Deterministic, network-free summarizer for tests and dry runs.

Not for production use. Output is a word-truncated prefix of the body, which
preserves enough structure for downstream sanity checks while requiring no
LLM and no network.
"""

from __future__ import annotations

import re
from typing import ClassVar, Final

from cairn.summarize.base import SummaryLevel

_WORD = re.compile(r"\S+")


class FakeSummarizer:
    """Word-truncation summarizer. Deterministic; no network."""

    name: Final = "fake:words"

    _BUDGETS: ClassVar[dict[SummaryLevel, int]] = {
        SummaryLevel.GIST: 15,
        SummaryLevel.SYNOPSIS: 60,
        SummaryLevel.DIGEST: 200,
    }

    async def summarize(
        self,
        *,
        title: str,
        body: str,
        level: SummaryLevel,
    ) -> str:
        budget = self._BUDGETS[level]
        words = _WORD.findall(body)
        if not words:
            return f"{title.strip() or 'Section'}."
        truncated = " ".join(words[:budget])
        if len(words) > budget:
            truncated += "…"
        return truncated
