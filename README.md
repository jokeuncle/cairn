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

> ⚠️ **Pre-alpha — v0.1 walking skeleton.** End-to-end Markdown indexing,
> all five v0.1 retrieval tools, stdio MCP server, and a typer CLI are
> working today. PDF, entity index, and cross-references are scheduled for
> v0.2. See [`ROADMAP.md`](ROADMAP.md).

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

## Quickstart

The fastest way to see Cairn work: index Cairn's own architecture document
and search it. **Zero API keys, zero model downloads** — the `--fake` flag
uses deterministic in-process plugins so the whole thing runs offline.

```bash
git clone https://github.com/cairn-dev/cairn.git
cd cairn

python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 1. Index a document (Cairn's own architecture, ~18k words, 32 sections)
.venv/bin/cairn index ARCHITECTURE.md --out /tmp/cairn-arch --fake
# → indexed: /tmp/cairn-arch/manifest.json   (under one second)

# 2. Get the map — gists only, never full text
.venv/bin/cairn outline /tmp/cairn-arch --depth 2

# 3. Keyword search: every section that mentions "LanceDB"
.venv/bin/cairn query keyword /tmp/cairn-arch LanceDB

# 4. Multi-term keyword search with mode=all
.venv/bin/cairn query keyword /tmp/cairn-arch progressive disclosure --mode all
# → top hit: "3.3 Progressive-disclosure contract"

# 5. Start the MCP stdio server for Claude Code / Cursor / Cline / Goose
.venv/bin/cairn serve /tmp/cairn-arch --fake
```

A walkthrough with full output and an MCP-client config snippet is in
[`examples/hero-demo.md`](examples/hero-demo.md).

### Real LLM + real embeddings

The `--fake` plugins are great for offline reproducibility but they have no
semantic understanding. For production indexing, point Cairn at any
OpenAI-compatible endpoint. The defaults target a **local Ollama** so you
keep the local-first promise without paying for API tokens:

```bash
ollama serve
ollama pull llama3.2:3b
ollama pull nomic-embed-text

.venv/bin/cairn index ARCHITECTURE.md --out /tmp/cairn-arch   # no --fake
```

OpenAI, vLLM, Together, Anyscale, …all of them work the same way; override
`CAIRN_LLM_*` and `CAIRN_EMBED_*` environment variables.

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

| Phase | Status | What |
|---|---|---|
| 0 — Foundation | ☑ | Authoritative docs in place (PRODUCT, ARCHITECTURE, CLAUDE, ROADMAP, ADR-0001) |
| 1 — v0.1 walking skeleton | ☑ | Markdown ingest, Tree + Summaries + Vectors indexes, 5 MCP tools, stdio server, CLI, hero demo |
| 2 — v0.2 structure-aware retrieval | ☐ | Entities (`find_mentions`), Cross-references (`get_related`), digest summaries, PDF, incremental rebuild, benchmark |
| 3 — v0.3 federation & inspection | ☐ | Multi-doc, HTML/mkdocs, web inspector, OpenTelemetry |
| 4 — v0.4 polish for production | ☐ | DOCX/RTF/EPUB, VSCode extension, security review |
| v1.0 GA | ☐ | All `PRODUCT.md` §7 success criteria met |

Full plan: [`ROADMAP.md`](ROADMAP.md). Current test suite: **234 passing**,
mypy strict clean, ruff clean.

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
