# Cairn MCP Tool Specification

> **Status:** Authoritative. This document is the single source of truth for the
> public tool surface. Code generation, MCP server schemas, and contract tests
> all derive from here. Changes require an ADR.

This is **v0.1-frozen for the included tools**; tools listed but marked
`v0.2+` are designed but not yet implemented.

---

## 0. Conventions

### Identifiers

- `doc_id`: human-readable, slug-based. Example: `"react-docs"`.
- `section_id`: hierarchical, slug-based, `/`-separated. Stable across
  re-indexing of the same document. Example: `"hooks/use-effect/cleanup"`.
- Anchor URI (for MCP resource references): `cairn://<doc_id>/<section_id>`.

### Tokens and budgets

Every tool result includes `tokens_returned: int` so an agent can budget its
context. The count is for the **textual content** in the response (excluding
JSON envelope and `trace`). It is an estimate using the indexing-time tokenizer;
agents should treat it as accurate to within ±10%.

### Trace

Every MCP tool result includes a top-level `trace` object so AI clients and
humans can inspect what Cairn did for the call without relying on transport
logs. The MCP server also declares a generic output schema for the envelope so
clients that support structured tool results can render this trace separately
from the textual JSON fallback.

Common trace shape:

```json
{
  "server": "cairn",
  "tool": "repo_context",
  "mode": "repo" | "document" | "repo_document",
  "status": "ok" | "error",
  "arguments": { ... normalized MCP arguments ... },
  "steps": [
    {"name": "search_documents", "status": "ok", "hits": 3},
    {"name": "return_result", "status": "ok", "tokens_returned": 920}
  ]
}
```

Tool-specific examples below may elide `trace` for readability; the real MCP
response includes it.

### Errors

Tools never raise to the MCP transport. They return a structured envelope:

```json
{
  "ok": false,
  "error": {
    "code": "NOT_FOUND" | "INVALID_INPUT" | "INDEX_STALE" | "INTERNAL",
    "message": "human-readable",
    "details": { ... }
  },
  "trace": { ... }
}
```

Successful responses:

```json
{
  "ok": true,
  "tokens_returned": 412,
  "data": { ... tool-specific payload ... },
  "trace": { ... }
}
```

### Pagination / continuation

Tools that may return more than fits in a single response include `cursor` in
the result. Passing it back as `cursor` in the next call resumes from where the
previous call stopped.

### Common parameters

All tools accept these optional parameters:

| Param | Type | Default | Description |
|---|---|---|---|
| `doc` | `string` | server primary | Document namespace (`doc_id`). Required only when the server hosts multiple documents and no primary is configured. |

In single-document mode (`cairn serve <doc-dir>`), clients should omit `doc`.
In repository mode (`cairn serve` from a repo initialized with `cairn init -y`),
clients should call `list_documents` first, use `search_documents` for global
repo discovery, then pass `doc` to route normal retrieval tools to a specific
indexed document.

### Repository-only tool: `list_documents`

`list_documents` is advertised only by repo-scoped MCP servers.

Inputs:

| Param | Type | Default | Description |
|---|---|---|---|
| `state` | `"indexed"\|"stale"\|"missing"\|"error"\|"orphaned"\|null` | `null` | Optional state filter. |

Output:

```json
{
  "ok": true,
  "tokens_returned": 0,
  "data": {
    "root": "/repo",
    "primary_doc": "readme",
    "documents": [
      {
        "id": "architecture",
        "source": "ARCHITECTURE.md",
        "doc_dir": ".cairn/documents/architecture",
        "state": "indexed",
        "section_count": 32
      }
    ]
  }
}
```

### Repository-only tool: `search_documents`

`search_documents` is advertised only by repo-scoped MCP servers. It searches
every indexed repository document and returns globally ranked section hits with
their `doc` ids so clients can immediately drill down with normal tools.

Inputs:

| Param | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | required | Conceptual query to search across indexed repo docs. |
| `k` | `int` (1–32) | `8` | Number of globally ranked section hits to return. |
| `sections_per_doc` | `int \| null` (1–8) | `.cairn/config.toml search_sections_per_doc` (`1` by default) | Maximum section hits per document. Omit it for the repository default; override it per query when you need either wider document discovery or deeper hits from one doc. |
| `include` | `list["synopsis"\|"head"\|"evidence"]` | `["synopsis", "head", "evidence"]` | Fields to attach to each hit. |

Output:

