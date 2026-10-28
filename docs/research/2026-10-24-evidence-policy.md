# Evidence policy research and experiments

Started 2026-10-24; completed across midnight on 2026-10-25 (Asia/Shanghai).

The subsequent [budget and dependency study](2026-10-25-budget-parity.md)
records newer source snapshots, failed parity screens and separate long-manual
experiments. Counts in this report identify the earlier snapshot.

**Acceptance correction, 2026-10-25:** the original Ruff-inheritance grader
forced a configuration file and missed the automatic-discovery context of the
proposed root-directory commands. Explicit generated files are not excluded in
that context. Corrected transfer acceptance is **2/3 per arm**, and five-task
Cairn/raw acceptance is **4/5 each**. Original reviews/answers are retained;
machine-readable results contain both the historical and corrected decisions.

## Question and acceptance contract

Can Cairn improve complete agent-task success or reduce whole-session cost,
without losing original evidence, scope conditions or citations? The immediate
bounded experiment repairs completeness reporting for the existing explicit
full context option. It adds no tool, query-time model or persistent format.
Acceptance requires executable deliverables plus source/explanation review;
retrieval overlap alone is insufficient. Commercial superiority is not assumed.

This continues the [earlier cost diagnosis](../agent-cost-diagnosis.md).
All model attempts, including invalid tool arguments and unfavorable outcomes,
remain in the local experiment directory. No remote publication is performed.

## Papers inspected and what transfers

The following primary papers were inspected at method/evaluation level. Their
reported results are not Cairn measurements, and their full systems have not
been reproduced here. A mechanism can inspire a controlled ablation without
justifying adoption of its entire architecture.

