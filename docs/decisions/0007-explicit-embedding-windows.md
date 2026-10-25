# ADR-0007: Explicit section embedding windows

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Maintainer (continued reliability optimization)
- **Related:** PRODUCT.md §3; ARCHITECTURE.md §2.5; ADR-0004

## Context

The previously frozen Ruff corpus exposed a real ingest failure: a 3,034-token
section exceeded the local embedder's 2,048-token window. The inference server
capped its context to the model's training window despite a larger CLI setting.
Changing test sources or discarding the tail would conceal the failure.

## Decision

Add an explicit `WindowedEmbedder` adapter. Split each input into UTF-8-bounded
windows, preserving every byte and preferring nearby whitespace boundaries.
Embed every window and pool normalized window vectors by their byte lengths
into one normalized section vector. Short inputs retain the delegate result.
Keep tree nodes, original bodies, stable citations and storage schemas intact.

Expose it as the opt-in existing provider setting
`CAIRN_EMBED_PROVIDER=windowed-openai-compatible`, using 1,500-byte windows.
The SDK constructor accepts a different byte budget. This is not an exact token
budget; users must allow for provider prefixes and tokenization. Do not silently
retry an overflowing request with truncation or switch providers.

## Consequences

Long sections require more embedding work, and pooling may dilute a localized
fact. Sparse search still indexes the complete body. The embedder identity
includes the windowing policy/budget, so normal sync invalidates old vectors
when the adapter is enabled. Indexing and serving must use the same policy.
Structured logs report window counts without logging content or credentials.
The existing default provider is unchanged; no new dependency is introduced.

## Verification

Property tests prove Unicode roundtrip and per-window byte bounds. Tests cover
short-input equivalence, inclusion of tail windows, batching/order, invalid
provider outputs and factory selection. Reindex the unchanged failed Ruff
sources against the actual local embedder and record the observed result.