```json
{
  "ok": true,
  "tokens_returned": 920,
  "data": {
    "query": "how do plugin tools work?",
    "hits": [
      {
        "doc": "docs-specs-mcp-tools",
        "source": "docs/specs/mcp-tools.md",
        "id": "repository-only-tool-search-documents",
        "title": "Repository-only tool: search_documents",
        "score": 0.86,
        "vector_score": 0.71,
        "lexical_score": 0.94,
        "sparse_score": 0.63,
        "graph_score": 0.18,
        "anchor": "cairn://docs-specs-mcp-tools/repository-only-tool-search-documents",
        "explanation": {
          "dominant_signal": "lexical",
          "matched_terms": ["plugin", "tools", "work"],
          "signals": {
            "vector": {"score": 0.71, "weight": 0.22},
            "lexical": {"score": 0.94, "weight": 0.5},
            "sparse": {"score": 0.63, "weight": 0.28},
            "graph": {"score": 0.18, "weight": 0.1}
          },
          "rank_factor": 1.0,
          "identity_bonus": 0.0,
          "notes": [
            "matched query terms in doc/source/title/summary/body fields",
            "BM25-style sparse evidence contributed"
          ]
        },
        "synopsis": "Repo-scoped MCP servers expose a cross-document search tool...",
        "evidence": {
          "text": "search_documents is advertised only by repo-scoped MCP servers...",
          "matched_terms": ["search", "documents"],
          "span": {"start": 0, "end": 123}
        }
      }
    ],
    "sections_per_doc": 1,
    "searched_documents": 12,
    "ranker": {
      "mode": "full",
      "total_sections": 140,
      "compatible_sections": 140,
      "scored_sections": 140
    },
    "stale_documents": [],
    "skipped_documents": [],
    "cursor": null
  }
}
```

Semantics:

- The query embedding is computed once, then searched against each indexed
  document's vector overlay.
- Hits use hybrid ranking: vector similarity, BM25-style sparse evidence,
  structure-aware field support, weighted query-term coverage, path/title
  identity, and local graph-neighborhood propagation. The ranker is generic:
  it does not special-case repository names, document ids, or benchmark
  answers.
- Large repositories use a two-stage scoring path. Cairn always computes dense
  scores in batch, then combines dense seeds, cheap lexical/path seeds, and
  graph neighbors into a wide shortlist before running the full BM25/graph
  explanation ranker. Small repositories stay in `full` mode. The `ranker`
  object reports `mode`, `total_sections`, `compatible_sections`, and
  `scored_sections` for observability.
- Every hit includes raw signal scores plus an `explanation` object with the
  dominant signal, matched query terms, configured signal weights, rank
  adjustments, and short notes. This makes repo search debuggable by agents,
  CLI users, and benchmark reports.
- By default, results use `.cairn/config.toml search_sections_per_doc` (`1`
  in the generated config) so agents can find the right document before
  drilling down. Set `sections_per_doc > 1` per call, or raise the config
  value, for deeper per-document recall.
- Hits include `doc`, `source`, and section `id` for follow-up calls such as
  `get_section(doc=..., id=...)`.
- `stale_documents` lists indexed documents whose source file fingerprint no
  longer matches the last synced fingerprint. Search still returns the existing
  index for continuity, but clients should run `cairn sync` before relying on it
  for final answers.
- Documents with incompatible embedding dimensions or load errors are reported
  in `skipped_documents` instead of failing the whole call.

---

### Repository-only tool: `repo_context`

`repo_context` is a composite retrieval tool for agents that need a ready-to-read
context pack rather than a list of hits. It runs repo search, attaches compact
section content, adds local relationships, and returns a small relationship map.

Inputs:

| Param | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | required | Conceptual query to search across indexed repo docs. |
| `k` | `int` (1-32) | `5` | Number of ranked hits to include. |
| `sections_per_doc` | `int \| null` (1-8) | repo config | Diversity override passed through to `search_documents`. |
| `related_k` | `int` (0-12) | `3` | Related sections to attach per selected hit. |
| `level` | `"gist"\|"synopsis"\|"full"` | `"synopsis"` | Content granularity for `context_sections`. |
| `max_section_chars` | `int` (200-8000) | `1600` | Hard character cap per selected section. |

Output shape:

```json
{
  "ok": true,
  "data": {
    "query": "where are tools configured?",
    "hits": [{"doc": "docs-tools", "id": "tools/configuration"}],
    "context_sections": [
      {
        "rank": 1,
        "doc": "docs-tools",
        "id": "tools/configuration",
        "level": "synopsis",
        "content": "Tools are configured...",
        "hit": {"score": 0.91, "explanation": {"dominant_signal": "lexical"}},
        "relationships": [
          {"id": "tools/install", "kind": "parent", "confidence": 1.0}
        ]
      }
    ],
    "relationship_map": {"nodes": [], "edges": []},
    "stale_documents": [],
    "skipped_documents": [],
    "codegraph_bridge": {
      "status": "not_invoked",
      "note": "Cairn does not parse source code..."
    }
  }
}
```

