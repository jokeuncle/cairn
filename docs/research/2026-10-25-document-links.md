# Explicit document links: correct native graph, cost gate not established

Date:2026-10-25. The actual installed product exposes an explicit cached Markdown document-reference graph. Independent original-source scans match all80 directed document pairs and their occurrence counts. All six real-Agent modules of graph-analysis answers pass independent calculation/source acceptance. No commercial superiority is established.

## Implementation and scope

`repo_graph(view="documents")` preserves the old default section/entity graph. The new view resolves explicit CommonMark links from cached Markdown section bodies, including reference definitions elsewhere in the same document. Stable source anchors, character spans, opt-in bounded original block excerpts, stale/skipped/unavailable records and caps are retained. Headings/code/HTML/external/unindexed/self links are outside the declared scope; fragments are not validated. References do not imply semantic/code impact. Existing graph/impact tools are now available through the actual generic CLI. No dependency, storage format or model query was added.

Full regression605 passed; Ruff clean; mypy75 source files clean. Fresh wheel74 product Python files match the workspace at freeze. Server-off actual installed CLI graph/section/lexical calls succeed with an invalid provider; explicit hybrid queries fail with INDEX_BUILD_FAILED/ConnectError after3 attempts, without fallback. The owned Nomic server was stopped. Two preflight assertion mistakes (a guessed rather than discovered section ID and the wrong expected error-code spelling) are retained in initial/second offline logs; final qualification uses a real returned anchor and the defined error code.

## Frozen Agent protocol

CodexCLI0.164.0, gpt-6.1-sol/high, fresh ephemeral read-only sessions, no network/web/delegation/writes. At most24 observed shell/MCP command events and900s; nested subprocess queries are not additional observed command events. Two new tasktexts ask for all reverse references within3 edges, canonical shortest paths, full SCC, entry reachability after vertex deletion, and exact source witnesses. Oracle definitions and sources frozen before answers; positive references and four seeded regressions per case qualify the checks. Valid Cairn citations pass and invented citations fail.

HTTPX pinned docs23files/128253bytes/23pairs; MkDocs19files/284354bytes/57pairs. Original Cairn HEAD and Starlette corpora were excluded before outcomes for sparse multi-hop structure. These are new tasks on known public projects, author-curated rather than externally blinded. Selected corpus paths/revisions/hashes are in the protocol artifacts. Controls are an independent on-demand full-source MarkdownIt graph helper (no Cairn/index/models) and raw original Markdown with shell/inline Python. All arms may compute and verify their own algorithms.

The first adapter was incorrectly named httpx.py, shadowing the installed HTTPX dependency. That one incomplete session was stopped as infrastructure failure; its prompt/partial events and unknown unfinished usage remain in the parent folder, outside the six completed comparative runs. Corrected non-shadowing script entrypoints were qualified before a fresh770-artifact freeze. The original769-artifact and recovery770-artifact snapshots both verify unchanged. No product/source/answer tuning occurred during the comparison.

## Full-session usage

I=cumulative input; K=cached input; U=I−K; O includes reasoning and every other output token. Command counts are observed events, not model turns or all nested CLI invocations.

| Arm | Accepted | I | K | U | O | Command events | Skill events/chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| cairn | 2/2 | 284571 | 240000 | 44571 | 11277 | 9 | 4/17944 |
| helper | 2/2 | 298338 | 254848 | 43490 | 9865 | 9 | 4/31002 |
| raw | 2/2 | 349245 | 290560 | 58685 | 10730 | 8 | 1/10771 |

Cairn vs helper: input_tokens -4.61%, uncached_input_tokens +2.49%, output_tokens +14.31%.
Cost difference, normalizing uncached input price to1 with cache ratio r and output ratio q: `1081 + (-14848)r + (1412)q`. No provider price or indexing amortization is assumed.

Cairn vs raw: input_tokens -18.52%, uncached_input_tokens -24.05%, output_tokens +5.10%.
Cost difference, normalizing uncached input price to1 with cache ratio r and output ratio q: `-14114 + (-50560)r + (547)q`. No provider price or indexing amortization is assumed.

The predeclared gate requires I/U/O each no greater than BOTH controls, separately from task acceptance. Skill reads and verification/representation choices differ and remain charged; one session per cell cannot isolate the cause of a usage difference. In particular Cairn Agents reconstructed the optional lossless text format and wrote graph-analysis programs themselves. Those are optimization leads, not established causal explanations.

## Setup costs and limits

Indexing uses the real local prefixed/windowed Nomic768 factory and controlled extractive summaries with a warm model server. HTTPX indexing3.64s/1496056bytes; MkDocs5.94s/2745270bytes. Cold model startup, default LLM summary costs, installation and repeated-query amortization are excluded. Both index sizes exceed the original source by more than2x; this is a remaining product target failure. The helper requires no such setup. Offline graph queries do not imply model-free cold indexing or a TCO advantage.

[Machine-readable results](../../benchmarks/repo-quality/document-links-results-20261025.json) · [CLI usage](../cli-retrieval.md) · [ADR-0016](../decisions/0016-explicit-document-reference-view.md)

External artifacts: `/Users/ksher/self-projects/cairn-evaluations/rescue-20261024/document-links-20261025/recovery-round`.
