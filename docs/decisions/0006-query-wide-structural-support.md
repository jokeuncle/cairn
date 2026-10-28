# ADR-0006: Complementary source evidence for context packs

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Maintainer (continued Agent success/cost optimization)
- **Related:** ADR-0004, ADR-0005

## Context

The matched complex-task experiment showed a long query beginning with `async`
returning mostly sections from the async introduction, missing timeouts, limits,
hooks and retries. Discovery ranking intentionally favors topic/document
identity. Sorting the discovery candidate pool again by that score discarded
its document diversity. More navigation then caused irrelevant reads.

## Decision

Keep `search_documents` discovery ranking and its contract unchanged. Within
compact `repo_context`, select complementary source evidence using the existing
query-wide BM25 score and marginal coverage of matched query terms. Weight
coverage by inverse candidate frequency, honor the per-document cap, and use
hybrid ranking when lexical evidence is absent. This chooses among structural
sections; it does not split documents or introduce a new index or model call.
Diagnostic `include_details=true` keeps its previous ordering.

Navigation remains optional and bounded. Tell agents to follow only headings
relevant to uncovered requirements and use short targeted searches for separate
requirement groups. No neighbor bodies are concatenated by default.

Respect fenced-code boundaries when selecting a bounded evidence window. A code
example that fits the window must not be cut in half; oversized partial code is
explicitly marked `truncated_code`. Filter common English function words from
lexical query terms. This repairs an observed regression where the timeout
constructor's final argument was cut out of a secondary 400-character excerpt.

## Alternatives and evidence

A development experiment normalized all global structural bonuses against the
whole query. It reduced first-term dominance but broke an existing document-
discovery use case. Its source and failing regression log are retained in
`navigation-round/iteration2-repo-search-rejected.py` and the corresponding
local log. That global ranking change was reverted, not silently adopted.

## Verification

Test complementary coverage, semantic fallback, caps and stable ties, plus the
existing discovery contracts and fixed QA. Preserve failed navigation-only
snapshots. Freeze a final candidate after development checks and evaluate the
previously frozen tasks over new repositories once. Compare whole-agent task
acceptance and reported session tokens with the same model/budget using BM25
and literal search. Small experiments do not establish commercial readiness.