Semantics:

- This is the preferred one-call context builder for MCP clients.
- It propagates `stale_documents` and `skipped_documents` from
  `search_documents`.
- The relationship map covers documentation nodes only. For source-code symbols,
  callers/callees, and code impact, pair the result with the CodeGraph MCP server.

---

### Repository-only tool: `repo_graph`

`repo_graph` returns a bounded documentation relationship map. It is useful for
inspectors, debugging ranker behavior, and giving agents a structured view of
docs before they drill into exact sections.

Inputs:

| Param | Type | Default | Description |
|---|---|---|---|
| `doc` | `string \| null` | `null` | Optional document id to restrict the graph. |
| `max_sections` | `int` (1-500) | `120` | Maximum section nodes to include. |
| `max_entities` | `int` (0-200) | `40` | Maximum entity nodes to include. |
| `include_entities` | `boolean` | `true` | Include entity nodes and mention edges. |
| `include_xrefs` | `boolean` | `true` | Include xref edges when available. |

Output nodes use stable ids such as `doc:readme`,
`section:readme:introduction`, and `entity:code:runcontext`. Edge kinds include
`contains`, `xref`, and `mentions`.

Semantics:

- `repo_graph` is a documentation graph, not a source-code graph. Structural and
  xref edges are document-local today; cross-document connectivity is represented
  through shared entity nodes and `mentions` edges.
- The response includes `codegraph_bridge.status = "external"` to make that
  boundary explicit.

---

### Repository-only tool: `repo_impact`

`repo_impact` estimates documentation surfaces affected by a document or section
change. It reports derived artifacts, MCP surfaces, nearby sections, and related
documents connected by shared entities.

Inputs:

| Param | Type | Default | Description |
|---|---|---|---|
| `doc` | `string` | required | Repository document id. |
| `id` | `string \| null` | `null` | Optional section id. Omit for document-level impact. |
| `max_results` | `int` (1-100) | `24` | Maximum impacted sections/documents to return. |

Semantics:

- Document-level impact names generated artifacts such as `.cairn/manifest.json`,
  per-document tree/summaries/vectors/entities/xrefs, inspectors, and repo tools.
- Section-level impact includes parent/child/xref/shared-entity neighbors when
  present.
- This is docs graph impact. Use CodeGraph for source-code symbol impact.

---

## 1. `outline`

Get the document's structural map. The cheapest tool. Agents should call this
first when working with an unfamiliar document.

### Inputs

| Param | Type | Default | Description |
|---|---|---|---|
| `depth` | `int` (1–6) | `2` | Maximum heading level to include. |
| `focus` | `string` (section_id) \| `null` | `null` | If set, restrict to this section and its descendants. |
| `include` | `list["gist"\|"synopsis"]` | `["gist"]` | Which summary levels to attach to each node. |

### Output

```json
{
  "ok": true,
  "tokens_returned": 380,
  "data": {
    "doc": "react-docs",
    "depth": 2,
    "focus": null,
    "tree": [
      {
        "id": "intro",
        "title": "Introduction",
        "level": 1,
        "gist": "Why React, and what this document covers.",
        "children": [
          {
            "id": "intro/quickstart",
            "title": "Quickstart",
            "level": 2,
            "gist": "Five-minute install + first component.",
            "children": []
          }
        ]
      }
    ]
  }
}
```

### Semantics

- Returns a **forest** keyed by top-level sections.
- Never returns full body text. Truncating `gist` to the configured limit
  (≤ 20 words) is the responsibility of the indexer.
- Children deeper than `depth` are omitted; the truncated nodes are signaled
  with a `truncated: true` flag and not enumerated.

---

## 2. `get_section`

Fetch a specific section at a chosen summary level. The agent's main "drill in"
primitive.

### Inputs

| Param | Type | Default | Description |
|---|---|---|---|
| `id` | `string` (section_id) | required | Section to fetch. |
| `level` | `"gist"\|"synopsis"\|"digest"\|"full"` | `"synopsis"` | Granularity. `full` returns `raw_text`. |
| `include_children` | `bool` | `false` | If true, recursively include child sections at the same level. |

### Output

