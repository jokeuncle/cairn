# ADR-0001: Foundation Decisions

- **Status:** Accepted
- **Date:** 2026-06-11
- **Deciders:** Founding maintainer
- **Related:** PRODUCT.md, ARCHITECTURE.md, CLAUDE.md, ROADMAP.md

## Context

We are founding a new open-source project to address a specific, currently
under-served problem: agents (Claude Code, Cursor, Cline, etc.) cannot
effectively use large structured documents because:

- Whole-document dump-into-context burns tokens and degrades accuracy.
- Naive RAG (vector chunking) loses the structure that makes a document
  navigable.
- GraphRAG-style heavy pipelines over-engineer the case of documents that
  already have structure.

Recent research — RAPTOR (ICLR 2024), BookRAG (Dec 2025), and A-RAG (Feb 2026)
— points toward the right approach: structure-aware hierarchical retrieval with
progressive disclosure, exposed as agent tools. But:

- BookRAG (closest in spirit) has no public implementation.
- A-RAG has clean tooling but its "hierarchy" is granularity-level, not
  document-structural; it targets multi-hop QA corpora, not the
  single-large-document case.
- Both miss the universal interop layer that is now coalescing: the Model
  Context Protocol (MCP).

We are founding this project to fill that gap.

## Decision

We will build Cairn:

1. **Name:** `cairn` (CLI and package). A cairn is a stone marker on a hiking
   trail. The metaphor maps directly to building navigation markers through
   large documents.

2. **Language:** Python 3.11+. The RAG ecosystem, MCP SDK, and ML tooling are
   all Python-first. Performance hot paths are not language-bound; structure is.

3. **License:** Apache 2.0. OSS-friendly, patent-grant clear, compatible with
   enterprise adoption.

4. **Thesis (load-bearing):** Structure beats vectors for structured documents.
   Vectors are a supplement, not a substitute. Progressive disclosure is the
   default. The agent navigates; Cairn provides the map.

5. **Surface:** A library, a CLI, and an MCP server — in that order of
   importance. No chatbot UI. No SaaS in the OSS core. No general-purpose RAG
   abstractions.

6. **Plug-in shape:** Five plug-in interfaces (Parser, Summarizer, Embedder,
   EntityExtractor, VectorStore). Local-first defaults. End-to-end must work
   with no proprietary API keys.

7. **Storage:** File-system-native under `.cairn/`. JSON for structural
   artifacts; LanceDB for vectors. Inspectable. Diffable. Git-friendly.

8. **Governance:** Authoritative documents are `PRODUCT.md`, `ARCHITECTURE.md`,
   `CLAUDE.md`, `ROADMAP.md`. Changes to scope, architecture, MCP tool catalog,
   or on-disk formats require ADRs.

9. **AI-assisted development:** `CLAUDE.md` is the session anchor for AI
   contributors. Future sessions defer to the inviolable principles there.

## Consequences

### What we gain

- A coherent, opinionated product that's easy to explain and hard to drift.
- A defensible niche: the structure-aware, MCP-native, single-document case.
- Lineage to credible academic work (BookRAG, A-RAG, RAPTOR) for trust and
  discoverability.
- Local-first defaults that broaden the addressable user base (no API keys
  required).

### What we give up

- Generality. Cairn is not a RAG framework; users wanting multi-source
  retrieval will reach for LlamaIndex/LangChain.
- A chat UI. Adoption depends on agents being our distribution surface — which
  is a bet on MCP's continued momentum.
- Cloud-default convenience. Users who want a SaaS will not be served by the
  OSS core (though we may layer one later).

### Risks

- **BookRAG official code lands and outcompetes us.** Mitigation: ship the
  MCP-native + DX story fast; the paper covers algorithm, not product.
- **A-RAG authors add MCP support.** Mitigation: our differentiator is
  single-document structural retrieval, not multi-hop QA — different shape.
- **GraphRAG ecosystem absorbs the niche.** Mitigation: avoid the entity-graph
  framing as the headline; lead with structure-and-navigation.

## Alternatives Considered

### Build a Notion/Linear-style PRD-management web app

Rejected: red ocean, slow to traction, requires UX investment we don't want to
make. The "PRD-as-Code" insight that started this conversation is preserved as
a *downstream* use case Cairn enables — but the platform is generic
document-navigation, not PRD-management specifically.

### Wrap an existing OSS MCP doc server (e.g., docs-mcp-server) with better
prompts

Rejected: those servers are vector-RAG-shaped. The thesis here is that vectors
are the wrong primary index for structured documents. A wrapper would not
deliver the differentiation.

### Fork A-RAG and add structural parsing

Considered seriously. Rejected because A-RAG's data model is corpus-of-chunks,
not document-tree; the refactor would be invasive enough that a clean
implementation is faster and clearer to reason about. We adopt A-RAG's
agent-tool philosophy as inspiration, not its code.

### Implement BookRAG verbatim from the paper

Considered. Rejected as the only path because (a) the paper does not specify a
production-grade engineering shape, (b) it does not address MCP integration,
and (c) parts of the index (entity graph) can be deferred without
sacrificing the headline win. Cairn implements the BookRAG *vision* but with
phased, shipped engineering — see `ROADMAP.md`.

### Use TypeScript / Rust

Rejected for v1.0. Python keeps us in the same ecosystem as our target users'
existing tools (LlamaIndex, Hugging Face, MCP Python SDK). A Rust core for
hot paths is plausible post-v1.0 — but not a foundation-time decision.

## Open Questions

- Should the default LLM endpoint be Ollama or a generic OpenAI-compatible URL?
  → To be decided in the v0.1 plug-in defaults ADR.
- LanceDB vs. sqlite-vec as the default vector store?
  → To be decided after Phase 1 prototyping; both are file-system-native.
- Hosted/commercial layer: timing and shape?
  → Not before v1.0. Captured in `ROADMAP.md` as a sketch only.
