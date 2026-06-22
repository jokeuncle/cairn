"""JSON Schemas for the five v0.1 retrieval tools.

These are advertised to MCP clients via the ``list_tools`` handler. They
are the public contract; updates here are versioned breaking changes per
``docs/specs/mcp-tools.md`` §10.
"""

from __future__ import annotations

import copy
from typing import Any, Final

from mcp.types import Tool, ToolAnnotations

_TRACE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": True,
    "required": ["server", "tool", "mode", "status", "arguments", "steps"],
    "properties": {
        "server": {"const": "cairn"},
        "tool": {"type": "string"},
        "mode": {"enum": ["document", "repo", "repo_document"]},
        "status": {"enum": ["ok", "error"]},
        "arguments": {
            "type": "object",
            "additionalProperties": True,
            "description": "Normalized MCP arguments received for the tool call.",
        },
        "steps": {
            "type": "array",
            "description": "Human-readable execution steps for AI client inspection.",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["name", "status"],
                "properties": {
                    "name": {"type": "string"},
                    "status": {"enum": ["ok", "error"]},
                },
            },
        },
    },
}

_ERROR_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": True,
    "required": ["code", "message", "details"],
    "properties": {
        "code": {"type": "string"},
        "message": {"type": "string"},
        "details": {"type": "object", "additionalProperties": True},
    },
}

_ENVELOPE_OUTPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "description": (
        "Cairn MCP envelope. Successful calls include data and trace; failed "
        "calls include error and trace."
    ),
    "oneOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok", "tokens_returned", "data", "trace"],
            "properties": {
                "ok": {"const": True},
                "tokens_returned": {"type": "integer", "minimum": 0},
                "data": {"type": "object", "additionalProperties": True},
                "trace": _TRACE_SCHEMA,
            },
        },
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok", "error", "trace"],
            "properties": {
                "ok": {"const": False},
                "error": _ERROR_SCHEMA,
                "trace": _TRACE_SCHEMA,
            },
        },
    ],
}


def _read_only(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, readOnlyHint=True)

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
            "items": {"enum": ["synopsis", "head", "evidence"]},
            "default": ["synopsis", "head", "evidence"],
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

_READ_RANGE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["start_id", "end_id"],
    "properties": {
        "start_id": {"type": "string", "description": "First section to include."},
        "end_id": {
            "type": "string",
            "description": "Last section to include (inclusive).",
        },
        "max_tokens": {
            "type": "integer",
            "minimum": 1,
            "default": 4000,
            "description": "Soft cap on the returned content's token count.",
        },
    },
}


CAIRN_TOOLS: Final[list[Tool]] = [
    Tool(
        name="outline",
        annotations=_read_only("Cairn Outline"),
        description=(
            "Get a structural map of the document. The cheapest tool; "
            "agents should call it first."
        ),
        inputSchema=_OUTLINE_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="get_section",
        annotations=_read_only("Cairn Get Section"),
        description=(
            "Fetch one section at a chosen summary level (gist/synopsis/full)."
        ),
        inputSchema=_GET_SECTION_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="expand",
        annotations=_read_only("Cairn Expand Section"),
        description=(
            "Move from a shallower summary to a deeper one for a known section. "
            "Equivalent to get_section(id, level=to)."
        ),
        inputSchema=_EXPAND_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="search_semantic",
        annotations=_read_only("Cairn Semantic Search"),
        description=(
            "Dense vector search. Use for conceptual queries where exact "
            "wording is unknown."
        ),
        inputSchema=_SEARCH_SEMANTIC_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="search_keyword",
        annotations=_read_only("Cairn Keyword Search"),
        description=(
            "Exact (case-insensitive) lexical search. Use for known entities, "
            "code symbols, technical terms."
        ),
        inputSchema=_SEARCH_KEYWORD_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="find_mentions",
        annotations=_read_only("Cairn Find Mentions"),
        description=(
            "Locate every section where a named entity is mentioned. Requires "
            "the entities sub-index (v0.2+)."
        ),
        inputSchema=_FIND_MENTIONS_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="get_related",
        annotations=_read_only("Cairn Get Related"),
        description=(
            "Return neighbors of a section across the cross-reference graph "
            "and the structural tree (xref/sibling/parent/child)."
        ),
        inputSchema=_GET_RELATED_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="read_range",
        annotations=_read_only("Cairn Read Range"),
        description=(
            "Read continuous content across consecutive sections from "
            "start_id through end_id, truncating at max_tokens."
        ),
        inputSchema=_READ_RANGE_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
]


def _with_doc(schema: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(schema)
    properties = out.setdefault("properties", {})
    properties["doc"] = {
        "type": ["string", "null"],
        "default": None,
        "description": (
            "Repository document id. Omit to use the configured primary doc."
        ),
    }
    return out


def _repo_doc_tool(tool: Tool) -> Tool:
    title = (
        tool.annotations.title
        if tool.annotations is not None and tool.annotations.title is not None
        else tool.name.replace("_", " ").title()
    )
    return Tool(
        name=tool.name,
        annotations=_read_only(f"Cairn Repo {title.removeprefix('Cairn ')}"),
        description=(
            f"{tool.description} Accepts optional `doc` in repo mode. "
            "Returns a structured envelope with `trace.steps` for AI clients."
        ),
        inputSchema=_with_doc(tool.inputSchema),
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    )


_LIST_DOCUMENTS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "state": {
            "type": ["string", "null"],
            "enum": ["indexed", "stale", "missing", "error", "orphaned", None],
            "default": None,
            "description": "Optional state filter.",
        }
    },
}


