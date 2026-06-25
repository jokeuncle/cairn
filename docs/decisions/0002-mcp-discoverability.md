# ADR-0002: MCP Tool Discoverability (Server Instructions + Intent-Based Descriptions)

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** Founding maintainer
- **Related:** ADR-0001, ARCHITECTURE.md §3.1, docs/specs/mcp-tools.md, CLAUDE.md (P2, P5, P8)

## Context

Cairn's MCP server registers correctly and its tools are visible to clients, but
agents rarely *choose* to call them. Observed failure mode: with the Cairn tools
present in the catalog, an agent answering a documentation/spec question still
reaches for built-in `Grep`/`Read` instead of `repo_context`/`search_documents`.

This is a tool-selection problem, not a registration or empty-index problem. An
LLM decides whether to call a tool almost entirely from (a) any server-level
guidance injected into its system prompt and (b) the per-tool `name` +
`description`. Reviewing the current surface (`src/cairn/mcp/server.py`,
`src/cairn/mcp/schemas.py`) surfaces concrete causes:

1. **No server `instructions`.** `Server(SERVER_NAME)` is constructed with no
   `instructions=` argument (server.py:172, 496). The MCP Python SDK supports it
   (`Server(name, version, instructions=...)`), and clients surface it to the
   model. This is the single highest-leverage place to tell an agent *when* to
   prefer Cairn over grep — and it is currently empty.
2. **Descriptions state *what*, not *when*.** e.g. `search_keyword` →
   "Exact (case-insensitive) lexical search." An LLM matches *user intent →
   description*; pure capability text matches weakly.
3. **Generic names collide with built-ins.** `outline`, `get_section`,
   `search_semantic`, `read_range` overlap conceptually with the agent's
   always-available `Grep`/`Read`/`Glob`, which win by default.
4. **Discouraging language.** `find_mentions` advertises "Requires the entities
   sub-index (v0.2+)"; `get_section` mentions "reserved for v0.2". Models avoid
   tools that signal "may be unavailable".
5. **Pipeline noise.** `_repo_doc_tool` appends "Returns a structured envelope
   with `trace.steps` for AI clients." (schemas.py:358) — irrelevant to the
   call/no-call decision.
6. **Decision paralysis.** ~13 near-equal tools with no signposted entry point;
   the natural entry point (`repo_context`) is buried fifth and unlabeled as
   such.

## Decision

Improve discoverability **without changing the frozen tool catalog** (no tool
added, removed, or re-signatured — P5 untouched). Specifically:

1. **Set MCP server `instructions`** in `build_server` and `build_repo_server`.
   The text names `repo_context`/`search_documents` as entry points, states the
   progressive-disclosure path, and draws the boundary against source-code grep.
2. **Rewrite tool `description` strings to be intent-first** — lead with "Use
   when …", keep one clause of capability, preserve citations/altitude framing
   (P2).
3. **Remove discouraging/forward-looking caveats** from tools that work today;
   keep gating language only where a sub-index is genuinely required, and phrase
   it as a precondition rather than "reserved".
4. **Drop the envelope/`trace.steps` boilerplate** from repo-doc descriptions.

These are description/instructions-only edits. Tool names, input schemas, and
output schemas are unchanged.

### Proposed server `instructions` (document mode)

> Cairn is a structure-aware navigation map for this document. Prefer it over
> dumping or grepping raw text. Start with `outline` to see the structure, then
> `search_semantic`/`search_keyword` to locate relevant sections, then
> `get_section` to read at the right level (gist → synopsis → full). Every
> result carries stable section ids — cite them. Cairn returns summaries by
> default; request `full` only when you need the exact text.

### Proposed server `instructions` (repo mode)

> Cairn indexes this repository's documentation (specs, design docs, READMEs)
> as a navigable map. For any question about what the docs/specs/design say,
> prefer Cairn over grepping the repo. Start with `repo_context` (one call:
> ranked hits + ready-to-read sections + relationship map) or `search_documents`
> (cross-document ranked hits), then drill into a specific doc with
> `get_section`/`get_related`. Cairn is documentation navigation — it does not
> replace source-code search; use your code tools for source files. Results are
> summaries with stable, citable section ids by default; request `full` text
> only when needed.

### Proposed description rewrites

