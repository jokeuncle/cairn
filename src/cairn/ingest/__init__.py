"""Ingestion layer — parsers from source formats into the canonical Document AST."""

from cairn.ingest.base import Parser
from cairn.ingest.markdown import MarkdownParser

__all__ = ["MarkdownParser", "Parser"]