_SEARCH_DOCUMENTS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": "Conceptual query to search across all indexed repo docs.",
        },
        "k": {"type": "integer", "minimum": 1, "maximum": 32, "default": 8},
        "sections_per_doc": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 8,
            "default": None,
            "description": (
                "Maximum section hits per document. Omit to use "
                ".cairn/config.toml search_sections_per_doc."
            ),
        },
        "include": {
            "type": "array",
            "items": {"enum": ["synopsis", "head", "evidence"]},
            "default": ["synopsis", "head", "evidence"],
            "description": "Fields to attach to each cross-document hit.",
        },
    },
}


_REPO_CONTEXT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Conceptual query. Cairn returns a compact context pack with "
                "ranked hits, selected section content, and a relationship map."
            ),
        },
        "k": {"type": "integer", "minimum": 1, "maximum": 32, "default": 5},
        "sections_per_doc": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 8,
            "default": None,
        },
        "related_k": {
            "type": "integer",
            "minimum": 0,
            "maximum": 12,
            "default": 3,
            "description": "Related sections to attach per selected hit.",
        },
        "level": {
            "enum": ["gist", "synopsis", "full"],
            "default": "synopsis",
            "description": "Content granularity for context_sections.",
        },
        "max_section_chars": {
            "type": "integer",
            "minimum": 200,
            "maximum": 8000,
            "default": 1600,
        },
    },
}


_REPO_GRAPH_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "doc": {
            "type": ["string", "null"],
            "default": None,
            "description": "Optional document id to restrict the graph.",
        },
        "max_sections": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "default": 120,
        },
        "max_entities": {
            "type": "integer",
            "minimum": 0,
            "maximum": 200,
            "default": 40,
        },
        "include_entities": {"type": "boolean", "default": True},
        "include_xrefs": {"type": "boolean", "default": True},
    },
}


_REPO_IMPACT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["doc"],
    "properties": {
        "doc": {
            "type": "string",
            "minLength": 1,
            "description": "Repository document id to inspect.",
        },
        "id": {
            "type": ["string", "null"],
            "default": None,
            "description": (
                "Optional section id. Omit for document-level impact; provide "
                "for section-level impact."
            ),
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 24,
        },
    },
}


REPO_TOOLS: Final[list[Tool]] = [
    Tool(
        name="list_documents",
        annotations=_read_only("Cairn List Documents"),
        description=(
            "List repository documents known to Cairn and their index status. "
            "Use this first when serving a repo-scoped Cairn index."
        ),
        inputSchema=_LIST_DOCUMENTS_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="search_documents",
        annotations=_read_only("Cairn Search Documents"),
        description=(
            "Search across every indexed repository document and return globally "
            "ranked section hits with doc ids. Use this before drilling into a "
            "specific document."
        ),
        inputSchema=_SEARCH_DOCUMENTS_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="repo_context",
        annotations=_read_only("Cairn Repo Context"),
        description=(
            "Composite repo retrieval: search across documents, attach compact "
            "section content, explanations, related sections, and a relationship "
            "map in one call. Use this when an agent needs ready-to-read context."
        ),
        inputSchema=_REPO_CONTEXT_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="repo_graph",
        annotations=_read_only("Cairn Repo Graph"),
        description=(
            "Return a repository documentation relationship map with document, "
            "section, entity, contains, xref, and mention edges. This is docs-only; "
            "use CodeGraph for source-code AST graphs."
        ),
        inputSchema=_REPO_GRAPH_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    Tool(
        name="repo_impact",
        annotations=_read_only("Cairn Repo Impact"),
        description=(
            "Estimate documentation surfaces affected by a document or section "
            "change. This is docs graph impact, not code symbol impact."
        ),
        inputSchema=_REPO_IMPACT_SCHEMA,
        outputSchema=_ENVELOPE_OUTPUT_SCHEMA,
    ),
    *[_repo_doc_tool(tool) for tool in CAIRN_TOOLS],
]
