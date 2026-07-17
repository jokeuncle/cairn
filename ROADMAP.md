# Cairn — Roadmap

> **Status:** Living document. Phase scope changes require an ADR.

This roadmap stages the v1.0 architecture into shippable milestones. Every
phase is a coherent slice of the end-state described in `ARCHITECTURE.md`. We
do **not** build throwaway scaffolding to be replaced later.

Legend: ☐ not started · ◐ in progress · ☑ done.

---

## Phase 0 — Foundation (current)

Goal: lock the design so every contributor and every AI session aligns.

- ☑ Name and license
- ☑ PRODUCT.md, ARCHITECTURE.md, CLAUDE.md, ROADMAP.md
- ☑ First ADR (foundation decisions)
- ☑ Project skeleton (pyproject, gitignore, src/tests layout)
- ☐ MCP tool schema document (`docs/specs/mcp-tools.md`) — written before any
  tool is implemented

**Exit:** all four authoritative docs reviewable; CLAUDE.md cited by a future
session and observed to prevent a scope-violating change.

---

## Phase 1 — v0.1 "Markdown Walking Skeleton"

Goal: end-to-end Markdown → BookIndex → MCP server → working tool calls from
Claude Code. Single document, single user, single machine. **No PDF, no entity
graph, no cross-refs yet.**

### In scope

- **Ingestion**
  - ☐ Markdown parser → `Document` AST with stable section IDs and source spans
- **Index — minimum viable subset**
  - ☐ Tree (T): full hierarchical SectionNode model
  - ☐ Summaries (S): gist + synopsis (digest deferred to v0.2)
  - ☐ Vectors (V): section-level only (chunk-level deferred); LanceDB store
- **Retrieval tools** (subset)
  - ☐ `outline`
  - ☐ `get_section`
  - ☐ `expand`
  - ☐ `search_semantic`
  - ☐ `search_keyword`
- **MCP server**
  - ☐ stdio transport only
  - ☐ Single-document mode
  - ☐ JSON-lines audit log
- **CLI**
  - ☐ `docsgraph init`, `docsgraph index`, `docsgraph serve`,
    `docsgraph outline`, `docsgraph query`
- **Plug-ins**
  - ☐ Default Summarizer: OpenAI-compatible HTTP (works with Ollama)
  - ☐ Default Embedder: `sentence-transformers/all-MiniLM-L6-v2`
  - ☐ Default Store: LanceDB
- **Docs**
  - ☐ Quickstart in README
  - ☐ Worked example: indexing the React docs (or similar hero doc)
  - ☐ One short demo video / GIF

### Out of scope (explicit deferrals)

- Entity index, cross-references, `find_mentions`, `get_related`, `read_range`
- PDF / HTML / DOCX parsers
- SSE/Streamable HTTP MCP transport
- Multi-document mode
- Web inspector

### Quality bars

- `pip install docsgraph && docsgraph index ./README.md && docsgraph serve` works on a
  fresh machine in under 60 seconds (model download excluded).
- `mypy --strict src/cairn/` clean.
- ≥ 80% test coverage on new code.
- One worked demo recorded.

### Exit criteria

- [ ] Claude Code calls all five tools end-to-end against a real Markdown doc.
- [ ] Indexing 100k words finishes in < 3 min on M-series CPU.
- [ ] `outline` p95 < 50 ms; `search_semantic` p95 < 300 ms.
- [ ] Demo video published.
- [ ] ADR for every plug-in default decision.

**Estimated effort:** 3–4 weeks of focused work.

---

## Phase 2 — v0.2 "Structure-Aware Retrieval"

Goal: deliver the full structural advantage over naive RAG. Adds entity index,
cross-references, and the navigation tools that depend on them. **This is the
release that proves the thesis.**

ADR-0002 adds an explicit production-readiness bar for this phase: the release
should prove that Cairn can index, update, retrieve from, and measure realistic
large documents without falling back to naive chunk-RAG behavior.

### In scope

- **Index additions**
  - ☐ Section-level incremental rebuild with per-section fingerprints,
    per-builder state, resumable writes, and atomic artifact replacement
  - ☐ Entity index (E): glossary + heuristic extraction + optional
    model-assisted extraction + canonicalization
  - ☐ Cross-reference graph (X): explicit links, textual refs, entity-mediated
    edges, and optional model-assisted verification
  - ☐ Summaries: add `digest` level
  - ☐ Vectors: chunk-level (sentence-aligned ~512 tokens), plus section and
    summary embeddings where they improve ranking
