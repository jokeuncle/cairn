# ADR-0010: Compact MCP search results by default

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Maintainer (Agent success and whole-session cost optimization)
- **Related:** ADR-0004, ADR-0006, ADR-0009

## Context

Real Codex CLI runs passed the two composed tasks with Cairn, BM25 and raw
source search. Cairn did not yet have a cost advantage. Codex chose
`search_documents` rather than compact `repo_context`; every result repeated
ranking explanations, signal weights and bookkeeping. The initial controlled
tool subset also omitted the existing `read_range` batching capability.

## Decision

Default MCP `search_documents` to cited source hits, preserving requested
synopsis/head/evidence, document metadata and recovery signals. Add optional
`include_details=true` to retrieve the previous diagnostic payload. Keep the
library search API, ranking, candidate order and source evidence unchanged.
Recompute token estimates from the actual view returned. Full traces remain.

Explain the existing `read_range` tool for adjacent-section reading. Expose it
in the next real-Agent protocol rather than adding another batch tool.

## Consequences and verification

MCP clients relying on numeric scores/explanations must request details.
Existing Python library clients keep their previous responses. Test identical
hit order, citations and evidence between compact and detailed modes, plus
preservation of stale/skipped/embedding recovery signals. Repeat the same real
Agent tasks; retain the unfavorable first-run costs and all later attempts.
Report raw/cached/uncached token counts, never infer dollar savings or claim
general superiority from two tasks.
