# ADR-0012: Opt-in budgeted original evidence blocks

- **Status:** Experimental; not a demonstrated parity or commercial win
- **Date:** 2026-10-25
- **Deciders:** Maintainer (continued success/cost optimization)
- **Related:** ADR-0006, ADR-0011

## Context

Full context packs improved HTTPX acquisition but over-read long Ruff bodies.
Across five tasks, correctness tied raw search while uncached input remained
31% higher. Smaller snippets and fewer calls alone did not establish savings.

LongLLMLingua motivates query-aware compression; BRIGHT-Pro motivates
complementary evidence. We borrow these ideas, not their trained models or
reported gains. The present experiment must retain exact source and code syntax.

## Decision

Add explicit `repo_context(level="evidence")` and an evidence-only
`max_context_chars` source-character budget (default 8000). Existing defaults
and other views are unchanged. Select whole Markdown blocks, with adjacent
prose for context, under both global and per-section source-character limits.
Fitting examples remain intact. Recognizable CLI help can be read as individual
options with their usage/group context; arbitrary code is never split.

Selection uses diminishing marginal query-term coverage plus section diversity
per serialized-character cost. These are relevance proxies, not calibrated
success probabilities. Return each selected original block once with exact
section-relative character spans, citations and explicit omitted-content status.
Ancestor/descendant content is not implicitly included. Unmatched or oversized
content remains available through normal section reads. Never certify semantic
completeness or infer undocumented behavior from omitted text.

A retained development iteration first reduced candidates to k sections before
packing blocks. A real Ruff query had the necessary rule-selection section at
discovery rank 2, but preselection discarded it. The next candidate jointly
selects blocks from the wider structural shortlist under the requested section
and document caps. Both candidate snapshots are retained. General discovery
ranking and existing summary/full views remain unchanged.

An optional `queries` list lets the calling agent supply 1-8 focused information
needs in evidence mode. The backend does not invent decompositions. It searches
each focus, fuses at most 64 unique structural candidates and preserves each
query's discovery rank. Block selection uses a maximum-relevance coverage
surrogate per focus (lexical overlap discounted by rank), under shared budgets.
These values are not semantic entailment or calibrated probabilities; dependent
queries remain a later agent action. The earlier single-query candidate remains
frozen for comparison.

No new tool, index artifact, model call, dependency, source mutation or hidden
session state. Diagnostic expansion is incompatible with this compact view and
fails explicitly. The metadata budget is observable; character limits are not
an exact model-token budget.

## Verification and stop conditions

Test source-span round trips, complete/partial bodies, code integrity, CLI
option context, Unicode, deterministic complementary selection and both hard
budgets. Verify transport schema dispatch and unchanged old modes. Freeze source
before a real-Agent development comparison against actual rg, then use frozen
additional tasks if development results justify it. Preserve all failures and
report cached/uncached/output separately. Parity remains a hypothesis.
