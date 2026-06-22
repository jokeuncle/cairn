# Cairn — Technical Architecture

> **Status:** Authoritative. Changes require an ADR under `docs/decisions/`.
> **Audience:** Engineers and AI agents implementing Cairn.

This document describes the **end-state** architecture (v1.0). Phased rollout is
described in `ROADMAP.md`. When implementing, build *toward* this shape — never
build something that would have to be torn down to reach it.

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          External agents                                │
│   (Claude Code, Cursor, Cline, Goose, custom MCP clients, ...)          │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ MCP (stdio | SSE)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 4: MCP Server  (src/cairn/mcp/)                                  │
│   • stdio + SSE transports        • per-document namespacing            │
│   • tool dispatch + validation    • hot-reload on index changes         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ Internal Python API
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 3: Retrieval Tools  (src/cairn/tools/)                           │
│   outline · get_section · search_semantic · search_keyword              │
│   find_mentions · get_related · expand · read_range                     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ Query primitives
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 2: Index  (src/cairn/index/)                                     │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│   │  Tree T  │  │ Summaries│  │ Entities │  │  XRefs   │  │ Vectors  │ │
│   │  (TOC)   │  │   (S)    │  │   (E)    │  │   (X)    │  │   (V)    │ │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ Builders (idempotent, incremental)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 1: Ingestion  (src/cairn/ingest/)                                │
│   Parsers (Markdown · PDF · HTML · DOCX) → canonical Document AST       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ Source files
                                 ▼
                          ┌──────────────┐
                          │ Source docs  │
                          └──────────────┘

  Cross-cutting:  src/cairn/cli/      (typer-based CLI)
                  src/cairn/plugins/  (parsers, embedders, summarizers, stores)
                  src/cairn/core/     (config, types, errors, logging)
```

Read this top-down for runtime flow, bottom-up for build flow.

---

## 2. Layered Architecture

### Invariants across all layers

1. **Layer N may depend on Layer N−1 only.** No upward dependencies.
2. **All cross-layer contracts are typed.** Use `pydantic` models, not dicts.
3. **Every layer is independently testable.** No layer requires a running MCP
   server, an LLM key, or an embedding model to run its own unit tests.
4. **Every layer is independently swappable.** Plug-in interfaces sit at every
   boundary; concrete implementations live in `src/cairn/plugins/`.

---

### Layer 1: Ingestion

**Responsibility:** Convert any source format into a canonical `Document` AST.

**Inputs:** A file path (local) or a stream.
**Outputs:** A `Document` object — see Section 4.

**Plug-in interface:** `Parser`

```python
class Parser(Protocol):
    name: str                     # e.g. "markdown", "pdf"
    extensions: tuple[str, ...]   # e.g. (".md", ".markdown")

    def parse(self, source: Path | bytes) -> Document: ...
```

**v0.1 implementations:** Markdown (CommonMark + extensions: front-matter, footnotes, tables).
**v0.2:** PDF (via `marker` or `pymupdf` — see ADR-0003 when written).
**v0.3:** HTML, mkdocs/docusaurus sites.
**v0.4:** DOCX, RTF, EPUB.

**Hard rules:**
- Parsers MUST preserve heading hierarchy.
- Parsers MUST emit stable section IDs derived from heading paths (slug-based),
  not from positional indices.
- Parsers MUST NOT lose source byte offsets — every node carries `(start, end)`
  spans into the original file.

---

### Layer 2: Index

**Responsibility:** Build, persist, and query the multi-layered `BookIndex`.

The index is the heart of Cairn. It is composed of five sub-indexes, each
independently built and queried:

#### 2.1 Tree (T) — Structural backbone

A rooted tree of `SectionNode` objects mirroring the document's heading
hierarchy. Each node has:

- `id` (stable, slug-based, hierarchical: e.g. `intro/getting-started/install`)
- `title`
- `level` (heading depth, 1-based)
- `parent`, `children`
- `span` (byte offsets into source)
- `raw_text` (the section body, excluding sub-section bodies)
- `path` (full breadcrumb)

The tree is the **primary navigation structure**. Every other sub-index keys
into it.

#### 2.2 Summaries (S) — Multi-granularity views

For each `SectionNode`, three pre-computed summaries:

- `gist` — one-line, ≤ 20 words. The "scent" in IFT terms.
- `synopsis` — one paragraph, ≤ 80 words.
- `digest` — multi-paragraph, ≤ 300 words, structurally faithful.

Generated by a pluggable `Summarizer` during indexing. **Never generated at
query time.**

```python
class Summarizer(Protocol):
    def summarize(self, node: SectionNode, level: SummaryLevel) -> str: ...
