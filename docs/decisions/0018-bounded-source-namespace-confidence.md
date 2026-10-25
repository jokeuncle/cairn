# ADR-0018: Bounded confidence for an explicit source namespace

- **Status:** Accepted for alpha0.1.0a13; no general quality/cost claim
- **Date:** 2026-10-25

## Context

The pre-release32-query fake-provider development gate initially scored27/32
top1 and31/32 top3. A fresh original-release control on the same source revisions
scored29/32 and32/32. Full cached-body recall must remain: reverting to a body
prefix or document-specific BM25 normalization would restore known defects.

A query explicitly naming a source namespace such as `rpc adapter` loses
document-identity confidence when prefixed with an action verb. Existing
identity confidence only measures the first three weighted query terms. A
literal compound namespace is stronger evidence than incidental body mentions.

Separately, original-source review found overly narrow evaluation labels. A
fresh Agent, blind to ranks/scores/previous labels, accepts the UV homepage for
both uvx execution and tool installation, and the Bazel guide's explicit login
instructions for the index-authentication query. It rejects TLS certificate
guidance for that login question and the MCP client role for exposing an agent
as an MCP server. Those three source aliases are oracle corrections, not
product-performance improvements. Preserve original outcomes and adjudication.

## Decision

For an existing literal command/identifier phrase matching whole normalized
tokens in the document ID or source path, use the existing maximum document
identity confidence. Keep the same0.25 cap and every fusion weight. Do not grant
this signal from title/body occurrences. Keep full bodies, query-wide BM25,
cached-only retrieval, citations and all existing API/storage defaults.
No repository names, benchmark questions or domain-specific expected answers
enter product code.

Add three independently source-qualified aliases to the public evaluator,
preserving original queries, all existing labels and all strict thresholds.
Freeze a correction record before the repaired gate run; report original,
corrected-label and repaired-code outcomes separately. Prior frozen Agent
studies and their failed cost gates are unchanged.

## Verification and consequences

Use metamorphic checks that action-verb prefixes do not dilute a literal
namespace, directory separators normalize consistently, and partial tokens or
body/title-only mentions do not acquire this source signal. Re-run full
lint/types/tests, the unchanged strict thresholds and the37-repository smoke.
This is a development repair and source-label adjudication, not heldout semantic
accuracy, an Agent success advantage or commercial certification.
