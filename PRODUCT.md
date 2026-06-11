# Cairn — Product Definition

> **Status:** Authoritative. Changes to this document require an ADR.
> **Audience:** Maintainers, contributors, and every AI agent assisting development.

---

## 1. Vision

**Cairn turns any large structured document into a navigable map that AI agents
traverse on demand — fetching the right slice at the right granularity, instead
of swallowing the whole thing.**

One sentence. If a change to Cairn doesn't move this vision forward, reject the change.

---

## 2. The Problem We Solve

Modern AI agents struggle with large documents (books, manuals, RFCs, regulations,
multi-hundred-page PRDs, legal contracts, technical specifications). Three failure
modes dominate:

1. **Dump the whole thing in.** Burns tokens, dilutes attention, accuracy degrades
   sharply past ~50k tokens regardless of advertised context windows.
2. **Naive RAG (vector chunking).** Splits structured documents into context-free
   shards. Loses hierarchy. Loses cross-references. Returns the right paragraph
   under the wrong premise.
3. **GraphRAG / heavyweight pipelines.** Expensive to build, opaque to debug,
   over-engineered for documents that already have explicit structure.

The structured-document use case is **underserved** by every category above.

---

## 3. Core Thesis

Five claims. Every design decision must be consistent with all five.

1. **Structure beats vectors for structured documents.** Tables of contents,
   headings, cross-references, and entity mentions encode authorial intent that
   embeddings approximate poorly. Use structure as the primary index; use vectors
   as a supplement, not a substitute.

2. **Progressive disclosure is the right default.** An agent should see the
   outline first, summaries second, and full text only when justified. This
   minimizes tokens, maximizes accuracy, and produces an auditable trail of
   "what the agent chose to look at."

3. **The agent navigates; we provide the map.** Cairn does not answer questions.
   Cairn does not summarize on the fly. Cairn exposes a fixed set of well-typed
   tools and lets the agent decide retrieval strategy.

4. **MCP is the universal interop layer.** Every tool Cairn ships must be
   accessible to any MCP-compatible agent (Claude Code, Cursor, Cline, Goose, …)
   without bespoke integration.

5. **Citations are mandatory.** Every retrieval result carries a stable anchor.
   Agents must cite. Humans must be able to verify in one click.

---

## 4. Audience

### Primary users

- **AI agent authors** building assistants that need to query large structured
  documents (technical documentation, compliance, research, internal wikis).
- **Developer-tool builders** integrating document Q&A into IDEs, chat clients,
  CLI tools.
- **Power users** who want their local AI assistant to actually understand a
  500-page handbook on their disk.

### Explicitly not for

