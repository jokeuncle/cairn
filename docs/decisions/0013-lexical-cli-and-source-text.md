# ADR-0013: Explicit lexical retrieval and a shared read-only CLI

- **Status:** Experimental; the preselected task-cost candidate failed its screen
- **Date:** 2026-10-25
- **Authorization:** Continued maintainer-directed optimization, including reducing
  unnecessary retrieval cost; no publication or default replacement authorized
- **Related:** ADR-0012; strong-control/new-project study

## Decision

Expose existing read-only repository tools through `docsgraph query tool`, with
JSON arguments and JSON output by default. Factor the existing dispatcher into
a transport-neutral module shared by CLI and MCP. Retrieval tools never import
MCP/CLI or read original source files. Existing MCP dispatch import paths remain
compatible. No new MCP tool or on-disk format is introduced.

Add explicit `retrieval="lexical"` to repository search/context; default remains
`hybrid`. Lexical mode reuses cached source, BM25/field/structural scoring and
evidence packing, without constructing a query embedding or reading vector
entries. It still needs an existing index and its metadata/summaries. This is
not a model-free cold-indexing feature. Separate bounded caches keep lexical and
dense data independent; unmatched lexical queries do not return arbitrary zero
score passages. Semantic lookup remains an explicit caller choice, never an
automatic threshold-based success claim.

The CLI constructs an embedding provider only for hybrid search. Cached reads
and lexical searches must work with an unavailable or unconfigured endpoint.
Invalid inputs produce a failure exit status; normal results preserve citations,
source scopes, omissions, stale/skipped documents and recovery signals.

An opt-in text representation separates long payload strings from compact JSON
metadata, with explicit references and Unicode-character lengths. All values
must roundtrip, including source text, code, spans, citations and warnings.
Repeated identical strings may share one record; no source is truncated or
summarized. Equally shaped record lists may share explicit columns and rows;
missing fields and nulls remain distinct. A plain compact JSON fallback avoids increasing serialized byte
size. This is not an exact model-token guarantee or a structured-only MCP
response. MCP transport stays unchanged.

## Acceptance, boundaries and rollback

Verify source/metadata roundtrips, Unicode/control characters, marker collisions,
error envelopes and byte-size fallback. Test lexical calls with vector access
and provider construction forbidden, misses, stale data, cache separation and
unchanged default hybrid results. Verify CLI exit/argument behavior and layer
imports, then build/install the package.

Freeze a ten-session development screen: two known multi-constraint coding
tasks crossed with lexical/hybrid and JSON/text, plus fresh actual raw-source
controls. The preselected primary candidate is lexical/text; do not select the
best cell after answers. Preserve all outcomes and qualify final code/citations
using the independently qualified runtime checks. Compare full-session I/K/U/O,
not only payload size. These reused tasks cannot establish broad generalization
or commercial superiority.

No global authentication/config changes, source mutation, new dependency or
publication. Existing JSON/hybrid behavior is the rollback path; the new mode
and representation are explicit opt-ins. If the screen fails, retain the result
and do not promote the mode or representation to a cheaper default.

## Observed result

The [completed ten-session screen](../research/2026-10-25-lean-cli.md) accepts
both tasks in every arm. Primary lexical/text increases cumulative input by
98.09% and uncached input by 21.67% against fresh actual raw-document controls.
Hybrid/text is a secondary observation with lower uncached input but higher
cumulative input. It is not substituted as the preselected winner. The product
keeps all defaults, and no commercial or generalization claim follows.
