# ADR-0004: Complete Markdown Ingestion and Compact, Grounded Context

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Maintainer (approved repair and verification scope in this session)
- **Related:** ADR-0001, ARCHITECTURE.md §2.1/§3.3, CLAUDE.md P2/P3/P7/P8

## Context

An independent local-model evaluation found that headingless Markdown files were
successfully indexed with zero sections, and that preambles were discarded.
`repo_context` repeated search hits inside sections and expanded relationship
maps by default. Its returned metadata cost more than its evidence. Sparse
ranking also truncated long section bodies and normalized against only the
terms matched in each result, rewarding incomplete matches.

## Decision

Preserve headingless prose and preambles as synthetic, independent sections,
excluding YAML frontmatter. Existing heading IDs and hierarchy remain unchanged.
Increment the tree producer version so unchanged sources with old indexes are
rebuilt on the next sync. This changes producer semantics, not storage schemas.

Make `repo_context` compact by default: one cited record per selected section,
precomputed summary and bounded verbatim evidence, with an explicit drilldown
instruction. `include_details=true` preserves the previous diagnostic envelope,
including nested hits and expanded relationships. Full section text remains
explicitly requested with `level="full"`; no answer generation or query-time LLM
is introduced. Search, outline, get_section and existing citations remain usable.

Search lexical evidence across complete section bodies and normalize sparse
scores with a query-wide denominator. Keep structure, vector evidence and graph
navigation; do not add repository-specific or evaluation-answer ranking rules.

## Consequences

MCP section identifiers also accept the existing `cairn://doc/section` citation
format. A real agent reused a returned citation as `id`, causing failed reads
and a false claim that documentation was absent. Decode the identifier, infer
its indexed document, and reject malformed URIs or conflicting namespaces.
Plain section IDs remain supported. This adds no new tool or input field.

Existing clients that inspect `repo_context` diagnostic fields must request
`include_details=true`. Default consumers use `context_sections` and anchors.
Reindexing old trees is intentional and automatic on sync; unchanged new indexes
remain no-ops. No new dependency, model provider, storage format or MCP tool is
required. Source documents are never modified.

## Verification contract

Regression tests cover headingless prose, preambles, frontmatter, UTF-8 spans,
anchor collisions, old-producer invalidation, complete-body ranking, compact
context, legacy details and actual MCP calls. Run pytest, ruff and strict mypy.

Freeze the original HTTPX questions and baseline artifacts. Target at least
11/12 on their fixed QA subset and median default context below 2,000 real model
tokens. Freeze additional questions over two other public repositories before
evaluating fixes. Compare against section-aware BM25 and the same semantic
embedder. Preserve prompts, payloads, answers, metrics and failures; report any
unmet targets. These are acceptance targets, not claims of achieved quality.

## Alternatives considered

- Return full documents by default: rejected; violates progressive disclosure.
- Replace the tree with flat vector chunks: rejected; loses navigation and
  cannot repair source completeness or payload duplication.
- Tune to HTTPX names/answers: rejected; evaluation must test transferable rules.
