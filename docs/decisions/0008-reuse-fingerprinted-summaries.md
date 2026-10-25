# ADR-0008: Reuse fingerprinted stored summaries during rebuilds

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Maintainer (continued success/cost optimization)
- **Related:** ADR-0007; ARCHITECTURE.md §2.6

## Context

Enabling an embedding-window adapter requires vector rebuilding. Repository
sync did not supply the optional summary cache, so an embedding-only change or
failed vector build caused every unchanged summary to be generated again.
Existing `summaries.json` already stores model and section-content fingerprints.

## Decision

On normal builds, reuse stored summary text only when format, outer/row model,
section hash and summary level match. Changed sections, models and missing
levels are regenerated. Corrupt prior JSON is logged and rebuilt. No new cache
or storage artifact is created. `index_path(force=True)` bypasses this stored
reuse; an explicitly supplied external cache keeps its prior semantics.

## Consequences and verification

Local index content is trusted as before. Reuse is observable in structured
logs. Test unchanged sections, one-section edits, model changes, new levels,
force rebuilding and corrupt stored data. Verify a real embedding-policy
rebuild with unchanged documents consumes zero additional summary-model calls.
Indexing cost savings are separate from whole-agent query-session savings.
