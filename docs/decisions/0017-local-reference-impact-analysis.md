# ADR-0017: Deterministic reference impact analysis

- **Status:** Experimental; Agent advantage requires a separate frozen test
- **Date:** 2026-10-25

## Context

ADR-0016 repairs explicit document links. All six Agent runs passed, but the
cost gate failed. Agents still reconstruct the optional text format and write
graph programs. Graph traversal is deterministic local work, naturally part of
the existing `repo_impact` tool. Sending every edge to an LLM is unnecessary for
an exact bounded reverse-reference query.

## Decision

Add `repo_impact(view="references")`, preserving the default artifact/entity
impact. In this view `doc` and optional `entry` accept an indexed document ID or
exact source path. Compute reverse shortest paths up to `max_hops` (1..8),
direct incoming references, the target's full strongly connected component,
and, when entry is supplied, which documents become unreachable after deleting
the target vertex and its incident edges. Tie-break shortest paths by the whole
source-path sequence. References mean explicit links, not semantic/code impact.

Compute from ADR-0016's cached-only graph, bounded at500 documents/2000 pairs.
Cap each node collection with the existing `max_results` (1..100, default24),
prefer closest reverse paths, and cap proof edges with `max_witnesses`
(1..2000, default200). Report full counts, collection/proof truncation and source
graph incompleteness. Preserve scope and stale/skipped/unavailable records.
Return source anchors for the union of selected shortest paths and all internal
component edges. Optional source text remains a separate explicit read.

Use ordinary JSON for machine-consumed metadata. No new tool, dependency,
storage format, model query, answer generation or source-body read is added.
The implementation is a generic graph operation, without project/task names or
domain-specific expected answers.

## Verification and boundaries

Verify tie-breaking, hop boundaries, cycles, deletion reachability, entry equal
to target, isolated nodes, missing selectors, result/proof/source caps and stale
source behavior. Compare against independently enumerated paths and full graph
closure, including generated graphs. Verify CLI/MCP dispatch offline. Run full
regression, typing/lint, fresh wheel and independent original-source task checks.
Freeze two new target-document tasks and eight fresh sessions before answers:
native Cairn analysis, Cairn graph-only access, an independent helper with the
same analysis mathematics, and raw sources. Preselect the native reference view;
keep the strict I/U/O gate against raw and the matched helper and preserve valid
failures. Graph-only access is a development diagnostic, not a replacement
control. Prior outcomes remain unchanged. The matched helper prevents treating
simple reproducible graph algorithms as a proprietary advantage.

Only reversible local code/tests/docs and isolated evaluation artifacts change.
No production release, global configuration, commits or publication. Legacy
artifact view and the ADR-0016 graph view remain available for rollback.

## Consequences

Local structural analysis avoids requiring an Agent to implement traversal, but
performance, paid adoption, larger-corpus scalability and generalization remain
empirical questions. An independent helper can implement the same mathematics;
this is useful infrastructure, not a claim of a novel graph algorithm.

Outcome:617 regression tests and independent original-source checks for all42
target documents pass. Actual no-provider CLI and MCP stdio calls are verified.
All eight prospectively frozen Agent sessions pass task/source acceptance, but
native I/U/O dominance fails against raw and matched controls. Keep the opt-in
structural operation; do not claim commercial/general Agent savings. See the
[frozen results](../research/2026-10-25-reference-impact.md).