- **Retrieval quality**
  - ☐ Hybrid ranking across structure, BM25/FTS, dense vectors, headings,
    breadcrumbs, summaries, entities, and cross-references
  - ☐ Result snippets and spans for keyword/lexical hits
  - ☐ Optional reranker provider behind an explicit configuration flag
- **Retrieval tools** (full v1.0 catalog)
  - ☐ `find_mentions`
  - ☐ `get_related`
  - ☐ `read_range`
- **MCP server**
  - ☐ SSE / Streamable HTTP transport
- **CLI**
  - ☐ `cairn inspect` reports index health
  - ☐ `cairn doctor` validates provider configuration, endpoint reachability,
    embedding dimensions, and local-first defaults
  - ☐ Incremental rebuild (`cairn index` detects unchanged sections and reports
    which sub-indexes were touched)
- **Plug-ins**
  - ☐ Provider adapter registry for summarizers and embedders
  - ☐ Capability probing for batching, dimensions, rate limits, retry behavior,
    and redacted manifest metadata
- **Parsers**
  - ☐ PDF (via `pymupdf` baseline; `marker` opt-in)
  - ☐ Canonical AST preserves preambles, front matter metadata, tables, code
    blocks, block quotes, figures, page numbers, and parser coordinates where
    available
- **Benchmarks**
  - ☐ `cairn-bench` v0: 5 curated documents, 200 questions
  - ☐ Published comparison vs. naive vector RAG
  - ☐ Report recall, citation accuracy, tokens returned, latency, index size,
    and reindex cost across at least one multilingual document set

### Exit criteria

- [ ] On `cairn-bench`, ≥ 90% retrieval recall@5, ≥ 80% LLM-judged QA accuracy.
- [ ] Token usage ≤ 50% of naive vector RAG baseline for comparable accuracy.
- [ ] Incremental rebuild on a 1-section change touches only that subtree.
- [ ] Provider diagnostics catch misconfigured embedding dimensions and
      unsupported endpoints before indexing begins.
- [ ] First external contributor PR merged.

**Estimated effort:** 4–6 weeks after v0.1.

---

## Phase 3 — v0.3 "Federation and Inspection"

Goal: multi-document, multi-format, human-inspectable.

### In scope

- ☑ Multi-document namespacing in MCP server
- ☑ Repo-scoped discovery/sync/status and shareable `.cairn/config.toml`
- ☑ Repo tools: `list_documents`, `search_documents`, `repo_context`,
  `repo_graph`, `repo_impact`, plus normal tools routed by optional `doc`
- ☑ Public repo eval/smoke scripts with strict release-gate thresholds
- ☑ Public golden documentation standard for repo authors and ranker tuning
- ☐ HTML / mkdocs / docusaurus site parser
- ☐ Web inspector (`cairn web`): read-only, browse index, see what agents
  retrieved, replay sessions
- ☐ OpenTelemetry tracing (opt-in)
- ☐ Index format migration (`cairn migrate`)

### Exit criteria

- [ ] A team can host 10+ documents on one Cairn server.
- [ ] Web inspector shows the audit trail of a Claude Code session against a
  real document.
- [ ] No regressions in benchmarks.

---

## Phase 4 — v0.4 "Polish for Production"

Goal: reach v1.0-readiness.

### In scope

- ☐ DOCX, RTF, EPUB parsers
- ☐ VSCode extension surfacing the inspector
- ☐ Configurable RBAC for hosted multi-tenant scenarios (optional plug-in)
- ☐ Performance pass: profile + meet all v1.0 latency/memory targets
- ☐ Security review

### Exit criteria

- [ ] All v1.0 performance, quality, and ecosystem targets in `PRODUCT.md` §7
      met or exceeded.
- [ ] Third-party security review concluded.

---

## v1.0 — General Availability

Goal: the v1.0 contract in `PRODUCT.md` §7 holds in production.

- [ ] All success criteria in `PRODUCT.md` §7 satisfied.
- [ ] ≥ 3 unaffiliated production deployments referenced publicly.
- [ ] Stable API contract committed: no breaking changes in v1.x without a
      deprecation cycle.

---

## Beyond v1.0 (sketches, not commitments)

- Hosted offering (optional commercial layer, OSS-core preserved)
- Multi-modal sections (figures, tables, equations as first-class nodes)
- Cross-document entity resolution
- Plugin marketplace
- Differential indexing for streaming documents

---

## How to Propose a Change to This Roadmap

1. Open an ADR explaining the motivation and which milestone is affected.
2. Update this file in the same PR.
3. Get sign-off from a maintainer before merging.

**Do not** quietly add scope to an in-flight phase. Phase boundaries are
contracts.
