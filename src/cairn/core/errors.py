"""Cairn error hierarchy.

Every error raised by Cairn library code derives from `CairnError`. Tool-layer
code translates these into structured MCP error envelopes; never lets them
escape to the transport.
"""

from __future__ import annotations

from typing import Any


class CairnError(Exception):
    """Base class for all Cairn errors."""

    code: str = "INTERNAL"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_envelope(self) -> dict[str, Any]:
        """Convert to the structured MCP error payload.

        See docs/specs/mcp-tools.md §0 for the envelope shape.
        """
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ParseError(CairnError):
    """Source document could not be parsed into a canonical Document AST."""

    code = "PARSE_FAILED"


class IndexBuildError(CairnError):
    """An index builder failed while constructing or updating an artifact."""

    code = "INDEX_BUILD_FAILED"


class IndexNotFoundError(CairnError):
    """A referenced index or section does not exist."""

    code = "NOT_FOUND"


class IndexStaleError(CairnError):
    """The on-disk index is older than its source and must be rebuilt."""

    code = "INDEX_STALE"


class ConfigError(CairnError):
    """Invalid or missing configuration."""

    code = "INVALID_CONFIG"


class ToolError(CairnError):
    """An MCP tool received invalid input or could not produce a result."""

    code = "INVALID_INPUT"
