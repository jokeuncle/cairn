# Cairn

> **Cairns for your largest documents. Agents navigate by markers, not chunks.**

[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)](ROADMAP.md)
[![MCP](https://img.shields.io/badge/MCP-native-7c3aed.svg)](https://modelcontextprotocol.io/)

Cairn is a **structure-aware, MCP-native retrieval system** for large structured
documents. Instead of shredding your 500-page handbook into context-free vector
chunks, Cairn builds a *navigable map* — hierarchical tree, multi-granularity
summaries, entity index, cross-reference graph — and exposes it as a small,
well-typed set of MCP tools that any AI agent can traverse on demand.

The result: dramatically higher retrieval accuracy and lower token spend on
structured documents, compared to naive RAG. Local-first. Vendor-neutral.
Built to be the layer between your documents and every AI agent you'll use over
the next decade.

> ⚠️ **Pre-alpha.** Foundation docs in place; first code (`v0.1`) lands soon.
> See [`ROADMAP.md`](ROADMAP.md).

---

## Why Cairn?

| Today | With Cairn |
|---|---|
| Dump the whole document into context. Burns tokens, dilutes attention. | Agent fetches only what it needs, at the granularity it needs. |
| Naive RAG splits structure into context-free chunks. | The document's own structure is the index. |
| Cross-references and entities are lost in chunking. | They are first-class objects. |
| Locked into one vendor's embeddings / vector DB. | Pluggable everything. Local-first defaults. |
| Different tool stacks for Claude / Cursor / Cline / Goose. | One MCP server. Any compliant agent works. |

For the in-depth motivation, see [`PRODUCT.md`](PRODUCT.md).
For the technical design, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## How It Works (90 seconds)

1. **Ingest.** Cairn parses your document into a canonical AST preserving
   headings, anchors, and source spans.
2. **Index.** Cairn builds five sub-indexes — a structural tree (T), multi-level
   summaries (S), an entity index (E), a cross-reference graph (X), and a
   vector overlay (V).
3. **Serve.** Cairn exposes a small MCP tool catalog: `outline`, `get_section`,
   `expand`, `search_semantic`, `search_keyword`, `find_mentions`,
   `get_related`, `read_range`.
4. **Navigate.** Your agent calls `outline()` first, drills into the sections
   that look promising, and only fetches full text when justified. Every result
   carries stable anchors for one-click verification.

A visual explainer comparing Cairn's approach to RAPTOR, BookRAG, and A-RAG
lives at [`docs/canvas.html`](docs/canvas.html). Open it in any browser.

---

## Quickstart *(coming with v0.1)*

```bash
# Install
pip install cairn

# Index a document
cairn index ./my-large-doc.md

# Start the MCP server (stdio)
cairn serve

# Point Claude Code / Cursor / Cline at it — done.
```

Worked example with the React docs is planned for the v0.1 launch demo. See
[`ROADMAP.md`](ROADMAP.md) for the current milestone.

---

## Inspiration and Lineage

Cairn synthesizes two strands of recent research and ships them as a real,
agent-ready tool:

- **[BookRAG](https://arxiv.org/abs/2512.03413)** (Dec 2025): structure-aware
  index combining a hierarchical tree with an entity graph, queried via an
  Information-Foraging-Theory-inspired agent. Cairn implements this vision in
  production-grade form.
- **[A-RAG](https://arxiv.org/abs/2602.03442)** (Feb 2026): clean agent loop
  with hierarchical retrieval tools (keyword/semantic/chunk). Cairn borrows the
  agent-tool philosophy and replaces A-RAG's chunk-based index with a
  structure-first one.
- **[RAPTOR](https://arxiv.org/abs/2401.18059)** (ICLR 2024): the seminal
  recursive-summarization tree. Cairn's summary layer takes inspiration from it
  while anchoring summaries to the document's own structure instead of
  clustered chunks.

We are deeply grateful to these authors; see ADRs for the specific design
choices we adopted, modified, or declined.

---

## Status & Roadmap

We're at **Phase 0 — Foundation**. Authoritative documents are in place.
v0.1 (the Markdown walking skeleton) lands next.

Full plan: [`ROADMAP.md`](ROADMAP.md).

---

## Contributing

Cairn is opinionated. Before opening a PR, please read:

1. [`PRODUCT.md`](PRODUCT.md) — especially the non-goals.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — the end-state design we're building toward.
3. [`CONTRIBUTING.md`](CONTRIBUTING.md) — workflow and PR expectations.
4. [`docs/decisions/`](docs/decisions/) — existing ADRs.

If you're an AI agent helping a contributor, you'll find your session anchor in
[`CLAUDE.md`](CLAUDE.md).

---

## License

Apache 2.0. See [`LICENSE`](LICENSE).

---

*A cairn is a small stack of stones marking a trail through difficult terrain.
This project is one for AI agents lost in large documents.*