```json
{
  "ok": true,
  "tokens_returned": 220,
  "data": {
    "doc": "react-docs",
    "id": "hooks/use-effect",
    "title": "useEffect",
    "level": "synopsis",
    "content": "useEffect lets you synchronize a component with an external system...",
    "anchor": "cairn://react-docs/hooks/use-effect",
    "path": ["Hooks", "useEffect"],
    "has_children": true,
    "next_levels_available": ["digest", "full"]
  }
}
```

### Semantics

- Default `level="synopsis"` is **progressive disclosure**. Never change this
  default in any client SDK.
- `full` returns the `raw_text` of just this section (no descendant bodies).
  Use `read_range` for continuous reads.
- `level="full"` for a section with no body returns an empty string and
  `tokens_returned: 0` — not an error.

---

## 3. `expand`

Move from one summary level to a deeper one for a section already in the
agent's working set. A specialization of `get_section` optimized for the common
"I saw the synopsis, give me the digest" path.

### Inputs

| Param | Type | Default | Description |
|---|---|---|---|
| `id` | `string` (section_id) | required | Section to expand. |
| `to` | `"synopsis"\|"digest"\|"full"` | required | Target level. Must be strictly deeper than the previously delivered level (server does not track this; agent is responsible). |

### Output

Same shape as `get_section`.

### Semantics

- Behaves exactly as `get_section(id, level=to)`. Kept as a separate tool to
  encourage the progressive idiom in agent prompts.

---

## 4. `search_semantic`

Dense-vector retrieval. Use when the agent wants conceptually related content
but doesn't have an exact phrase.

### Inputs

| Param | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | required | The query text. |
| `scope` | `string` (section_id prefix) \| `null` | `null` | Restrict search to this section's subtree. |
| `k` | `int` (1–32) | `8` | Number of results to return. |
| `return_` | `"sections"\|"chunks"` | `"sections"` | Granularity of results. `chunks` only available in v0.2+. |
| `include` | `list["synopsis"\|"head"\|"evidence"]` | `["synopsis", "head", "evidence"]` | What to attach to each hit. `head` = first 200 chars of raw_text. `evidence` = a short lexical window explaining the hit. |
| `cursor` | `string` \| `null` | `null` | Pagination cursor. |

### Output

```json
{
  "ok": true,
  "tokens_returned": 920,
  "data": {
    "query": "how to fetch data on mount",
    "scope": null,
    "hits": [
      {
        "id": "hooks/use-effect/data-fetching",
        "title": "Data fetching with useEffect",
        "score": 0.87,
        "anchor": "cairn://react-docs/hooks/use-effect/data-fetching",
        "synopsis": "Use useEffect to load data when a component mounts...",
        "head": "useEffect can run side effects after render. A common pattern...",
        "evidence": {
          "text": "...data fetching can be implemented inside an Effect...",
          "matched_terms": ["data", "fetching"],
          "span": {"start": 142, "end": 502}
        }
      }
    ],
    "cursor": null
  }
}
```

### Semantics

- Scores are cosine similarity, normalized to [0, 1]. Comparable within a
  single query but not across queries.
- `evidence` is explanatory, not a ranking input. It is generated after vector
  search from the section's raw text so humans and agents can inspect why a
  hit may be relevant.
- Hits are **deduplicated by section** when `return_="sections"`: at most one
  hit per section, even if multiple chunks matched.
- `scope` is a prefix match on `section_id`. `scope="hooks"` matches
  `hooks/use-effect/...` but not `hooks-recipes/...`.

---

## 5. `search_keyword`

Exact lexical search. Use for named entities, code symbols, technical terms
where wording is known.

### Inputs

| Param | Type | Default | Description |
|---|---|---|---|
| `terms` | `list[string]` | required | One or more terms (1–8). Matching is case-insensitive; phrases supported. |
| `scope` | `string` (section_id prefix) \| `null` | `null` | Restrict to subtree. |
| `k` | `int` (1–32) | `12` | Number of results to return. |
| `mode` | `"any"\|"all"` | `"any"` | Whether a hit must contain any or all terms. |

### Output

```json
{
  "ok": true,
  "tokens_returned": 540,
  "data": {
    "terms": ["useEffect", "cleanup"],
    "mode": "any",
    "hits": [
      {
        "id": "hooks/use-effect/cleanup",
        "title": "Cleanup functions",
        "score": 18.5,
        "anchor": "cairn://react-docs/hooks/use-effect/cleanup",
        "matches": [
          {"term": "useEffect", "count": 6},
          {"term": "cleanup",   "count": 11}
        ],
        "head": "When you return a function from useEffect..."
      }
    ]
  }
}
```

