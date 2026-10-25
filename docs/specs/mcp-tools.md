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

Every tool result includes `tokens_returned: int`, a rough whitespace-based
estimate of textual payload content. It excludes JSON envelope/keys and `trace`,
and can undercount code, identifiers and non-English text. It is neither an
exact tokenizer count nor a hard context cap. Use actual model usage or the
model's tokenizer for complete-response and whole-session cost comparisons.

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

### Server instructions

The MCP server declares an `instructions` string (MCP `initialize` result) that
clients may inject into the model's system prompt. It is the only server-level
place to shape *when* an agent reaches for Cairn rather than grepping raw text,
and is therefore part of the public surface (changes require an ADR — see
ADR-0002). Two variants are served:

- **Document mode** (`docsgraph serve <doc-dir>`): directs the agent to start
  with `outline`, locate via `search_semantic`/`search_keyword`, then read with
  `get_section` at an explicit level, citing stable section ids.
- **Repository mode** (`docsgraph serve` in a repo): directs the agent to call
  Cairn before reading raw README/docs/spec files for documentation questions,
  to start with `repo_context` or `search_documents`, to follow structured setup
  `next_steps` when the repo is not initialized or synced, and explicitly states
  that Cairn does **not** replace source-code search. Repository indexes are
  isolated per `.cairn/config.toml`; `projectPath` switches to another repo only
  when explicitly provided.

The instruction text lives beside the server in `src/cairn/mcp/server.py`
(`DOCUMENT_INSTRUCTIONS`, `REPO_INSTRUCTIONS`). Per-tool `description` strings
are intent-first ("Use when …") for the same reason: tool selection is driven by
intent-to-description matching.

Section reads explicitly state that the body excludes descendants. Bounded
`navigation` metadata lists up to eight direct children and eight siblings with
stable citations, total counts and an `outline` call for the complete map.
These are optional navigation choices, not an exhaustive reading checklist.
Root sections share an implicit document parent for sibling navigation. The
section token estimate includes these metadata strings (ADR-0005).

Compact `repo_context` selects source-supported candidates using query-wide
BM25 evidence and marginal query-term coverage. Semantic/hybrid ranking remains
the fallback when lexical evidence is absent; document-discovery ranking and
diagnostic context remain unchanged (ADR-0006). Fitting fenced examples remain
whole within the configured excerpt budget. `evidence.truncated_code=true`
explicitly marks an oversized partial example that needs a full section read.

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

Recoverable repo setup errors include `error.details.next_steps`, an ordered
array of `{command, reason}` objects. Missing config starts with
`docsgraph init -y`; missing or unusable document indexes start with
`docsgraph sync`. When the discovered document surface is suspiciously narrow,
`error.details.config_guidance` may also suggest `.cairn/config.toml` include
and exclude edits.

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

### Repository-mode common parameters

Repository-scoped MCP tools accept these optional parameters:

| Param | Type | Default | Description |
|---|---|---|---|
| `doc` | `string` | server primary | Document namespace (`doc_id`). Used by document retrieval tools in repo mode. Required only when the server hosts multiple documents and no primary is configured. |
| `projectPath` | `string` | current MCP workspace | Path to a different repo containing `.cairn/config.toml`. Repos are isolated; omit for normal current-workspace use and provide only for explicit cross-repo queries. |

