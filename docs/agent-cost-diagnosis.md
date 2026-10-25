# Agent effectiveness and cost diagnosis — 2026-10-24

This report ends at the bulk-source diagnostic. The subsequent
[paper-informed experiments](research/2026-10-24-evidence-policy.md) record
later changes and verification; the source hashes and counts below identify
the earlier snapshot.

The repairs make Cairn more reliable, but current experiments do **not** show
an agent success-rate or cost advantage over simpler retrieval. The next
research target should be cost-sensitive evidence acquisition across an entire
task, rather than another fixed ranking-weight adjustment. This is a proposed
direction, not an implemented or validated commercial advantage.

## What was actually tested

Fresh Codex CLI agents (`0.164.0`, `gpt-6.1-sol`, high reasoning) completed an
HTTPX shared-client implementation task and a Ruff isolated-CI configuration
task using three evidence sources: Cairn MCP, independent BM25 MCP, or actual
`rg`/shell reads over the same selected original documents. Each had a 24-call
budget, 900-second wall limit, and the same permission to execute local tests.
No expected answers were supplied. Answers, tool events, usage, source snapshot
hashes, and unsuccessful startup probes were retained.

All three arms passed both tasks in each of two development iterations.
Acceptance includes independent execution of the HTTPX code, actual Ruff
execution against temporary fixtures, and manual review of explanations and
citations. Network negotiation, live timeout timing, and production load were
not tested. The second iteration keeps compact MCP search responses and exposes
the existing `read_range` alongside the previous five tools. All arms were
rerun once; neither iteration is discarded.

Second-iteration totals across the **same two tasks**:

| Evidence source | Accepted tasks | Tool calls | Input tokens | Uncached input | Output tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cairn | 2/2 | 33 | 582,839 | 82,231 | 6,741 |
| BM25 | 2/2 | 30 | 438,049 | 60,577 | 6,596 |
| Original documents + rg | 2/2 | 11 | 326,252 | 45,932 | 6,243 |

Input counts are CLI-reported cumulative model inputs, including cached input;
they are not unique source tokens. Tool counts include shell and skill reads.
Cairn used approximately 79% more total input and 79% more uncached input than
the raw-document arm on this pair. This is evidence **against** a cost advantage
in this setting. It is not a population estimate or an API dollar bill.

Compact search did not establish a causal session-cost improvement: Cairn's
HTTPX input grew from 339,251 to 363,338, while Ruff input fell from 253,892 to
219,501. BM25 and raw repeated runs also varied. There is one attempt per
task/arm/iteration and two simultaneous protocol changes; a randomized repeated
ablation is necessary to attribute a difference.

In the latest Cairn trajectories, HTTPX made nine searches before section
reads; Ruff made two searches, two outlines, and nine section reads. Neither
task used `repo_context` or `get_related`. Existing compact evidence selection
therefore did not directly receive an end-to-end test in these sessions.
Adding a capability does not establish that an autonomous agent will select it.

Machine-readable usage, answer hashes, source hashes, protocols and limitations:
[agent-cost-results-20261024.json](../benchmarks/repo-quality/agent-cost-results-20261024.json).
Complete local traces and independent execution results are under
`/Users/ksher/self-projects/cairn-evaluations/rescue-20261024/navigation-round/`.
This is a local artifact location, not a public download URL.

### Follow-up: does supplying all source upfront solve this?

A diagnostic run supplied **all** the same selected original documents verbatim
in the first prompt, with the same raw-file access, tasks, model and budgets.
There was no oracle passage selection, answer generation or hidden rubric in
the prompt. Both tasks passed independent execution and manual review.

| Task | Raw iteration 2 input | Upfront-full-source input | Raw uncached | Upfront uncached |
| --- | ---: | ---: | ---: | ---: |
| HTTPX | 236,642 | 292,341 | 23,778 | 83,189 |
| Ruff | 89,610 | 32,738 | 22,154 | 22,882 |