| tool | before | after |
|---|---|---|
| `outline` | "Get a structural map of the document. The cheapest tool; agents should call it first." | "Use first to see the document's structure before reading. Returns a cheap heading tree with one-line gists and stable section ids to navigate from." |
| `get_section` | "Fetch one section at a chosen summary level (gist/synopsis/full)." | "Read one known section at the level you need: gist (one line), synopsis (default), or full text. Use after outline/search to drill in; request full only when exact wording matters." |
| `expand` | "Move from a shallower summary to a deeper one for a known section. Equivalent to get_section(id, level=to)." | "Go deeper on a section you've already seen (synopsis → full). Use when a summary isn't enough and you need more detail for that exact section." |
| `search_semantic` | "Dense vector search. Use for conceptual queries where exact wording is unknown." | "Use when the user asks about a concept or topic and you don't know the exact wording. Returns ranked, cited sections from the structured index — prefer this over grepping prose." |
| `search_keyword` | "Exact (case-insensitive) lexical search. Use for known entities, code symbols, technical terms." | "Use when you know the exact term, symbol, or phrase to find in the docs. Returns cited sections — prefer this over grep for indexed documents." |
| `find_mentions` | "Locate every section where a named entity is mentioned. Requires the entities sub-index (v0.2+)." | "Find every section that mentions a named entity (term, code symbol, proper noun). Use to trace where a concept is discussed across the document." |
| `get_related` | "Return neighbors of a section across the cross-reference graph and the structural tree (xref/sibling/parent/child)." | "Use after landing on a relevant section to find connected sections — cross-references, siblings, parent, children. Good for following a thread without re-searching." |
| `read_range` | "Read continuous content across consecutive sections from start_id through end_id, truncating at max_tokens." | "Read a continuous span across consecutive sections (start_id → end_id) when you need the surrounding context, not just one section. Capped at max_tokens." |
| `repo_context` | "Composite repo retrieval: search across documents, attach compact section content, explanations, related sections, and a relationship map in one call. Use this when an agent needs ready-to-read context." | "START HERE for a question about this repo's docs. One call returns ranked hits, ready-to-read section content, related sections, and a relationship map — enough to answer without further drilling in most cases." |
| `search_documents` | "Search across every indexed repository document and return globally ranked section hits with doc ids. Use this before drilling into a specific document." | "Use to find which docs and sections are relevant to a query across the whole repo. Returns globally ranked, cited hits with doc ids; follow up with get_section on the winners." |

Repo-doc tool wrapper (`_repo_doc_tool`): keep the base description, append only
"Pass optional `doc` to target a specific repository document." — drop the
envelope/`trace.steps` sentence.

## Consequences

### What we gain
- A server-level signal that shapes the agent's mental model ("docs question →
  Cairn first"), which per-tool text alone cannot establish.
- Intent-first descriptions that match user phrasing, raising call probability.
- Honest tool surface: no "reserved"/"required (v0.2+)" language deterring use
  of tools that work today.

### What we give up / risks
- **Over-triggering.** Stronger "prefer Cairn over grep" language could pull
  agents toward Cairn for source-code questions where grep is correct. Mitigated
  by an explicit boundary clause in the repo instructions ("does not replace
  source-code search").
- Description text becomes longer (more tokens in `list_tools`). Acceptable: it
  is paid once per session, not per call.
- Instructions/descriptions are now a maintained surface that must track tool
  behavior. Covered by keeping them in `schemas.py`/`server.py` beside the tools
  and noting them in `docs/specs/mcp-tools.md`.

## Alternatives Considered

- **Rename tools to be less generic** (e.g. `cairn_outline`). Rejected for now:
  renames are signature-level catalog changes (P5) and a heavier commitment than
  warranted before measuring the instructions+description effect.
- **Reduce the tool count** (hide drill-down primitives behind a composite).
  Rejected for now: the primitives are part of the documented progressive-
  disclosure contract (P2); signpost an entry point via instructions instead of
  removing tools.
- **Inject guidance via client-side prompting only.** Rejected as the primary
  fix: it doesn't help other clients/users and isn't shipped with the server.

## Open Questions

- Do target clients (Claude Code, Cursor, Cline) actually surface MCP server
  `instructions` to the model today? → Validate empirically before marking
  Accepted; if a client ignores them, the description rewrites still stand alone.
- Should we measure trigger rate before/after (e.g. a bench harness counting
  tool selections on a fixed task set)? → Defer to a follow-up; not blocking.