In single-document mode (`docsgraph serve <doc-dir>`), clients should omit `doc`.
In repository mode, `docsgraph serve` resolves the current MCP workspace from
the client's `rootUri` / `workspaceFolders` / `roots/list` signal, then walks up
to the nearest `.cairn/config.toml`. If no config is found, the call returns an
`INVALID_CONFIG` envelope with setup `next_steps` rather than falling back to
another repo. Clients should use repo tools before raw file reads for
documentation, product, architecture, setup, naming, protocol, business
workflow, and decision-record questions. For source-code symbol tracing,
known-file edits, test output, build logs, and exact literal search, clients
should prefer CodeGraph, shell, or native project tools. For documentation tasks,
call `repo_context` for ready-to-read context, call `search_documents` for
ranked discovery, or call `list_documents` to inspect the indexed surface,
freshness, usage guidance, and config guidance before routing normal retrieval
tools to a specific indexed document.

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
  "tokens_returned": 96,
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
    ],
    "usage_guidance": {
      "prefer_cairn_for": [
        "repository documentation, product requirements, architecture, setup, naming, protocols, business workflows, and durable decision records"
      ],
      "prefer_other_tools_for": [
        "source-code symbol lookup, callers/callees, and code impact analysis"
      ],
      "recommended_flow": [
        "Use repo_context first for conceptual documentation or project-knowledge questions."
      ]
    }
  }
}
```

When no indexed/stale documents are available, `data.next_steps` tells clients
to run `docsgraph sync` and inspect `docsgraph status`. When the document
surface looks too narrow, for example only a README is known, optional
`data.config_guidance` suggests `.cairn/config.toml` `include` examples such as
`guides/**/*.md`, `specs/**/*.md`, and `decisions/**/*.md`, plus `exclude`
examples such as `node_modules/**`, `dist/**`, `build/**`, and `coverage/**`.

### Repository-only tool: `search_documents`

MCP responses return cited source hits and requested text fields by default.
Set `include_details=true` for scores, explanations and ranker bookkeeping.
Candidate ranking and source evidence are identical between views. The Python
library search API remains detailed and does not take this MCP-only flag.

`search_documents` is advertised only by repo-scoped MCP servers. It searches
every indexed repository document and returns globally ranked section hits with
their `doc` ids so clients can immediately drill down with normal tools.

Inputs:

| Param | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | required | Conceptual query to search across indexed repo docs. |
| `include_details` | `bool` | `false` | MCP-only: include ranking diagnostics and the legacy detailed envelope data. |
| `k` | `int` (1–32) | `8` | Number of globally ranked section hits to return. |
| `sections_per_doc` | `int \| null` (1–8) | `.cairn/config.toml search_sections_per_doc` (`1` by default) | Maximum section hits per document. Omit it for the repository default; override it per query when you need either wider document discovery or deeper hits from one doc. |
| `include` | `list["synopsis"\|"head"\|"evidence"]` | `["synopsis", "head", "evidence"]` | Fields to attach to each hit. |

Detailed output (`include_details=true`):

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
- With `include_details=true`, every hit includes raw signal scores plus an `explanation` object with the
  dominant signal, matched query terms, configured signal weights, rank
  adjustments, and short notes. This makes repo search debuggable by agents,
  CLI users, and benchmark reports.
- By default, results use `.cairn/config.toml search_sections_per_doc` (`1`
  in the generated config) so agents can find the right document before
  drilling down. Set `sections_per_doc > 1` per call, or raise the config
  value, for deeper per-document recall.
- Hits include `doc`, `source`, and section `id` for follow-up calls such as
  `get_section(doc=..., id=...)`.
- If no indexed/stale documents are searchable, the tool returns a `NOT_FOUND`
  envelope with setup `next_steps` instead of a successful empty `hits` list.
- `stale_documents` lists indexed documents whose source file fingerprint no
  longer matches the last synced fingerprint. Search still returns the existing
  index for continuity, but clients should run `docsgraph sync` before relying
  on it for final answers.
- Documents with incompatible embedding dimensions or load errors are reported
  in `skipped_documents` instead of failing the whole call.
- When query/index embedding dimensions differ, `embedding_mismatch` is a
  structured object with `query_dim`, `index_dims`, and affected `documents`.
  This usually means the MCP server was started with different `CAIRN_EMBED_*`
  settings than the process that ran `docsgraph sync`.

---

Section identifiers in MCP inputs (`id`, `start_id`, `end_id`, `focus`, `scope`)
also accept returned `cairn://doc/section` citation URIs. In repository mode the
URI selects the indexed document when `doc` is omitted. Explicit `doc` values,
multiple URI inputs, and document-scoped servers must agree on the document
namespace; conflicting or malformed anchors return a tool error. Plain section
IDs remain supported.

### Repository-only tool: `repo_context`

Repository `search_documents` and `repo_context` also accept
`retrieval="hybrid" | "lexical"` (default hybrid; ADR-0013). Lexical mode reuses
cached BM25/field/structure scoring without query embeddings or vector entries.
It still needs an existing index, may miss semantic matches, reports its mode
and retains stale/skipped signals. No automatic semantic fallback is performed.
The [read-only CLI](../cli-retrieval.md) exposes the same handlers; MCP transport
and existing default views remain unchanged.

`repo_context` is a composite retrieval tool for agents that need a ready-to-read
context pack rather than a list of hits. By default each cited section appears
once, with a precomputed summary and bounded verbatim evidence. Diagnostic
ranking information and expanded relationships are opt-in (ADR-0004).

Request `level="full"` to combine discovery and reading original section bodies.
Each full section reports `content_scope="section_body_only"`,
`source_characters` (Unicode characters before the cap), and `truncated`.
Descendant bodies are separate even if `truncated=false`. Complete bodies can
be reused directly; expand truncated content or unmet requirements rather than
automatically re-reading every source. The existing 200-8000 character cap
still applies. This does not certify that all task requirements are covered
(ADR-0011).

Experimental `level="evidence"` (ADR-0012) returns `evidence_blocks` instead of
`content`: whole original Markdown blocks, fitting examples and neighboring prose,
each with a section-relative Unicode-character span. Recognizable CLI help is
split by options while retaining usage/group context; arbitrary code is atomic.
`omitted_content` is explicit. Ancestor and descendant bodies are separate, and
the tool does not certify that all task requirements are covered.

`max_context_chars` (1000-32000, default 8000) bounds the total original-source
characters in this evidence view; `max_section_chars` also applies per section.
Metadata is excluded, so this is not an exact model-token budget. Sections that
could not contribute fitting blocks are listed in `sections_without_blocks`.
Request full text for missing conditions or oversized examples. The evidence
view requires `include_details=false`; non-default global budgets with other
levels fail explicitly. Existing default summary views remain unchanged.

For multiple information needs, evidence mode also accepts `queries` (1-8
nonempty strings, each at most 1000 characters). The agent supplies focused
queries; Cairn performs no automatic decomposition. Candidate hits are fused,
deduplicated and jointly packed under one budget, with at most `k` returned
sections and the document cap. Later queries may depend on evidence already
read. Non-evidence views reject this argument. `sections_without_blocks` supplies
bounded recovery anchors if no whole block can be returned; otherwise unselected
candidate sections are counted, rather than emitted as a navigation checklist.

Inputs:

| Param | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | required | Conceptual query to search across indexed repo docs. |
| `k` | `int` (1-32) | `5` | Number of ranked hits to include. |
| `sections_per_doc` | `int \| null` (1-8) | `null` | Compact context permits up to three sections per document; explicit values override. Diagnostic mode retains repo-config document diversity. |
| `related_k` | `int` (0-12) | `3` | Related sections per hit when `include_details=true`. |
| `level` | `"gist"\|"synopsis"\|"full"` | `"synopsis"` | Content granularity for `context_sections`. |
| `max_section_chars` | `int` (200-8000) | `1600` | Hard character cap per selected section. |
| `include_details` | `bool` | `false` | Return the previous diagnostic shape, including full hits and expanded relationships. |

Output shape:

```json
{
  "ok": true,
  "data": {
    "query": "where are tools configured?",
    "context_sections": [
      {
        "doc": "docs-tools",
        "source": "docs/tools.md",
        "id": "tools/configuration",
        "title": "Configuration",
        "anchor": "cairn://docs-tools/tools/configuration",
        "level": "synopsis",
        "content": "Tools are configured...",
        "evidence": {"text": "An original excerpt...", "matched_terms": [], "span": {"start": 0, "end": 22}}
      }
    ],
    "next_step": "Verify exact values with get_section(doc,id,level='full'). For missing parts use get_related/outline; excerpts are not exhaustive."
  }
}
```

Semantics:

- This is the preferred one-call context builder for documentation and
  project-knowledge questions.
- It propagates `stale_documents` and `skipped_documents` from
  `search_documents` when nonempty, and propagates embedding mismatch recovery.
- `level="full"` explicitly requests original text, capped at `max_section_chars`.
- Evidence spans are character offsets into the stripped section body, not byte
  offsets into the original file. The cited section provides the source boundary.
- Compact evidence budgets prioritize the first ranked hit (up to 1,600
  characters) and bound remaining excerpts to 400 characters each, all capped
  by `max_section_chars`. A short excerpt is not proof that a topic is absent.
- Consumers of `hits`, nested `hit`, `relationships`, `relationship_map`, or
  `codegraph_bridge` must pass `include_details=true` for the previous shape.
- The optional relationship map covers documentation nodes only. For source-code symbols,
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
| `view` | `"sections" \| "documents"` | `"sections"` | Legacy section/entity graph, or explicit document references. |
| `max_documents` | `int` (1-500) | `100` | Document-view source universe cap. |
| `max_references` | `int` (1-2000) | `200` | Document-view document-pair edge cap. |
| `include_evidence` | `boolean` | `false` | Document-view verbatim source-block excerpt, at most 240 characters. |

Output nodes use stable ids such as `doc:readme`,
`section:readme:introduction`, and `entity:code:runcontext`. Edge kinds include
`contains`, `xref`, and `mentions`.

Semantics:

- The default section view is a documentation graph, not a source-code graph. Structural and
  xref edges are document-local today; cross-document connectivity is represented
  through shared entity nodes and `mentions` edges.
- The default response includes `codegraph_bridge.status = "external"` to make that
  boundary explicit.

With `view="documents"`, nodes are documents and `document_link` edges represent
explicit CommonMark hyperlinks in cached Markdown section bodies. Relative and
repository-root paths resolve only to selected indexed files. Reference-style
definitions can live in other sections of the same document. Headings, code,
HTML links, external/unindexed targets and self-links are excluded. Fragments
are preserved in `href`, without checking their existence. No semantic/code
impact is inferred, and no model or original source body is read at query time
(normal repository freshness hashing still runs).

One edge per directed document pair carries `reference_count`, the first parsed
`href`, a stable `source_anchor` and a containing-block `source_span` measured in
cached section characters. Optional `evidence` is a verbatim prefix of that
block; its precise `evidence_span` and `evidence_complete` flag distinguish it
from the whole block. Retrieve the source anchor for full evidence. A `doc`
filter retains edges incident to that document in either direction, within the
selected universe. Section/entity flags and budgets apply to the section view;
document/reference budgets and evidence apply to the document view. The focus
document is selected first under the document cap. Output declares scope,
stale/skipped/unavailable documents, caps and `complete`; completeness refers
only to this defined link scope. See [ADR-0016](../decisions/0016-explicit-document-reference-view.md).

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
| `view` | `"artifacts" \| "references"` | `"artifacts"` | Existing artifact/entity impact, or deterministic explicit-link analysis. |
| `entry` | `string \| null` | `null` | Reference view: indexed document ID or source path for deletion reachability. |
| `max_hops` | `int` (1-8) | `3` | Reference view: inclusive reverse shortest-path depth. |
| `max_witnesses` | `int` (1-2000) | `200` | Reference view: maximum distinct proof edges. |

In `view="references"`, `doc` accepts an indexed document ID or exact source
path, and `id` must be omitted. Return direct incoming references,
`reverse_references` (source, distance, full forward path to target),
`strongly_connected_documents` and optional `disconnected_documents` after
deleting the target and incident edges from entry reachability. No entry means
`disconnected_documents=null`, not an empty/negative result. Paths minimize
distance then the whole source-path sequence lexicographically. Traversal runs
locally without a model; it covers explicit document links rather than semantic
or code impact. Metadata uses source paths, with source-section anchors on
`witnesses`. Proofs cover selected shortest paths and internal component edges;
optional original text is fetched separately with `get_section`.

This view analyzes at most500 cached documents/2000 directed document pairs.
`max_results` caps each node collection (nearest reverse paths first; output
sorted by source), and `max_witnesses` caps the proof-edge union. Total counts,
source-graph stats, limits and `complete` expose truncation and stale/skipped/
unavailable data. Incomplete input implies an incomplete analysis; absence in a
partial graph is not evidence of absence in the full corpus. Original body
files are never queried; repository freshness hashing remains in place. Default
artifact/entity impact stays unchanged. See [ADR-0017](../decisions/0017-local-reference-impact-analysis.md).

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
- **Recall model (default offline extractor `heuristic:regex-v2`, ADR-0003).**
  The entity vocabulary is built per document from four signals: code
  identifiers (in code spans), `**bold**` terms, definitional headings (a
  section title that reads as a term, not a structural name), and multi-word
  Title-Case proper nouns. Every body occurrence of a vocabulary term — across
  *all* sections of that document — is returned, not only the defining site.
  Matching is whole-word; single-word `code`/`defined`/`proper` terms match
  case-sensitively, multi-word terms case-insensitively. Vocabulary is
  document-local: a term defined in one document is not auto-recognized in
  another. Richer cross-document, lowercase, and morphological recall is the
  opt-in LLM extractor (ROADMAP v0.2.1).

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