Ruff needed zero tool calls and approximately 63% fewer cumulative input tokens,
but its uncached input rose slightly. HTTPX still used six calls to verify its
code and processed approximately 24% more input. Across both tasks, uncached
input rose from 45,932 to 106,071 (approximately 131%). Full-source delivery
therefore does not establish a general cost win either. Larger prefixes and
execution traces still matter, even after eliminating documentation lookups.
One run per task cannot establish a causal or repeatable improvement.

This is a diagnostic baseline, **not** a new Cairn feature or a held-out product
win. It strengthens the case for testing adaptive access and caching-aware
accounting, while retaining direct search and upfront delivery as alternatives.
See [bulk-source-diagnostic-20261024.json](../benchmarks/repo-quality/bulk-source-diagnostic-20261024.json)
for the frozen protocol, output hashes, usage and independent reviews.

## Which weaknesses are supported by evidence?

| Layer | Observation | Conclusion and limit |
| --- | --- | --- |
| Ingestion and provenance | Headingless/preamble loss, namespace reuse, code truncation and root-sibling defects were reproduced and repaired. | These were correctness defects; their repair has value independently of ranking superiority. |
| Index economics | Explicit windows allow an overlong section to embed; unchanged summary fingerprints avoid new summary-model requests. | Indexing reliability and repeat-build cost improved. This does not prove query-session savings. |
| Startup | A real Codex handshake failed; profiling found expensive storage imports. Lazy loading subsequently passed the configured 10-second startup smoke. | Startup became usable in this environment; first vector access still pays storage initialization cost. |
| Ranking | Both simpler baselines also satisfy the two Codex tasks. | There is no success-rate separation here. This does not prove ranking is optimal or graph structure is useless. |
| Evidence acquisition | Numerous search/read round trips; smaller individual replies did not consistently reduce total input. | Interaction granularity and tool selection are leading cost hypotheses, requiring controlled ablations. |
| Generation and verification | The 4B agent failed all six frozen stress tasks in each retrieval arm; Codex passed two tasks. | The protocols differ, including execution feedback. This cannot be attributed solely to model size. |
| Evaluation | Few public API/config tasks, repeated during development; limited graph traversal. | Broad generalization, commercial readiness and superiority remain unestablished. |

The 4B stress set covers new Uvicorn/Ruff documentation plus new HTTPX/Starlette
compositions. Invalid CLI flags, incorrect configuration and broken generated
Python failed executable checks; keyword overlap was not accepted as task
success. The config oracle was qualified with positive reference fixtures; an
initial macOS path-normalization bug and its failed control are preserved.
The earlier fixed-context QA results are a different experiment and must not be
reported as autonomous task success. See the [benchmark protocol](../benchmarks/repo-quality/README.md).

The two harnesses also expose an evaluation problem: their respective task
sets produce a floor for the small agent and a ceiling for Codex, with no
success-rate separation among retrieval arms. This is insufficient to diagnose
fine ranking improvements. Future tasks need varied difficulty and observable
dependence on supplied evidence, without selecting only cases that favor Cairn.

## A more useful mathematical objective

Let a policy choose searches, reads, navigation and verification actions from
the evidence already observed. Minimize cost subject to a success constraint
on a defined task distribution:

\[
\min_\pi \mathbb E[C(\pi)]\quad
\text{subject to }\Pr(\text{verified task success}\mid\pi)\geq\tau.
\]

This differs from maximizing recall@k or minimizing one response's length.
A practical ledger separates uncached input \(U\), cached input \(K\), output
\(O\), latency \(L\), and amortized indexing cost:

\[
C=p_uU+p_cK+p_oO+\lambda L+C_{\rm index}/Q.
\]

Prices and workload size \(Q\) must come from the deployment. Existing ChatGPT
account usage is not evidence of an API price. Index refreshes and cold starts
also matter.

For intuition only, assume a fixed prefix of \(B\) tokens, \(T\) model calls,
and \(b\) new history tokens retained after each call, without compaction:

\[
I=TB+b\,T(T-1)/2.
\]

This is a simplified accumulation model, not a fit to the recorded sessions;
prefix caching changes billing. It explains why reducing round trips can matter
more than shaving metadata from one reply. Batching everything can also add
irrelevant context or hide a critical exception.

