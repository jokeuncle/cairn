"""JSON Schemas for the five v0.1 retrieval tools.

These are advertised to MCP clients via the ``list_tools`` handler. They
are the public contract; updates here are versioned breaking changes per
``docs/specs/mcp-tools.md`` §10.
"""

from __future__ import annotations

from typing import Any, Final

from mcp.types import Tool

_OUTLINE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "depth": {
            "type": "integer",
            "minimum": 1,
            "maximum": 6,
            "default": 2,
            "description": "Maximum heading level to include.",
        },
        "focus": {
            "type": ["string", "null"],
            "default": None,
            "description": "Section id to restrict the outline to.",
        },
        "include": {
            "type": "array",
            "items": {"enum": ["gist", "synopsis"]},
            "default": ["gist"],
            "description": "Which summary levels to attach to each node.",
        },
    },
}

_GET_SECTION_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id"],
    "properties": {
        "id": {
            "type": "string",
            "description": "Section id (hierarchical, slug-based).",
        },
        "level": {
            "enum": ["gist", "synopsis", "digest", "full"],
            "default": "synopsis",
            "description": "Granularity. digest is reserved for v0.2.",
        },
        "include_children": {
            "type": "boolean",
            "default": False,
            "description": "Reserved for v0.2.",
        },
    },
}

_EXPAND_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "to"],
    "properties": {
        "id": {"type": "string"},
        "to": {"enum": ["synopsis", "digest", "full"]},
    },
}

_SEARCH_SEMANTIC_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "scope": {"type": ["string", "null"], "default": None},
        "k": {"type": "integer", "minimum": 1, "maximum": 32, "default": 8},
        "include": {
            "type": "array",
            "items": {"enum": ["synopsis", "head"]},
            "default": ["synopsis", "head"],
        },
    },
}

_SEARCH_KEYWORD_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["terms"],
    "properties": {
        "terms": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "maxItems": 8,
        },
        "scope": {"type": ["string", "null"], "default": None},
        "k": {"type": "integer", "minimum": 1, "maximum": 32, "default": 12},
        "mode": {"enum": ["any", "all"], "default": "any"},
    },
}

_FIND_MENTIONS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entity"],
    "properties": {
        "entity": {
            "type": "string",
            "minLength": 1,
            "description": "Entity name (canonical or any registered surface form).",
        },
        "scope": {"type": ["string", "null"], "default": None},
        "kinds": {
            "type": ["array", "null"],
            "items": {"enum": ["term", "code", "proper", "defined"]},
            "default": None,
        },
    },
}

_GET_RELATED_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id"],
    "properties": {
        "id": {"type": "string", "description": "Section id to find neighbors of."},
        "kinds": {
            "type": "array",
            "items": {"enum": ["xref", "sibling", "parent", "child"]},
            "default": ["xref"],
            "description": "Which relation channels to traverse.",
        },
        "k": {"type": "integer", "minimum": 1, "maximum": 32, "default": 8},
    },
}


CAIRN_TOOLS: Final[list[Tool]] = [
    Tool(
        name="outline",
        description=(
            "Get a structural map of the document. The cheapest tool; "
            "agents should call it first."
        ),
        inputSchema=_OUTLINE_SCHEMA,
    ),
    Tool(
        name="get_section",
        description=(
            "Fetch one section at a chosen summary level (gist/synopsis/full)."
        ),
        inputSchema=_GET_SECTION_SCHEMA,
    ),
    Tool(
        name="expand",
        description=(
            "Move from a shallower summary to a deeper one for a known section. "
            "Equivalent to get_section(id, level=to)."
        ),
        inputSchema=_EXPAND_SCHEMA,
    ),
    Tool(
        name="search_semantic",
        description=(
            "Dense vector search. Use for conceptual queries where exact "
            "wording is unknown."
        ),
        inputSchema=_SEARCH_SEMANTIC_SCHEMA,
    ),
    Tool(
        name="search_keyword",
        description=(
            "Exact (case-insensitive) lexical search. Use for known entities, "
            "code symbols, technical terms."
        ),
        inputSchema=_SEARCH_KEYWORD_SCHEMA,
    ),
    Tool(
        name="find_mentions",
        description=(
            "Locate every section where a named entity is mentioned. Requires "
            "the entities sub-index (v0.2+)."
        ),
        inputSchema=_FIND_MENTIONS_SCHEMA,
    ),
    Tool(
        name="get_related",
        description=(
            "Return neighbors of a section across the cross-reference graph "
            "and the structural tree (xref/sibling/parent/child)."
        ),
        inputSchema=_GET_RELATED_SCHEMA,
    ),
]