- End-user chatbot consumers expecting a friendly chat UI.
- General-purpose RAG framework users (use LlamaIndex/LangChain).
- Code-repository search (use ripgrep, Sourcegraph, Cursor's @-mentions).

---

## 5. What Cairn Does

At a glance, Cairn:

1. **Ingests** a structured document (Markdown first; PDF, HTML, DOCX later).
2. **Indexes** it into a `BookIndex`-style structure: hierarchical tree of
   sections + multi-granularity summaries + entity index + cross-reference graph
   + a vector overlay.
3. **Exposes** that index through a small set of well-typed MCP tools.
4. **Serves** the index over an MCP server (stdio + SSE).
5. **Persists** everything in a local, file-system-native format that diffs
   cleanly under git.

It is a **library + CLI + MCP server**, in that order of importance.

---

## 6. What Cairn Explicitly Does NOT Do

This list is load-bearing. Future sessions must defer to it.

- **❌ No chatbot UI.** Cairn is agent infrastructure, not an end-user product.
- **❌ No on-the-fly answer generation.** Cairn returns *retrieved structured
  content*, never synthesized prose responses.
- **❌ No general-purpose RAG abstractions.** No `Retriever` interface that tries
  to cover web search, SQL, and document QA in one shape. Cairn is opinionated
  about structured documents.
- **❌ No proprietary embedding service.** All embedding choices must be
  swappable; local-first must always work.
- **❌ No cloud-only features in the open-source core.** A hosted offering may
  exist later — but the OSS core must be fully usable offline.
- **❌ No vendor lock-in for storage.** Index lives on the file system in
  inspectable formats (JSON, SQLite-based vector store).
- **❌ No automatic summarization at query time.** Summaries are pre-computed
  during indexing; queries are cheap and deterministic.
- **❌ No mutation of source documents.** Cairn reads. Cairn never writes back to
  the original document.
- **❌ No "smart" defaults that hide behavior from the agent.** Tools are
  explicit; agents must opt into expansion.
- **❌ No code-repository indexing.** Different problem, different shape; out of
  scope.

If you find yourself proposing one of these, you are proposing the wrong product.
Open a discussion before opening a PR.

---

## 7. Success Criteria

Concrete, measurable, time-bounded. v1.0 ships when **all** of these are true.

### Functional

- [ ] Indexes a 500-page Markdown document (≥ 200k words) in ≤ 5 min on a
      MacBook Pro M-series, using a local embedding model.
- [ ] First-token latency on `outline()` < 50 ms.
- [ ] First-token latency on `get_section()` < 100 ms (warm cache).
- [ ] First-token latency on `search_semantic()` < 300 ms.
- [ ] Index size on disk: ≤ 2× the size of the source document.
- [ ] Re-indexing on document change is incremental (only changed sections
      re-embedded / re-summarized).

### Quality

- [ ] On a curated `cairn-bench` of 5 large documents and 200 questions, Cairn
      achieves ≥ 90% retrieval recall@5 and ≥ 80% LLM-judged QA accuracy with
      GPT-4o-mini / Claude Haiku tier models.
- [ ] On the same bench, Cairn uses ≤ 50% of the retrieved tokens that a naive
      vector RAG baseline uses for comparable accuracy.

### Ecosystem

- [ ] Works out-of-the-box with: Claude Code, Cursor, Cline, Goose.
- [ ] `pip install cairn && cairn index ./doc.md && cairn serve` reaches a
      working MCP endpoint in < 60 seconds on a fresh machine (excluding model
      download).
- [ ] ≥ 1,500 GitHub stars within 6 months of public launch.
- [ ] ≥ 3 unaffiliated production deployments referenced publicly.

### Developer experience

- [ ] All public APIs typed with mypy strict.
- [ ] ≥ 85% test coverage on `src/cairn/`.
- [ ] All ADRs current with the code (CI enforces no stale ADR references).

---

## 8. Competitive Landscape

How Cairn relates to the nearest neighbors. **Not "better than"** — better
positioned for a specific problem.

| System | What it is | Why Cairn is different |
|---|---|---|
| **RAPTOR** (ICLR 2024) | Recursive clustering + summarization tree | RAPTOR clusters chunks; Cairn uses the document's own structure. RAPTOR is research code; Cairn is a shipped tool with MCP. |
| **BookRAG** (Dec 2025) | Hierarchical structure-aware index + entity graph + IFT-inspired agent | Closest theoretical sibling. Cairn implements the BookRAG vision as a real MCP-native, production-grade tool — paper has no public code. |
| **A-RAG** (Feb 2026) | Agentic RAG with keyword/semantic/chunk tools | A-RAG's "hierarchy" is granularity-level (keyword→sentence→chunk), not document-structural. Cairn borrows A-RAG's agent-tool philosophy and replaces its index with a structure-first one. |
| **GraphRAG** (Microsoft) | Entity-extraction → knowledge graph → community summaries | GraphRAG flattens documents into entity graphs; expensive to build, hard to audit. Cairn keeps the document's own structure first-class. |
| **LlamaIndex / LangChain** | General-purpose RAG frameworks | Frameworks; you assemble. Cairn is an opinionated, drop-in product for one specific shape of problem. |
| **NotebookLM** | Consumer document Q&A | Closed-source SaaS, no agent integration. Cairn is local-first and agent-native. |
| **Existing MCP doc servers** (`docs-mcp-server`, `document-mcp`, …) | Vector RAG wrapped in MCP | Most do naive chunking. Cairn's differentiator is structure-awareness + progressive disclosure. |

### Where Cairn must win

- **vs. naive vector RAG**: dramatically better recall and token efficiency on
  structured docs.
- **vs. BookRAG (when official code lands)**: better DX, MCP-native, mature
  tooling, larger community.
- **vs. A-RAG**: better fit for the single-large-document case.
- **vs. NotebookLM**: local-first, agent-native, open.

### Where Cairn does not try to win

- **vs. LlamaIndex** on framework flexibility — we are deliberately rigid.
- **vs. ripgrep** on unstructured text search — different problem.
- **vs. Sourcegraph** on code indexing — different problem.

---

## 9. Naming Rationale

**Cairn** — a small stack of stones marking a trail through difficult terrain
(mountains, deserts, snowfields). Climbers and hikers depend on cairns to
navigate when the path is not obvious.

The metaphor maps cleanly:

- A large document is unfamiliar terrain.
- Cairn builds a system of markers (the hierarchical index, the summaries, the
  cross-reference graph).
- The agent follows the markers to reach the right destination, instead of
  brute-forcing through every step of the terrain.

Pronunciation: */kɛərn/* ("kairn"), one syllable.

---

## 10. Document Governance

- This document is the source of truth for product scope.
- Any contributor or AI session that wants to expand scope must:
  1. Justify the expansion against Section 3 (Thesis) and Section 6 (Non-Goals).
  2. Open an ADR under `docs/decisions/`.
  3. Get sign-off before code is merged.
- If you are an AI agent reading this in a future session: **the non-goals list
  is not a starting point for negotiation**. It is the boundary of the product.

---

*Last reviewed: foundation commit. See `docs/decisions/` for amendments.*