```

#### 2.3 Entities (E) — Term and concept index

Reverse index from entities → list of section IDs where they appear.

Entity types (initial):
- `term` — glossary terms (from explicit glossary sections + LLM extraction)
- `code` — code symbols (functions, classes, identifiers in code blocks)
- `proper` — capitalized noun phrases, deduplicated by canonical form
- `defined` — entities introduced by definition patterns ("X is …", "**X**")

```python
class Entity(BaseModel):
    canonical: str
    surface_forms: list[str]
    kind: Literal["term", "code", "proper", "defined"]
    mentions: list[Mention]  # section_id + span
```

#### 2.4 Cross-references (X) — Document graph

Directed edges between section nodes derived from:
- Explicit internal links (`[…](#anchor)`, `[[wiki-link]]`)
- Heading references ("see § 3.2", "Chapter 4 introduced …") — detected via
  regex + LLM verification
- Entity-mediated edges (sections that share defined entities)

```python
class XRef(BaseModel):
    src: str               # section_id
    dst: str               # section_id
    kind: Literal["link", "textual", "entity"]
    confidence: float
    span: tuple[int, int]  # source location of the reference
```

#### 2.5 Vectors (V) — Semantic overlay

Dense embeddings per section + per chunk (chunks are sub-section units of
~512 tokens for long sections, aligned to sentence boundaries).

Stored in a local vector store (LanceDB default; sqlite-vec optional).

**Vectors are a supplement, not the primary index.** Cairn never falls back to
"just do a vector search" when structural retrieval is possible.

```python
class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

```python
class VectorStore(Protocol):
    def upsert(self, items: list[VectorItem]) -> None: ...
    def query(self, vec: list[float], k: int, filter: dict | None) -> list[Hit]: ...
    def delete(self, ids: list[str]) -> None: ...
```

#### 2.6 Builder pipeline

```
Document AST
    │
    ├── TreeBuilder         → tree.json
    ├── SummaryBuilder      → summaries.json
    ├── EntityBuilder       → entities.json
    ├── XRefBuilder         → refs.json
    └── VectorBuilder       → vectors.db
                                │
                                ▼
                          manifest.json
```

**Hard rules:**
- Each builder is independently runnable and re-runnable (idempotent).
- Builders MUST support **incremental rebuilds**: if only Section 3.2 changed,
  only its descendants are re-summarized / re-embedded.
- Build state is durable — partial builds can be resumed.
- A `manifest.json` records source file hashes, builder versions, model
  identifiers, and build timestamps for every artifact.

---

### Layer 3: Retrieval Tools

**Responsibility:** Expose well-typed query primitives that compose into agent
workflows.

This is the **public API** an agent sees. Tools are deliberately few, sharply
typed, and progressive: each one returns the minimum useful information and
points to ways to drill deeper.

#### 3.1 Tool catalog

| Tool | Purpose | Returns |
|---|---|---|
| `outline` | Get the map of the document. | Truncated tree with titles + gists |
| `get_section` | Read a specific section. | Section content (raw_text + metadata) |
| `expand` | Progressively zoom in. | Section at requested summary level |
| `search_semantic` | Semantic search. | Ranked sections + chunks with anchors |
| `search_keyword` | Exact lexical search. | Ranked hits with anchors |
| `find_mentions` | Locate all occurrences of an entity. | List of section IDs + spans |
| `get_related` | Graph navigation from a section. | Neighbors via xrefs / siblings / parent |
| `read_range` | Continuous read across sections. | Concatenated content |

Every tool result includes:
- `cursor`: opaque continuation token for paginated drilling
- `anchors`: stable section IDs that can be passed to other tools
- `tokens_returned`: explicit cost report (so the agent can budget)

#### 3.2 Detailed schemas

See `docs/specs/mcp-tools.md` for the canonical OpenAPI-style schema. The
binding to MCP is generated from there; do not handwrite MCP schemas elsewhere.

#### 3.3 Progressive-disclosure contract

By default, tools return summaries before bodies. Specifically:

- `outline()` returns gists, never full text.
- `search_*()` returns synopsis + first 200 chars of raw_text by default;
  full text only when explicitly requested.
- `get_section(id)` defaults to `level="synopsis"`; the agent passes
  `level="full"` to opt into the raw text.

This is **non-negotiable**. It is the single biggest reason Cairn delivers
better token economics than naive RAG. Removing this default for "convenience"
is a regression.

---

### Layer 4: MCP Server

**Responsibility:** Speak the Model Context Protocol so any compliant agent can
use Cairn.

- Transports: stdio (default), Streamable HTTP / SSE (optional).
- Tool registration: 1-to-1 mapping from Layer 3 tools. No "convenience" wrappers.
- Resource exposure: documents are exposed as MCP resources keyed by
  `cairn://<doc-id>/<section-id>`.
- Lifecycle: server watches `.cairn/` for index changes and hot-reloads
  affected document namespaces.

Multi-document mode: one server can host many indexed documents. Each is its
own namespace; all tools accept an optional `doc` parameter that defaults to a
configured primary when omitted.

**Hard rules:**
- MCP server MUST validate every incoming tool call against the typed schema
  and reject with a structured error on mismatch — never silently coerce.
- MCP server MUST emit JSON-line logs of every tool invocation: tool name,
  inputs, latency, tokens_returned, success/error. This is the audit trail.

---

### Layer 5: Tooling (CLI / inspector / extensions)

CLI (`docsgraph`, typer-based; `cairn` remains a compatibility alias):

```
docsgraph init                  # scaffold a .cairn/ in cwd
docsgraph index <path>          # index a document
docsgraph serve [--http]        # start MCP server
docsgraph inspect <doc-id>      # print index stats
docsgraph outline <doc-id>      # print tree
docsgraph query <doc-id> ...    # exercise tools from terminal
docsgraph migrate               # bump index format versions
```

Future (v0.3+):
- `docsgraph web` — local inspector UI (read-only).
- VSCode extension surfacing the same inspector.

---

## 3. Plug-in Architecture

Five plug-in points. Each is a `Protocol`. Concrete implementations live in
`src/cairn/plugins/`. Selection is config-driven via `.cairn/config.toml`.

| Plug-in | Default | Alternates |
|---|---|---|
| `Parser` | markdown | pdf (v0.2), html (v0.3), docx (v0.4) |
| `Summarizer` | OpenAI-compatible LLM client | Ollama, Anthropic, local llama.cpp |
| `Embedder` | `sentence-transformers/all-MiniLM-L6-v2` | Qwen3-Embedding-0.6B, OpenAI |
| `EntityExtractor` | regex + LLM | spaCy, gliner |
| `VectorStore` | LanceDB | sqlite-vec, in-memory |

**Hard rule:** A user must be able to run Cairn end-to-end **with zero proprietary
API keys**, using only local models. If a default ever requires an API key,
that's a release-blocking bug.

---

## 4. Data Model

Canonical Python types. Source of truth: `src/cairn/core/types.py`.

```python
class Span(BaseModel):
    start: int  # byte offset
    end: int    # byte offset

class SectionNode(BaseModel):
    id: str                       # stable, slug-based, hierarchical
    title: str
    level: int                    # heading depth, 1-based
    parent: str | None
    children: list[str]
    span: Span
    path: list[str]               # breadcrumb of titles
    raw_text: str                 # body excluding child sections

class SummarySet(BaseModel):
    section_id: str
    gist: str
    synopsis: str
    digest: str
    model: str                    # which model produced these
    generated_at: datetime

class Mention(BaseModel):
    section_id: str
    span: Span

class Entity(BaseModel):
    canonical: str
    surface_forms: list[str]
    kind: Literal["term", "code", "proper", "defined"]
    mentions: list[Mention]

class XRef(BaseModel):
    src: str
    dst: str
    kind: Literal["link", "textual", "entity"]
    confidence: float
    span: Span

class Document(BaseModel):
    id: str                       # human-readable, slug-based
    source_path: Path
    source_hash: str              # sha256 of source
    sections: list[SectionNode]
    indexed_at: datetime
    cairn_version: str
```

---

## 5. Storage Layout

Everything Cairn persists lives in `.cairn/` under the working directory.
Inspectable. Diffable. Git-friendly.

```
.cairn/
├── config.toml                  # plug-in selection, embedding model, LLM endpoint
├── documents/
│   └── <doc-id>/
│       ├── manifest.json        # source hash, builder versions, model IDs
│       ├── tree.json            # SectionNode[]
│       ├── summaries.json       # SummarySet[]
│       ├── entities.json        # Entity[]
│       ├── refs.json            # XRef[]
│       ├── vectors.lance/       # LanceDB directory
│       └── raw/
│           └── source.<ext>     # copy of original (canonicalized)
└── cache/
    ├── llm/                     # cached LLM completions for summary stability
    └── embeddings/              # cached embeddings for reproducibility
```

**Hard rules:**
- JSON files use stable key ordering and consistent indentation so they diff cleanly.
- `manifest.json` is the contract — any file referenced there must exist; any
  file present but unreferenced is treated as orphan and reaped.
- Vector store directories are .gitignored by default; everything else is
  git-trackable.

---

## 6. MCP Tool Reference (summary)

Full schemas in `docs/specs/mcp-tools.md`. Below is the contract sketch.

```
outline(doc?: str, depth?: int = 2, focus?: str | null = null,
        include: list["gist"|"synopsis"] = ["gist"]) -> Outline

get_section(id: str, doc?: str,
            level: "gist"|"synopsis"|"digest"|"full" = "synopsis") -> Section

expand(id: str, doc?: str,
       to: "synopsis"|"digest"|"full") -> Section

search_semantic(query: str, doc?: str, scope?: str | null = null,
                k: int = 8, return_: "sections"|"chunks" = "sections") -> Results

search_keyword(terms: list[str], doc?: str, scope?: str | null = null,
               k: int = 12) -> Results

find_mentions(entity: str, doc?: str, scope?: str | null = null,
              kind?: list[EntityKind] = None) -> list[Mention]

get_related(id: str, doc?: str,
            kinds: list["xref"|"sibling"|"parent"|"child"] = ["xref"],
            k: int = 8) -> list[Neighbor]

read_range(start_id: str, end_id: str, doc?: str,
           max_tokens: int = 4000) -> RangeResult
```

Notes:
- `scope` is a section ID prefix that restricts the search subtree. This is how
  agents narrow their foraging.
- All search results include `tokens_returned` for budget accounting.
- All section IDs are addressable as MCP resources via `cairn://<doc>/<id>`.

---

## 7. Tech Stack and Rationale

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | RAG ecosystem, MCP SDK, ML libraries |
| Type system | mypy strict + pydantic v2 | Public surfaces must be tightly typed |
| CLI | typer | First-class type-driven CLIs |
| MCP | official `mcp` Python SDK | Don't roll our own |
| Embeddings | `sentence-transformers` default | Local-first, no API key required |
| Vector store | LanceDB | Embedded, columnar, no separate server, file-system-native |
| Summarization | OpenAI-compatible HTTP | Works with Ollama, vLLM, OpenAI, Anthropic, Together, … |
| Parsing (md) | `markdown-it-py` + `mdit-py-plugins` | CommonMark-strict, well-maintained |
| Parsing (pdf) | `pymupdf` baseline, `marker` for high-fidelity (v0.2) | TBD per ADR |
| Testing | pytest + hypothesis | Property-based for parsers/builders |
| Lint/format | ruff | Speed |
| Build | hatchling | Standard, lightweight |
| Packaging | uv-friendly | Modern Python workflow |

**Anti-stack** (do not introduce without an ADR):
- No FastAPI/Flask in the core. The MCP server is the server.
- No Celery/Redis. Builders are in-process; concurrency via `asyncio` + `anyio`.
- No Django ORM, no SQLAlchemy. Pydantic + sqlite (raw) where SQL is needed.
- No PyTorch in the core path. Embeddings via `sentence-transformers` which can
  use CPU-friendly backends; no GPU requirement for v1.0.

---

## 8. Non-Functional Requirements

### Performance budgets (see PRODUCT.md §7 for v1.0 targets)

- Indexing throughput: ≥ 50k tokens/second on M-series CPU with default model.
- Query p95 latencies bound per tool (PRODUCT.md §7).
- Memory: index loading is lazy; resident set ≤ 500 MB for a 200k-word document.

### Reliability

- Index is durable: partial builds can resume.
- A corrupted artifact is detected (manifest hash mismatch) and triggers a
  precise re-build of just that artifact.
- The MCP server never returns 500 to an agent — errors are structured tool
  results with `error` fields, so the agent can plan around them.

### Security

- **Local-first by design.** No data leaves the machine unless the user
  configures a remote LLM/embedding endpoint.
- **No code execution** from indexed content under any circumstance.
- **Path traversal**: all source paths normalized; refuse to index outside the
  workspace without `--allow-outside`.
- **Secrets**: LLM API keys read only from env vars or a designated `.env`,
  never from `.cairn/`.

### Observability

- Structured JSON logs (line-delimited) for every tool call.
- `cairn inspect` reports index health, last build times, model IDs, anomalies.
- Optional OpenTelemetry tracing (opt-in via config; no telemetry by default).

### Reproducibility

- Index manifests include builder versions, model IDs, embedding model
  fingerprints. Re-running indexing on identical inputs with identical config
  produces identical artifacts modulo timestamps.

---

## 9. Extensibility Boundaries

Things that **must** be extensible:

- Parsers (new source formats).
- Summarizers (new LLM endpoints).
- Embedders (new models, including no-op for testing).
- Vector stores (LanceDB → sqlite-vec → cloud, if a user really needs it).
- Entity extractors.

Things that **must not** be configurable:

- The five-sub-index shape (T/S/E/X/V). Adding new sub-indexes requires an ADR.
- The progressive-disclosure default behavior.
- The MCP tool catalog (additions need an ADR; removals are breaking changes).
- The data model in Section 4 (changes are breaking; bump index format version
  and provide migration).

---

## 10. Threat / Failure Model

| Risk | Mitigation |
|---|---|
| Summarizer hallucination → bad gists | Cache + versioning, allow human overrides via sidecar files |
| Vector store corruption | Detected by manifest check, full rebuild of just vectors.lance |
| Embedding model drift between versions | Fingerprint stored in manifest; mismatch triggers rebuild |
| LLM API key leakage | Keys never persisted, never logged |
| Adversarial source document with millions of tiny sections | Hard caps on tree depth/breadth (configurable, errors when exceeded) |
| Agents over-fetching | `tokens_returned` in every response; soft budget warnings |

---

## 11. End-State vs. Phased Rollout

This document describes v1.0. The phased build is in `ROADMAP.md`. Phase
boundaries respect this architecture: every milestone ships a coherent slice of
the end-state, never a parallel design that has to be replaced.

If a phase plan ever conflicts with this architecture, update the architecture
(via ADR) — do not silently diverge.

---

*Last reviewed: foundation commit.*
