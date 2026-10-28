# Explicit document/query embedding roles: model correctness, failed cost gate

Date:2026-10-25. Production now supports explicit document/query instructions on every physical input window, with legacy fallback and policy fingerprints. Six real-Agent runs pass independent task/source acceptance. The preselected configured-prefix arm fails its cost gate against both stock and raw. Model-contract compliance is verified; a commercial cost benefit is not.

## Model integration and qualification

The [Nomic v1.5 model card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5#usage) requires distinct `search_document: ` and `search_query: ` instructions. Its [training report](https://arxiv.org/html/2402.01613v2) describes query-to-document contrastive training; these model-level results are not evidence of Cairn Agent performance. Previous studies already used external role adapters; this phase makes the configuration available in the actual product factory rather than explaining every earlier failure through missing prefixes.

Optional `embed_queries(texts)` plus a fallback helper preserves legacy Embedders. Repository/document retrieval and the flat-RAG control use the query path; indexing uses document encoding. Both empty-by-default prefix fields are explicit environment settings and preserve whitespace. Their hashed policy is part of model identity. The adapter is inside windowing, so each physical input receives the appropriate instruction; original bodies/citations remain unchanged. Existing CLI compatibility checks reject changed policies before query embedding.

Eight new meaningful tests qualify physical HTTP inputs for every Unicode window, empty input, native role forwarding, legacy/window equality, config whitespace, document/repository/flat-baseline query roles, unchanged source and mismatched-policy rejection. Full suite592 passed; Ruff clean; mypy74 sources clean. Fresh installed wheel: all73 Python source files match. Actual Nomic prefixed indexing/query succeeded in the real Codex read-only/network-restricted sandbox.

## Frozen real-Agent development screen

Same two now-known HTTPX/Starlette tasks and qualified20-group runtime oracles. All complete modules, source access, requirements and citations independently audited; four reference regressions remain rejected. Samegpt-6.1-sol/high CodexCLI0.164.0,24-observed-command/900s limits. Orders HTTPX prefix→raw→stock; Starlette stock→raw→prefix.116 frozen artifacts matched on completion. No valid failures rerun.

Both CLI arms use the same73-file wheel, same generic six-tool interface/text renderer, model/window sizes and budgets. Only the explicit role policy and its independently built index differ. Stock policy is two empty strings; prefix policy is the exact two instructions above. Four fresh indexes contain identical original source bytes; summaries are controlled extractive text and the local model server is already running.

| Arm | Accepted | I | K | U=I−K | O | Observed calls | Doc command events/errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| prefix | 2/2 | 690,783 | 614,272 | 76,511 | 13,111 | 19 | 9/1 |
| stock | 2/2 | 435,730 | 394,624 | 41,106 | 13,294 | 16 | 12/3 |
| raw | 2/2 | 313,897 | 281,600 | 32,297 | 13,221 | 9 | 0/0 |

I is cumulative input; O includes reasoning and all other output. Observed command invocations are not model turns.

Prefix vs stock: input_tokens +58.53%, uncached_input_tokens +86.13%, output_tokens -1.38%. Cost difference (uncached-input price1, cache ratio r, output ratio q) is `35405 + 219648r -183q`. No provider price is assumed.

Prefix vs raw: input_tokens +120.07%, uncached_input_tokens +136.90%, output_tokens -0.83%. Cost difference (uncached-input price1, cache ratio r, output ratio q) is `44214 + 332672r -110q`. No provider price is assumed.

All answers being correct does not override the predeclared requirement that I/U/O each not exceed both controls. Source-role correctness is not an end-to-end cost result. Prefix Agents read83,206 process-skill characters, stock46,893, raw0. Different local tests and corrective requests remain included. These behavioral differences and one session per cell prevent causal claims about prefix quality.

## Retained scope and records

Keep explicit opt-in roles because physical inputs, integration and compatibility are verified. Keep empty defaults and all previous source/citation/CLI repairs. Do not claim default cost savings or commercial superiority. The earlier source-command shortcut remains withdrawn.

External root: `/Users/example/project`. `protocol-frozen.json`, `runs/r00..r05`, `index-results.json`, `trace-diagnostics.json` preserve source bytes, all answers/errors/usage and independent reviews. The independent native-graph probe is ancillary and not an Agent outcome or optimization result.

[Machine-readable results](../../benchmarks/repo-quality/role-prefix-results-20261025.json) · [Configuration](../embedding-instructions.md) · [ADR-0015](../decisions/0015-explicit-query-document-embedding-roles.md)