At history \(h\), an action is worth taking only when its expected reduction
in decision loss exceeds its incremental total cost. That suggests choosing a
search, a source bundle or an execution check by expected useful evidence per
cost, with an explicit stopping rule. Reliably estimating that value is the
hard part; naming the objective does not solve the algorithm.

## Cross-disciplinary ideas worth testing

1. **Metareasoning:** spend computation when it improves the eventual decision
   enough to justify its cost. This motivates a search/read/verify/stop policy.
   Applying it here is an engineering hypothesis inspired by
   [Hay et al., Selecting Computations](https://arxiv.org/abs/1207.5879).
2. **Information bottleneck:** compress evidence while retaining information
   needed for the task. The testable analogue is an extractive, cited bundle
   preserving API signatures, examples, conditions and exceptions. Source must
   remain available. The motivation comes from
   [Tishby et al.](https://arxiv.org/abs/physics/0004057); Cairn currently does
   not optimize their mutual-information objective.
3. **Adaptive coverage:** select complementary rather than repeated topical
   evidence. However, two individually unhelpful passages may become essential
   together on a multi-hop task. Adaptive-submodular greedy guarantees cannot
   be claimed without proving the assumptions for this objective. See
   [Golovin and Krause](https://arxiv.org/abs/1003.3967).
4. **Database query planning:** compare alternative access paths and account
   for round-trip costs. The proposed analogue chooses lexical lookup, semantic
   search, structural expansion or batched reads using measured workload costs.
   Tree and cross-reference structure should close missing dependencies, rather
   than merely add an opaque ranking bonus.

There is no evidence for a universally dominant fixed algorithm. Small,
keyword-friendly corpora may favor direct search. A useful adaptive product
must tolerate selecting that simple path. Changing the source access layer or
structure-first guarantees requires a separate architecture decision; no such
architectural change is hidden in these repairs.

## Next experiments, in decision order

1. **Separate retrieval from generation.** Run a model-by-execution-feedback
   factorial with identical tasks, evidence, budgets and grading. Add an
   oracle-evidence diagnostic arm containing sufficient original source, without
   expected answers. Failure with sufficient evidence points away from retrieval
   as the immediate cause. Execution feedback has its own cost.
2. **Separate evidence from acquisition policy.** Replay identical relevant
   passages as individual replies versus bounded source bundles. Then compare
   autonomous tool choice with one controlled initial bundle. Keep total source
   content and verifier constant; measure extra reads, missing requirements,
   cached/uncached usage and success. Account for any evidence-budget difference.
3. **Qualify transport accounting.** Codex events contain textual and structured
   MCP result fields for Cairn. Whether both reach the model is unestablished.
   Use a controlled transport ablation before blaming or removing either;
   event-log duplication is not proof of billed duplication.
4. **Test generalization after freezing a candidate.** Use independently
   reviewed tasks spanning large corpora, terminology mismatch, cross-reference
   chains, version conflicts, distractors, negative evidence and executable
   deliverables. Include easy tasks where rg should win. Separate public-API
   memorization from evidence use with controlled unfamiliar names and documented
   changes. Freeze tasks, corpus revisions, oracle and product hash before runs;
   report every valid attempt and paired uncertainty.
5. **Apply a commercial evidence gate.** On a specified workload, require no
   material success-rate regression and at least 30% measured total-cost
   reduction against the strongest applicable baseline, including amortized
   indexing. Predeclare uncertainty/noninferiority criteria and repeat runs;
   two passing tasks cannot qualify. If the advantage does not survive, narrow
   the market claim or reject the proposed direction.

The existing code passes 537 tests, Ruff and strict mypy (119 source files).
The wheel and source distribution build successfully. The installed-wheel
smoke verifies CLI help, the windowed embedder, and MCP import without eager
LanceDB loading. All 69 Python source hashes match the latest evaluated snapshot.
Additional Python-oracle controls accept a valid configuration and reject
incorrect timeout, pool-limit and environment settings. These checks support
engineering reliability and grading sensitivity, not agent superiority.
