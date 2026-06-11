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
JSON envelope). It is an estimate using the indexing-time tokenizer; agents
should treat it as accurate to within ±10%.

### Errors

Tools never raise to the MCP transport. They return a structured envelope:

```json
{
  "ok": false,
  "error": {
    "code": "NOT_FOUND" | "INVALID_INPUT" | "INDEX_STALE" | "INTERNAL",
    "message": "human-readable",
    "details": { ... }
  }
}
```

Successful responses:

```json
{
  "ok": true,
  "tokens_returned": 412,
  "data": { ... tool-specific payload ... }
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
| `include` | `list["synopsis"\|"head"]` | `["synopsis", "head"]` | What to attach to each hit. `head` = first 200 chars of raw_text. |
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
        "head": "useEffect can run side effects after render. A common pattern..."
      }
    ],
    "cursor": null
  }
}
```

### Semantics

- Scores are cosine similarity, normalized to [0, 1]. Comparable within a
  single query but not across queries.
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
