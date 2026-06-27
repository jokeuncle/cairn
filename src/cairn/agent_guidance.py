"""Default guidance for agents deciding when to use Cairn."""

from __future__ import annotations

from typing import Final

DEFAULT_AGENT_USAGE_GUIDANCE: Final[dict[str, tuple[str, ...]]] = {
    "prefer_cairn_for": (
        "repository documentation, product requirements, architecture, setup, "
        "naming, protocols, business workflows, and durable decision records",
        "questions that need cross-document context with citations and stable "
        "section anchors",
        "recovering project knowledge or agent-facing rules from indexed docs",
    ),
    "prefer_other_tools_for": (
        "source-code symbol lookup, callers/callees, and code impact analysis",
        "small implementation edits where the relevant file is already known",
        "test execution, build output inspection, and exact literal searches",
    ),
    "recommended_flow": (
        "Use repo_context first for conceptual documentation or project-knowledge "
        "questions.",
        "Use search_documents when you need ranked hits before choosing a "
        "document.",
        "Use list_documents to inspect the indexed document surface or freshness.",
        "Use per-document tools only after selecting a specific document.",
    ),
}


def agent_usage_guidance() -> dict[str, list[str]]:
    """Return a JSON-serializable copy of Cairn's default agent guidance."""

    return {key: list(values) for key, values in DEFAULT_AGENT_USAGE_GUIDANCE.items()}