| Work | Relevant mechanism | Applicability limit / experiment implication |
| --- | --- | --- |
| [IRCoT, ACL 2023](https://aclanthology.org/2023.acl-long.557.pdf) | Interleaves retrieval with reasoning; later queries depend on earlier evidence. | Dependent questions cannot all be independently decomposed upfront. Keep adaptive follow-up possible. Their QA protocol is not executable engineering-task acceptance. |
| [Adaptive-RAG, NAACL 2024](https://aclanthology.org/2024.naacl-long.389.pdf) | Learns selection among no-, single-, and multi-step retrieval using a complexity classifier. | The classifier has training and inference costs. Cairn's citation-required tasks cannot silently choose an unsupported answer just because a model appears to know it. |
| [DRAGIN, ACL 2024](https://aclanthology.org/2024.acl-long.702.pdf) | Combines token entropy, attention-derived influence and semantic filtering to trigger retrieval. | Requires internal model signals unavailable through our current Codex CLI tool interface. It is not a drop-in routing rule for an MCP server. |
| [HippoRAG 2, 2025](https://arxiv.org/html/2502.14802v2) | Passage/triple integration, recognition filtering and graph propagation support associative retrieval. | Has LLM extraction/filtering and indexing costs. Graph sophistication is not free; directly adding its query-time LLM stage would conflict with Cairn's current boundaries. |
| [A-RAG, 2026](https://arxiv.org/html/2602.03442v1) | Fine-grained search/read interfaces and a tracker avoid returning already-read chunks. | Its loop deliberately avoids parallel tool calls. Our traces already parallelize. A duplicate-read notification still has protocol/history costs; zero new passage tokens does not imply zero session cost. |
| [LongLLMLingua, ACL 2024](https://aclanthology.org/2024.acl-long.91.pdf) | Question-aware coarse selection and fine token compression increase relevant information density. | Compression itself costs inference and can damage exact examples. Test source extraction and code/condition retention before adding another model. |
| [Efficiency vs. Verifiability, CustomNLP4U 2026](https://aclanthology.org/2026.customnlp4u-1.19.pdf) | Evaluates answer quality separately from citation grounding under compression. | Workshop evidence, not a universal result. Its grounding-preserving variant uses mild compression; it does not establish aggressive compression with unchanged grounding. |
| [BRIGHT, revised 2025](https://arxiv.org/html/2407.12883v4) | Relevance can require reasoning beyond lexical or semantic similarity, including coding questions. | Our short public API/config cases do not cover this whole difficulty distribution. Do not use their pass rate as a retrieval-generalization estimate. |
| [BRIGHT-Pro / RTriever, 2026 preprint](https://arxiv.org/html/2605.04018v1) | Multi-aspect gold evidence, novelty-sensitive evaluation and agentic retrieval expose missing aspects and repeated evidence. | Supports measuring complementary evidence. Its aspect/LLM judging is not a substitute for executing code/configuration. Training a new retriever is a separate, costly hypothesis. |
| [Are LLM-Based Retrievers Worth Their Cost?, 2026 preprint](https://arxiv.org/html/2604.03676v1) | Measures cold indexing, latency, perturbations and top-score discrimination of query success. | Reported top-score AUROC is not formal probability calibration. Do not route or stop by treating raw retrieval scores as success probabilities. |

## More than divide and conquer

Independent requirement groups can be acquired together, but dependency-driven
requirements must remain sequential. A target configuration can depend on a
version, inherited scope or exception discovered only after reading another
section. Decomposition without recombining these conditions can produce locally
plausible fragments and a globally incorrect deliverable.

The proposed policy has three separable responsibilities:

1. The agent identifies information needs and dependencies, without receiving
   hidden benchmark labels.
2. Cairn supplies bounded, cited original evidence with explicit scope and
   completeness; it does not generate the answer or certify semantic coverage.
3. The agent integrates the evidence and verifies the final artifact. It stops
   when requirements are supported and permitted checks pass, rather than
   exhausting navigation links.

An aspect-selection surrogate illustrates the difference from repeating top
matches. For nonnegative relevance estimates r and weights w, let

\[
F(S)=\sum_i w_i\max_{s\in S} r_i(s).
\]

With fixed r, this objective has diminishing returns: once an aspect already
has a strong passage, another similar passage adds little. A gain-per-cost
selection heuristic can favor missing aspects. However, these relevance values
are proxies, not calibrated task success. Prerequisite interactions and changing
queries violate the simple fixed-relevance model. No approximation guarantee
for real agent success follows from this formula.

Structure is potentially useful for preserving a passage's scope and explicit
dependencies. It should earn its cost on scope-sensitive cases; the product's
structure-first thesis is not itself experimental proof of an advantage.

## A trace-based correction

The HTTPX second-iteration trace starts six searches before any finishes, and
later starts eight source reads before they finish. Ruff also groups reads.
Thus 20 or 13 tool invocations are not 20 or 13 model turns. Earlier invocation
counts remain accurate, but a sequential cost model cannot be fitted to them.
Tool grouping is a diagnostic of overlap, not an exact model-forward-pass count.

The cost ledger remains uncached input U, cached input K, output O, latency,
and amortized indexing. Reducing a response or invocation count is only a
hypothesis until complete-session usage and acceptance are measured.

## Candidate and experiment freeze

[ADR-0011](../decisions/0011-explicit-context-completeness.md) adds explicit
`truncated`, `source_characters`, and `content_scope` to requested full context
sections. Complete original bodies can be reused directly; descendant bodies
are separate. The MCP descriptions explain this existing option. Defaults,
signatures, ranking and source selection remain unchanged.

Six new parameterized checks cover empty, complete and truncated Unicode parent
bodies in compact and diagnostic modes, including citations and exclusion of
child-only conditions. The full suite passes **543 tests**; Ruff and strict
mypy pass. A real-agent source snapshot contains 69 Python files.

Before new answers, source hashes and protocols were frozen for:

- two development task texts (HTTPX client, Ruff CI), Cairn and actual rg/raw
  source, fresh attempts with autonomous tool choice;
- three transfer stress task texts (Uvicorn factory, Ruff inheritance, Starlette
  shared lifespan state), Cairn/BM25/actual rg, rotated arm order.

The transfer task texts were already used in earlier Qwen experiments. They
are new to this Codex experiment, **not untouched held-out cases**. No source
or protocol tuning is permitted after inspecting transfer answers. Standard
budgets, local execution permissions and model are retained. Invalid calls
count toward budgets; valid failures are never silently replaced.

Independent graders include previously qualified Uvicorn/Ruff checks and a
Starlette runtime grader qualified with a working reference plus a mutation
that loses state across requests. Manual completeness and citation review is
still required. Live network/deployment behavior is outside this evaluation.

Local evidence:
`/Users/example/project`
and `rescue-20261024/paper-round/`. These are machine-local artifact locations.
Completed results and their failure to establish overall savings are recorded below.

## Development results

All four fresh development answers passed independent execution and manual
source/deliverable review. Agents autonomously used `repo_context(level="full")`.
HTTPX made four context calls (including an invalid 8,500-character request that
was corrected within the budget), instead of the earlier nine searches plus
eight source reads. Total calls fell from 20 to 7. This is an observed behavior
change, not an isolated causal effect of one metadata field.

| Two-task totals | Cairn candidate | Fresh actual rg/raw |
| --- | ---: | ---: |
| Accepted | 2/2 | 2/2 |
| Tool invocations | 16 | 10 |
| Input tokens | 544,327 | 291,039 |
| Cached input | 467,840 | 247,168 |
| Uncached input | 76,487 | 43,871 |
| Output tokens | 6,317 | 7,720 |

There is still no whole-workload cost advantage. HTTPX improved against Cairn's
previous iteration, but Ruff processed long configuration/CLI bodies and cost
more. Of 45,372 original-body characters returned by Ruff context calls,
5,310 repeated an identical body and additional reads repeated shorter prefixes
of earlier bodies. Whole-body duplication is only part of the issue: irrelevant
parts of long bodies and repeated partial prefixes also consume context.
Do not claim that simple whole-body deduplication alone will close the gap.

[Machine-readable results](../../benchmarks/repo-quality/paper-context-results-20261024.json)
preserve answer hashes, independent reviews, source snapshot and protocols.

## Transport and oracle diagnostics

A controlled MCP fixture returned the same structured source under identical
tool/output schemas. One variant also returned its full textual JSON; the
other returned only a short textual notice pointing to structured content.
The exact source marker was absent from the prompt. Each completed run made
exactly one source call and no shell call.

The full-text control returned the marker correctly. Both brief-text runs
failed to retrieve it despite the MCP client independently confirming that the
structured payload contained the marker and all 160 records. A later full-text
repeat failed during the required-server handshake, before any tool invocation;
it is retained as an infrastructure failure, not a model task failure.

This small fixture does not prove the client's internal serialization path.
It does refute treating a brief-text/structured-only representation as an
already-qualified replacement for this client. No product transport change was
made. Event logs containing two fields are insufficient evidence that Cairn is
billed for two copies of source text.

The Uvicorn grader also exposed a grammar gap: valid `UVICORN_RELOAD=false`
prefixes were not recognized as commands. The original grader is preserved.
The amended parser supports direct and `env`-prefixed assignments, with six
positive/negative controls. Reload-enabled, invalid-flag and wrong-concurrency
controls still fail. All three arms use the amended parser; regrading all six
earlier Qwen Uvicorn outputs leaves their failures unchanged. No task requirement
was weakened and no generated server command was actually started.

## Transfer results and the commercial gate

All nine transfer sessions completed. After correcting the discovery-context
grader, every arm passes two of three complete tasks. Ruff inheritance fails
explicit generated-file handling from the root. All three delivered
Starlette test programs were also executed independently, with networking
blocked. These are three task texts, not nine independent tasks.

| Transfer totals | Cairn | BM25 | Actual rg/raw |
| --- | ---: | ---: | ---: |
| Accepted | 2/3 | 2/3 | 2/3 |
| Input tokens | 1,126,753 | 921,804 | 613,165 |
| Cached input | 1,025,792 | 796,672 | 521,216 |
| Uncached input | 100,961 | 125,132 | 91,949 |
| Output tokens | 13,028 | 13,534 | 14,802 |
| Tool invocations | 31 | 46 | 21 |

There is a local positive result: Uvicorn used 22,420 uncached input tokens
with Cairn versus 32,393 with raw source (about 31% fewer). However, cached
input was 267,648 versus 125,696. This is not a demonstrated 31% reduction in
total cost. The Ruff-inheritance and Starlette tasks still used more uncached
input with Cairn than with raw source. Verification effort also varied across
autonomous agents, despite identical permissions and task requirements.

Across all five Cairn/raw task pairs in this round, both passed 4/5. Cairn used
177,448 uncached input tokens versus 135,820 for raw (about 31% more), and
1,493,632 cached input versus 768,384. Output was lower: 19,345 versus 22,522.
The success-rate ceiling persists and overall cost superiority is unproven.

For a price-sensitivity check, exclude latency and indexing temporarily and
let r be cached/uncached input price and q be output/uncached input price.
The measured token-cost difference, in uncached-input-price units, is:

\[
\Delta C/p_u=41{,}628+725{,}248r-3{,}177q.
\]

This is an accounting identity for all attempts, including the failed task,
not a cost-to-success claim or a price assumption. Without
latency/indexing, Cairn is cheaper only above the break-even line
q > 13.10 + 228.28r. Actual deployment prices must be supplied; an output-token
reduction alone is insufficient to announce savings. One run per case cannot
qualify a latency advantage or establish repeatability.

**The proposed commercial gate is not met.** Keep ADR-0011 as a correctness
repair and the changed guidance as an evaluated candidate; do not market full
context as universally cheaper. No new batch-query API or transport shortcut
was shipped based on these experiments.

The next hypothesis should target the observed long-body problem: select
bounded original paragraphs/examples while retaining their scope, exception
and citation dependencies, and avoid re-delivering overlapping prefixes.
Prove the evidence budget and dependency behavior on frozen cases before
changing public interfaces. Do not replace this with arbitrary shorter-body
ranking bonuses, which could suppress a long but indispensable condition.

Evaluation also needs long structured documents, distractors, version/scope
conflicts and controlled unfamiliar facts that require the supplied evidence.
The current public API tasks are useful regression checks but cannot establish
the product's claimed large-document advantage. Freeze independent oracles and
product hashes, keep easy cases where rg wins, and compare against both raw and
BM25 rather than only Cairn's own predecessor. The model-by-execution-feedback
factorial from the earlier diagnosis remains unperformed.
