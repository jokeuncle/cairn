# ADR-0002: Production Readiness Priorities

- **Status:** Proposed
- **Date:** 2026-06-12
- **Deciders:** Maintainers
- **Related:** PRODUCT.md, ARCHITECTURE.md, ROADMAP.md, ADR-0001

## Context

Cairn's foundation is intentionally sharp: structure-aware retrieval for large
documents, exposed as MCP tools, with progressive disclosure instead of
context-free chunk dumps. The current implementation already validates that
shape with a clean Markdown walking skeleton, typed tool contracts, local-first
defaults, and a benchmark harness.

The next risk is not product direction. The risk is that the implementation
could remain a compelling demo without crossing the line into production-grade
document infrastructure. Four areas determine that line:

- Large documents need section-level rebuilds, not only whole-source hash
  invalidation.
- Retrieval quality needs hybrid ranking that uses document structure,
  lexical signals, dense vectors, entities, and cross-references together.
- Provider integration must survive the real world, where chat endpoints,
  embedding endpoints, batching semantics, dimensions, and error shapes differ.
- Cairn's claims need public, repeatable measurements across realistic
  documents, languages, and workloads.

These priorities do not expand Cairn into a general-purpose RAG framework. They
make the existing thesis measurable and reliable.

## Decision

Phase 2 should explicitly prove Cairn's production-readiness by prioritizing
six implementation tracks:

1. **Section-level incremental indexing.** Persist per-section fingerprints and
   per-builder state so changed sections, descendants, summaries, vectors,
   entities, and cross-references can be rebuilt selectively. Writes should use
   temporary artifacts and atomic replacement so interrupted builds do not leave
   a corrupt index.

2. **Hybrid retrieval.** Keep structure as the primary index, but rank results
   with a combined signal from BM25/FTS, dense vectors, headings, breadcrumbs,
   summaries, entities, and cross-references. Dense search should include
   section, chunk, and summary embeddings where useful; optional reranking can
   be added behind an explicit provider.

3. **Provider adapter registry.** Keep OpenAI-compatible and local Ollama
   defaults, but make summarizer and embedder providers first-class adapters
   with capability probing, dimension checks, batching metadata,
   retry/backoff/rate-limit handling, and secret-redacted manifest entries.

4. **Richer canonical AST.** Preserve document preambles, front matter
   metadata, tables, code blocks, block quotes, figures, page numbers, and
   parser-specific coordinates as structured blocks. Section nodes remain the
   navigation backbone, but block-level structure should be available to tools
   and future parsers.

5. **Explainable entity and cross-reference quality.** Continue to support
   deterministic offline heuristics, then add optional model-assisted
   extraction and verification for aliases, multilingual entities, textual
   references, and confidence calibration. Tool results should expose why a
   relation was returned.

6. **Benchmark-as-product.** Treat `cairn-bench` as a core product surface:
   multi-document, multilingual, versioned, and publishable. Benchmarks should
   report recall, citation accuracy, tokens returned, latency, index size, and
   reindex cost against naive vector RAG and lexical baselines.

## Consequences

### What we gain

- A clear path from the current alpha skeleton to a trustworthy v0.2 release.
- Better alignment between the end-state architecture and the code milestones.
- Provider flexibility without hard-coding vendor-specific branches into core
  implementations.
- Stronger evidence for the core thesis: structure-aware retrieval should win
  on quality, token efficiency, and auditability.
- More useful issue and PR boundaries for external contributors.

### What we give up

- Some feature breadth moves later. More file formats and UI polish are less
  valuable than proving that the core index is fast, reliable, and measurable.
- The on-disk manifest and index formats become more deliberate earlier, which
  may require migration tooling sooner than planned.
- Hybrid retrieval adds more tuning surface than pure section-level vector
  search, so benchmarks become mandatory rather than optional.

## Alternatives Considered

### Ship more parsers before hardening the index

Rejected for Phase 2. More formats are valuable, but every parser inherits the
same indexing and retrieval constraints. Hardening the index first reduces
rework for PDF, HTML, DOCX, EPUB, and future formats.

### Keep provider support limited to OpenAI-compatible APIs

Rejected. "OpenAI-compatible" is useful as a default, but many real providers
are only partially compatible, especially for embeddings. A provider registry
keeps Cairn local-first and vendor-neutral without accumulating special cases in
one client.

### Defer benchmarks until v1.0

Rejected. Cairn's product claim is comparative: better retrieval and fewer
tokens than naive RAG on structured documents. That claim needs continuous,
public measurement before v1.0, not after.

### Add a general retriever abstraction

Rejected per PRODUCT.md non-goals. Hybrid ranking should stay scoped to
structured documents and Cairn's existing tool contract, not become a generic
RAG framework.

## Open Questions

- Which lexical index should be the default: SQLite FTS, Tantivy, LanceDB
  full-text features, or a lightweight in-process BM25 implementation?
- Should reranking be part of v0.2, or remain an opt-in v0.3 provider?
- What is the minimum stable block-level AST needed before adding more parsers?
- How should benchmark datasets be licensed and hosted so users can reproduce
  headline numbers without large downloads?
- What migration guarantees should Cairn make for pre-v1.0 on-disk indexes?
