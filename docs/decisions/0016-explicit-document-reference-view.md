# ADR-0016: Explicit document references in the repository graph

- **Status:** Experimental; task cost and graph correctness are separate gates
- **Date:** 2026-10-25

## Context

The repository graph only lifts per-document section cross-references. Relative
Markdown links to other indexed documents are absent. This loses explicit
author-provided structure, independently of embedding quality. The existing
`repo_graph`/`repo_impact` tools already belong to the public catalog.

## Decision

Extend `repo_graph` with an opt-in `view="documents"`. Preserve the default
section/entity view. Parse CommonMark hyperlinks from cached Markdown section
bodies, including reference-style definitions shared across sections. Resolve
relative and repository-root paths against known indexed source paths; decode
URL paths once. Exclude external URLs, self-links, code, HTML links and unknown
targets. Heading links are outside this view because cached titles are plain
text. Fragments are retained in the parsed href but not validated.

Return one directed edge per document pair, with occurrence count and a stable
source-section anchor. Source spans use characters in that cached section body.
An optional `include_evidence` adds at most 240 verbatim characters of the source
block, with its own precise span. Never infer semantic or code impact. A `doc`
filter selects incident edges in either direction. Explicit document/reference
caps, stale/skipped/unavailable documents and scope information make incomplete
results observable. No query-time models or original-body reads; normal
repository freshness hashing remains unchanged. No new dependencies or storage
formats. Expose the two existing graph/impact tools through the generic CLI.

## Acceptance and execution boundary

Verify path resolution, cross-section reference definitions, negative links,
pair deduplication, deterministic output, caps, stale cached content, provider
and vector isolation, MCP schemas/dispatch and default-view compatibility.
Run the full regression, typing/lint and a fresh installed wheel. Freeze new
graph-analysis tasks and independent source oracles before Agent answers;
compare the actual CLI, an independent on-demand Markdown graph helper and raw
documents. Preserve all attempts and report full-session token usage. Success
requires correct answers in all tasks; cost superiority is a separate measured
claim against both controls, not a consequence of matching the graph oracle.

Only local source/tests/docs and isolated evaluation artifacts may change.
No commits, publishing, deployment, global configuration, credentials or source
document mutation. A release is not performed in this phase. The old view is
the rollback path; all previous frozen experiment wheels remain unchanged.

## Consequences

This repairs a missing explicit graph relation and makes it accessible offline
after indexing. It does not prove broad generalization, a graph algorithm moat,
model-free cold indexing, valid URL fragments, or commercial cost savings.

Outcome: independent scans match80 directed document pairs and occurrence
counts;605 tests and all six completed real-Agent sessions pass. The cost gate
fails, and one separate adapter-naming infrastructure abort is retained.
See the [frozen study](../research/2026-10-25-document-links.md).
