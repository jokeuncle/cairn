# ADR-0005: Explicit section boundaries and navigable neighbors

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Maintainer (authorized continued navigation optimization)
- **Related:** ADR-0004; ARCHITECTURE.md §2.1; PRODUCT.md §3

## Context

A real MCP agent read a parent section at `level="full"` and answered using
incomplete evidence, missing the child that contained the requested capacity
limit. Another read a single-task section and failed to find its multiple-task
sibling. Markdown can have several root sections: `get_related(sibling)`
incorrectly returned none for roots sharing the document's implicit parent.

## Decision

Keep section content and progressive disclosure unchanged. Add explicit
`content_scope` and bounded navigation metadata to `get_section`/`expand`:
up to eight direct children and eight siblings, carrying IDs, titles and stable
citations, counts and an outline call for the complete map. No neighbor body
text or query-time synthesis is included. Describe that full section text
excludes descendants. Count navigation strings in the token estimate.

Treat document roots as siblings under an implicit document parent in
`get_related`. Preserve confidence ordering, existing limits and signatures.

## Consequences

Responses add a bounded navigation cost. Existing content, citations and tool
inputs remain compatible; `include_children` still does not concatenate bodies.
Consumers can detect omitted navigation entries from total counts and use the
advertised outline call. This improves access to evidence, not guarantees of
agent reasoning or generated-code correctness.

## Verification

Regression checks cover parent-body exclusion, followable child/sibling links,
root siblings, bounded lists, truncation counts, leaf behavior and actual MCP
responses. Matched real-agent experiments retain before/after source snapshots,
all attempts and executable failures. No repository-specific terms or expected
answers enter product logic.