### Semantics

- Score formula: `Σ count(term, section) × |term|`. Higher is better. Not
  comparable across queries.
- No stemming, no fuzzy matching. This is **deliberate**: agents should pick
  `search_semantic` when they want fuzziness.

---

## 6. `find_mentions` *(v0.2+)*

Locate every place an entity appears.

### Inputs

| Param | Type | Default | Description |
|---|---|---|---|
| `entity` | `string` | required | Canonical name or any registered surface form. |
| `scope` | `string` (section_id prefix) \| `null` | `null` | Restrict to subtree. |
| `kinds` | `list["term"\|"code"\|"proper"\|"defined"]` \| `null` | `null` | Filter by entity kind. |

### Output

```json
{
  "ok": true,
  "tokens_returned": 240,
  "data": {
    "entity": "useEffect",
    "canonical": "useEffect",
    "kind": "code",
    "mentions": [
      {
        "section_id": "hooks/use-effect",
        "title": "useEffect",
        "anchor": "cairn://react-docs/hooks/use-effect",
        "span": [12450, 12459]
      }
    ]
  }
}
```

### Semantics

- Returns at most 64 mentions per call; further reads via `cursor`.
- Resolution: if `entity` matches a registered surface form, the index returns
  mentions of the canonical entity.

---

## 7. `get_related` *(v0.2+)*

Graph navigation from a section.

### Inputs

| Param | Type | Default | Description |
|---|---|---|---|
| `id` | `string` (section_id) | required | Anchor section. |
| `kinds` | `list["xref"\|"sibling"\|"parent"\|"child"]` | `["xref"]` | Relation types to traverse. |
| `k` | `int` (1–32) | `8` | Max neighbors returned. |

### Output

```json
{
  "ok": true,
  "tokens_returned": 310,
  "data": {
    "id": "hooks/use-effect",
    "neighbors": [
      {
        "id": "hooks/use-effect/cleanup",
        "title": "Cleanup functions",
        "kind": "child",
        "relation": null,
        "anchor": "cairn://react-docs/hooks/use-effect/cleanup",
        "gist": "Return a function from useEffect to clean up."
      },
      {
        "id": "hooks/use-layout-effect",
        "title": "useLayoutEffect",
        "kind": "xref",
        "relation": "entity",
        "confidence": 0.72,
        "anchor": "cairn://react-docs/hooks/use-layout-effect",
        "gist": "Synchronous version of useEffect."
      }
    ]
  }
}
```

### Semantics

- `kind` describes how the neighbor is related (`xref` from the graph,
  `sibling`/`parent`/`child` from the tree).
- For `kind="xref"`, `relation` is one of `"link" | "textual" | "entity"`.
- Sorted by confidence descending for xrefs; tree order otherwise.

---

## 8. `read_range` *(v0.2+)*

Continuous read across sibling sections. For when an agent has identified a
target region and wants the full text.

### Inputs

| Param | Type | Default | Description |
|---|---|---|---|
| `start_id` | `string` | required | First section to include. |
| `end_id` | `string` | required | Last section to include (inclusive). |
| `max_tokens` | `int` | `4000` | Hard cap on returned content. |

### Output

```json
{
  "ok": true,
  "tokens_returned": 3850,
  "data": {
    "start_id": "hooks/use-effect",
    "end_id": "hooks/use-effect/cleanup",
    "content": "## useEffect\n\nuseEffect lets you...\n\n### Cleanup functions\n\n...",
    "anchor_start": "cairn://react-docs/hooks/use-effect",
    "anchor_end":   "cairn://react-docs/hooks/use-effect/cleanup",
    "truncated": false,
    "next_id": null
  }
}
```

### Semantics

- `start_id` and `end_id` must be in document order; otherwise `INVALID_INPUT`.
- When truncated, `next_id` is the first section that wasn't included; passing
  it as the new `start_id` continues the read.

---

## 9. Future tools (sketched, not specified)

These are placeholders to reserve names. They require their own ADR before
being added to the catalog.

- `summarize_subtree` — explicit aggregation of summaries across a subtree.
- `diff_index` — surface changed sections between two index versions.
- `define` — resolve an entity to its definition section.

---

## 10. Versioning

This spec is versioned alongside the package:

- `v0.1`: tools 1–5 implemented and frozen for the v0.1 line.
- `v0.2`: adds tools 6–8.
- Breaking changes to the schemas require a new major version of the spec and
  a deprecation cycle for clients.

The schema version is advertised in the MCP server's initialization response
under `serverInfo.metadata.cairn.spec_version`.
