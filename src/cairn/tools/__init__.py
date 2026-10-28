"""Retrieval tools — the public API consumed by the MCP server.

Each tool corresponds 1:1 to an MCP tool documented in
``docs/specs/mcp-tools.md``. Tools accept a :class:`DocumentIndex` plus typed
arguments and return a :class:`ToolResponse`. They do not speak MCP
themselves; the ``cairn.mcp`` layer translates :class:`ToolResponse` and
:class:`cairn.core.errors.CairnError` into the MCP wire envelope.
"""

from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens
from cairn.tools.find_mentions import find_mentions
from cairn.tools.get_related import get_related
from cairn.tools.get_section import expand, get_section
from cairn.tools.outline import outline
from cairn.tools.read_range import read_range
from cairn.tools.search_keyword import search_keyword
from cairn.tools.search_semantic import search_semantic

__all__ = [
    "DocumentIndex",
    "ToolResponse",
    "estimate_tokens",
    "expand",
    "find_mentions",
    "get_related",
    "get_section",
    "outline",
    "read_range",
    "search_keyword",
    "search_semantic",
]
