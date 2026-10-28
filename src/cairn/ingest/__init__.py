"""Ingestion layer — parsers from source formats into the canonical Document AST."""

from cairn.ingest.base import Parser
from cairn.ingest.markdown import MarkdownParser
from cairn.ingest.markitdown import MarkItDownParser
from cairn.ingest.pdf import PdfParser

__all__ = ["MarkItDownParser", "MarkdownParser", "Parser", "PdfParser"]


def parser_for_path(path) -> Parser:  # type: ignore[no-untyped-def]
    """Pick a parser based on the file's extension.

    Raises :class:`cairn.core.errors.ConfigError` for unknown extensions.
    """
    from pathlib import Path

    from cairn.core.errors import ConfigError

    p = Path(path)
    ext = p.suffix.lower()
    if ext in MarkdownParser.extensions:
        return MarkdownParser()
    if ext in PdfParser.extensions:
        return PdfParser()
    if ext in MarkItDownParser.extensions:
        return MarkItDownParser()
    msg = f"no parser registered for extension {ext!r}"
    raise ConfigError(msg, details={"path": str(p), "extension": ext})


def supported_extensions() -> frozenset[str]:
    """Return every file extension Cairn can dispatch to an ingest parser."""
    return frozenset(
        (*MarkdownParser.extensions, *PdfParser.extensions, *MarkItDownParser.extensions)
    )
