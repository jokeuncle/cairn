# ADR-0003: Two-Pass Heuristic Entity Recall

- **Status:** Accepted
- **Date:** 2026-06-26
- **Deciders:** Founding maintainer
- **Related:** ADR-0001, ARCHITECTURE.md §2.2 (entities sub-index), §4 (data
  model), docs/specs/mcp-tools.md §6 (`find_mentions`), CLAUDE.md P1/P4/P7/P8

## Context

`find_mentions` is specified to "return every section where a named entity
occurs" (mcp-tools.md §6). In practice it under-delivered:

1. The `heuristic:regex-v1` extractor only recognized two signals — identifiers
   inside code spans (`code`) and `**bold**` terms (`defined`). Domain terms
   that documents define with a *heading* (a glossary `### Tenant`) or write as
   a capitalized proper noun (`Auth Service`) were never extracted, so
   `find_mentions("Tenant")` returned nothing on a perfectly ordinary doc set.
2. More fundamentally, v1 was **single-pass**: it emitted a hit only at the
   exact site of the signal (the one bold span, the one code token). A term
   defined once but referenced in ten other sections produced a *single*
   mention. That contradicts the tool's contract — "every section where the
   entity occurs."

The naive fix ("also scan headings") would only add the defining section and
still miss the cross-section references — a half-measure. The real shape of the
feature is: discover a vocabulary of entities, then find every textual
occurrence of each across the document.

LLM-based `term`/`proper` extraction remains the higher-quality follow-up
(ROADMAP v0.2.1). It must stay opt-in so the no-API-key path keeps working
(P4); this ADR is the offline, deterministic baseline that makes `find_mentions`
genuinely useful today.

## Decision

Replace the extractor with a **two-pass, deterministic** design
(`heuristic:regex-v2`):

**Pass 1 — build a vocabulary** of candidate entities from precision-gated
signals:

- `code` — identifiers in fenced/inline code spans (unchanged rules: length
  ≥ 3, language-keyword stoplist).
- `defined` — `**bold**` terms (unchanged: ≤ 80 chars, no sentence
  punctuation) **plus** *definitional headings*: a `SectionNode.title` that
  reads as a term, not a generic section name. Gates: ≤ 6 words, no sentence
  punctuation, not in a stoplist of structural headings (Overview, Introduction,
  Usage, Inputs, Output, Semantics, Context, Decision, Consequences, …), and
  either Title-Case or a single capitalized token.
- `proper` — multi-word Title-Case sequences in prose (≥ 2 capitalized tokens,
  e.g. `Auth Service`, `Aurora Platform`), with leading function words trimmed
  and all-stopword sequences rejected.

**Pass 2 — resolve mentions**: for every section, scan its `raw_text` for
whole-word occurrences of each vocabulary term and emit one `ExtractionHit` per
occurrence (`span` is the match range in `raw_text`, satisfying the existing
coordinate contract). Headings feed the vocabulary but are not themselves
mentions, because `raw_text` excludes the heading line — a section is a mention
only when the term textually appears in its body.

Matching precision:

- Whole-word boundaries (a match may not be flanked by `[A-Za-z0-9_]`).
- `code` and single-word `defined`/`proper`: case-sensitive (avoids matching the
  common word "event" for the symbol `Event`).
- Multi-word `defined`/`proper`: case-insensitive (multi-word phrases rarely
  collide).
- Longest-match-wins when one term is a prefix of another (`Auth Service`
  beats `Auth`).

The `Entity` schema, `entities.json` `format_version`, and the MCP tool catalog
are all unchanged. Only the extractor `name` bumps (`heuristic:regex-v2`), which
is recorded in `entities.json` so a re-index is observable.

## Consequences

### What we gain
- `find_mentions` returns cross-section results for heading-defined terms and
  multi-word proper nouns — the contract it always advertised.
- Fully offline and deterministic (P4, P7). No new dependency, no API key, no
  per-section LLM cost.

### What we give up / risks
- **Recall < an LLM NER.** Single-word common-noun concepts not capitalized or
  defined (e.g. lowercase "event") are deliberately not matched, to protect
  precision. The LLM extractor (opt-in, v0.2.1) is the recall upgrade.
- **More entities per document** → larger `entities.json`. Bounded by the
  precision gates and stoplists; measured on the Cairn repo and aurora-handbook
  fixtures.
- **Re-index required** to pick up the new entities (source-hash no-op means
  existing indexes keep v1 output until rebuilt with `--force`). Expected and
  observable via the `extractor` field.

## Alternatives Considered

- **Single-pass "also scan headings."** Rejected: adds the defining section but
  still misses every cross-reference — the exact gap that makes `find_mentions`
  feel broken.
- **Ship the LLM extractor now.** Rejected as the baseline: violates the
  no-API-key path (P4) if made default, adds cost and non-determinism, and is a
  precision/canonicalization rabbit hole. Kept as the opt-in v0.2.1 follow-up.
- **Case-insensitive matching for all kinds.** Rejected: matching `event`
  everywhere for the symbol `Event` floods results. Case-sensitivity is gated by
  kind and arity instead.

## Open Questions

- Should `find_mentions` lookup be case-insensitive at query time (so "tenant"
  finds canonical "Tenant" even when no lowercase surface form was observed)?
  Deferred — a tool-layer change, separate from extraction.
- Morphological variants (plurals, possessives) are not matched. Revisit with
  the LLM extractor, which can canonicalize them.
