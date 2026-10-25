# ADR-0011: Explicit completeness of full context packs

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Maintainer (continued real-Agent cost optimization)
- **Related:** ADR-0004, ADR-0006, ADR-0010

## Context

Real Codex trajectories already parallelize searches and reads. Tool invocation
counts must not be equated with model turns. Adding a batch-query API without
measuring the critical path is therefore premature.

The existing `repo_context(level="full")` can combine discovery and source
reading, but silently slices each body to `max_section_chars` and tells clients
to fetch full text again even if all returned bodies are already complete.
This obscures the difference between a complete section and a partial excerpt.

## Decision

Keep the catalog, signatures, default summary granularity, ranking and index
formats unchanged. For explicit full context, report `content_scope`,
`source_characters`, and `truncated` on every section. Full means the node's own
original body; descendant bodies remain separate. Tell clients to reuse complete
bodies and expand only truncated content or unmet requirements. Clarify the
existing full context option in the MCP descriptions and server guidance.

No query-time LLM, automatic task decomposition, source mutation, session-global
read suppression, dependency or new storage artifact is introduced.

## Evidence and verification

IRCoT motivates retrieving along dependencies rather than splitting every task
upfront. Adaptive-RAG motivates charging for strategy selection. A-RAG motivates
granularity-aware interfaces and tracking repeated evidence. Its notification
on duplicate reads is not literally zero whole-session cost. LongLLMLingua and
later grounding experiments motivate preserving source conditions and citations.
Links, applicability limits and the experiment ledger belong in the research
report, not a claim that these methods have been reproduced by Cairn.

Test complete, truncated, empty and Unicode bodies, stable citations and
unchanged default disclosure. Freeze source and protocol before fresh real-Agent
attempts. Keep earlier unfavorable results. Measure CLI total/cached/uncached
input and output, executable task acceptance, and overlapping tool batches
separately. This change is a completeness repair; a cost benefit is unproven.
