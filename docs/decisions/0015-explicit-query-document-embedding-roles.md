# ADR-0015: Explicit document/query embedding instructions

- **Status:** Experimental; model-contract correctness and task cost are separate gates
- **Date:** 2026-10-25
- **Related:** ADR-0007, ADR-0013, rejected ADR-0014

The production provider factory exposes a single generic encoding operation.
Nomic's [model card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5#usage)
requires different textual instructions for document and query inputs. Earlier
evaluation adapters implemented this externally; production configuration must
support it without hidden adapters or automatic model-name inference. Previous
prefix-adapter experiments did not establish a commercial cost advantage, so
this repairs model integration rather than explaining all observed cost gaps.

Add an optional batched query-role protocol and a helper falling back to legacy
`embed`. Indexing keeps document encoding. Repository/document lookup and the
flat-RAG control use the query helper. Add explicit environment configuration
`CAIRN_EMBED_DOCUMENT_PREFIX` and `CAIRN_EMBED_QUERY_PREFIX`, empty by default.
Whitespace is significant. A generic adapter applies them before each actual
model input, inside windowing, preserving source bodies. Preserve any native
query-role extension on the delegated provider. Both prefixes contribute to a
hashed model identity, independent of which role is called; changing either
requires matching index/serving configuration and normal reindexing. Empty
configuration preserves existing model identities, values and legacy providers.
No dependency or storage-schema change. Existing MCP config environment export
already supports all `CAIRN_*` variables, including the two new values.

Verify the physical HTTP input for every document/query window, legacy fallback,
native role delegation, empty input, stable/change-sensitive identities, config
whitespace and query-role use in real retrieval. Run full regression and a fresh
installed wheel. A fixed six-session development screen will compare configured
prefixes, empty-prefix stock retrieval and fresh raw controls on two known
complex tasks. Freeze corpora, controls, oracle and all arms before answers.
Preselect the configured prefix arm, preserve all failures, and require equal
task acceptance plus aggregate I/U/O no greater than raw and stock. This is not
heldout generalization, and compliance with model instructions alone does not
establish task success or a cost advantage. No global config/auth/publication.

Outcome: all six real-Agent sessions passed task/source acceptance, but the
preselected prefix arm failed its cost gate against stock and raw controls.
Retain the opt-in model configuration with empty defaults; no default savings
claim. See the [frozen results](../research/2026-10-25-role-prefix.md).
