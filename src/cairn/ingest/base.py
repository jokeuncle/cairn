"""Parser protocol — the contract every ingestion plugin must satisfy."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from cairn.core.types import Document


@runtime_checkable
class Parser(Protocol):
    """A source-format parser.

    Implementations live in `cairn.plugins.*` or `cairn.ingest.*`. They must
    preserve heading hierarchy, emit stable slug-based section IDs, and
    populate byte spans into the original source.

    See ARCHITECTURE.md §2.1 for the full set of hard rules.
    """

    name: str
    """Identifier used in config (e.g. ``markdown``, ``pdf``)."""

    extensions: tuple[str, ...]
    """File extensions this parser claims, with leading dot. e.g. ``(".md",)``."""

    def parse(
        self,
        source: Path | bytes | str,
        *,
        doc_id: str | None = None,
    ) -> Document:
        """Parse ``source`` into a canonical :class:`Document`.

        Args:
            source: A path, raw bytes, or text.
            doc_id: Optional explicit document identifier. Required when
                ``source`` is bytes or text. When a path is given and
                ``doc_id`` is omitted, the parser derives it from the
                filename stem.

        Returns:
            A fully populated :class:`Document` with section tree and spans.
        """
        ...
