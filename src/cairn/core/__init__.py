"""Core types, errors, and configuration for Cairn."""

from cairn.core.errors import (
    CairnError,
    ConfigError,
    IndexBuildError,
    IndexNotFoundError,
    IndexStaleError,
    ParseError,
    ToolError,
)
from cairn.core.types import (
    Document,
    Entity,
    EntityKind,
    Mention,
    SectionNode,
    Span,
    SummarySet,
    XRef,
    XRefKind,
)

__all__ = [
    "CairnError",
    "ConfigError",
    "Document",
    "Entity",
    "EntityKind",
    "IndexBuildError",
    "IndexNotFoundError",
    "IndexStaleError",
    "Mention",
    "ParseError",
    "SectionNode",
    "Span",
    "SummarySet",
    "ToolError",
    "XRef",
    "XRefKind",
]
