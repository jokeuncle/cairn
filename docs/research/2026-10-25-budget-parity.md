# Budgeted evidence, dependency acquisition and parity screens

Date: 2026-10-25 (Asia/Shanghai). Local, uncommitted experiments following
[the evidence-policy study](2026-10-24-evidence-policy.md).

The later [strong-control/new-project study](2026-10-25-strong-control.md)
adds ten sessions and a cheap structural-link control. All new-project arms
pass 2/2, but higher uncached input prevents a price-independent cost advantage.
The synthetic results below must not be generalized beyond their frozen scope.

## Current decision

The public-API parity screens and the first synthetic long-manual screen do
**not** establish cost parity. Correctness alone has tied the raw-source arm;
cumulative input remains higher. Experimental block extraction is opt-in and
must not be marketed as universally cheaper. The commercial gate is unmet.

A later external one-hop prototype provides a narrower positive signal: on
three new aliases in the same manual, both arms pass 3/3 and Cairn uses 36%
less uncached input than raw, while cumulative input remains 9% higher.
Its same-case comparison against the preceding Cairn snapshot also improves
input usage. This supports further study, not a general or commercial win.

The external CLI interface then passes a qualified two-task screen **and an
unchanged reverse-order repeat**: four accepted attempts per arm over only two
unique task texts. Pooled I/U/O are respectively 49%, 17% and 23% lower than
fresh raw source. This is the first positive bounded token-parity result in
this study. The initial two CLI infrastructure failures remain recorded and
are not treated as savings. Neither the adapter nor the one-hop prototype is
merged into the product, and real-domain/commercial validation is outstanding.

An independent oracle correction also changes the earlier five-task result
from 5/5 to **4/5 for both Cairn and raw source**. This is a correction to the
evaluation, not a new product regression. Historical answers and original
reviews remain available. The unaffected two-task development rounds remain
2/2. New result files consistently include unsuccessful attempts in usage.

## What changed and what was frozen

[ADR-0012](../decisions/0012-budgeted-original-evidence.md) adds an explicit
`repo_context(level="evidence")` view. It selects whole original Markdown
blocks and preserves fitting code examples, source spans and citations under
global/per-section character limits. Recognizable CLI help options retain
their usage/group context; arbitrary code is not split. Existing summary/full
views and the default synopsis remain available.

The first candidate chose sections before packing their blocks. A retained
Ruff development probe showed that discovery rank 2 contained rule-selection
evidence but section preselection removed it. The second candidate jointly
selects blocks from the wider shortlist. Optional caller-supplied focused
`queries` use a shared budget and diminishing marginal per-focus relevance.
The backend neither invents queries nor generates answers. These lexical/rank
proxies do not certify semantic coverage or dependencies.

Both candidates, protocols, source hashes, every answer and JSONL trajectory
are retained. The second source snapshot contains 70 Python files. Its full
verification passed **555 tests**, Ruff and strict mypy (121 source files).
An independently audited runtime-verifier allowlist was subsequently extended
to permit `unittest.mock`; positive/negative controls retain the prohibition
on unrelated `os` imports. This verifier executes audited code; it is not an
untrusted-code sandbox.

## Real-agent results before link expansion

All sessions use actual Codex CLI 0.164.0, `gpt-6.1-sol`, high reasoning,
fresh ephemeral sessions, read-only tools, disabled web and no delegation.
The raw arm uses actual shell/rg over copied selected original Markdown.
Cairn uses a frozen source snapshot through the MCP server and real local
nomic embeddings. Each valid attempt is retained, including unfavorable ones.
Permission to run local inline checks is matched. Tool choice is autonomous.

I is cumulative input, K cached input, U = I − K, and O output. These are CLI
usage counters, not API invoices. Tool invocations are not model turns because
the agent can run calls together. All usage includes failed task attempts.

| Screen | Accepted Cairn / raw | I Cairn / raw | U Cairn / raw | O Cairn / raw |
| --- | --- | ---: | ---: | ---: |
| Budget blocks: five reused public API/config tasks | 4/5 / 4/5 | 1,667,246 / 1,004,879 | 197,166 / 116,687 | 18,071 / 21,219 |
| Joint selection: two reused development tasks | 2/2 / 2/2 | 593,285 / 383,697 | 73,349 / 37,585 | 9,193 / 9,853 |
| Synthetic novel-fact manual: three service aliases | 3/3 / 3/3 | 672,786 / 425,963 | 92,562 / 62,699 | 4,762 / 6,053 |

The joint-selection protocol required aggregate I/U/O no higher than fresh raw
before extending to the other three public tasks. It failed that gate, so the
extension was not run. The synthetic manual was a separately frozen mechanism
diagnostic, not an expansion that bypassed the failed gate. Results are never
pooled into one success or savings number.

[Public screen records](../../benchmarks/repo-quality/parity-results-20261025.json)
and [manual records](../../benchmarks/repo-quality/closed-book-results-20261025.json)
include per-session counters, answer hashes, reviews, protocols and limitations.

### The Ruff oracle correction

The original inheritance grader forced `--config child/ruff.toml` despite the
answer proposing automatic discovery from the repository root. This changes
which configuration governs explicitly passed generated files. Child-only
`force-exclude` does not make the proposed root commands skip those files.
Independent temporary fixtures tested lint and formatting, including an
unformatted generated file. A root-level force-exclude reference passes;
child-only force-exclude and missing exclusion mutations fail.

The qualified automatic-discovery oracle was applied to all five affected
answers across the earlier transfer and new budget rounds, including BM25.
Every affected answer fails the complete task. No acceptance requirement was
weakened; old reviews were not erased. This shared failure does not identify
retrieval as the sole cause. Execution feedback and task integration matter.

### What the long manual does and does not establish

The frozen fictional manual contains 2,294,586 UTF-8 bytes, 290,987 words and
912 sections. Active service records link to a profile, region, lease and
authority rules. Derivation requires override precedence, caps, fallbacks and
maintenance behavior; inactive legacy examples conflict. Exact random dispatch
labels require supplied evidence. Oracle values are never indexed or supplied
to the model. A separately implemented source parser agrees with the generator;
positive and wrong-value/legacy-label controls qualify the checker.

All six answers passed exact JSON fields/types and manual derivation/citation
review. Citations can use stable Cairn anchors or raw file lines resolving
inside the actual supporting section. Whole-session U still increased 48%.
Acquisition initially returns a service and sometimes authority; the agent
then fetches its linked settings sources. Parallel fetches share a dependency
stage, so three fetch calls must not be counted as three model turns.

This fixture has repetitive, coherent padding and all normative records near
the beginning. There are only three aliases in one manual, one attempt each.
It does not represent customer complexity or independent domain generalization.
Summaries are controlled extractive source words rather than the default LLM
summary provider, to isolate retrieval. Real local embedding/index construction
took 72.26 seconds and stored 6,999,378 bytes, about 3.05 times source size before
amortization. Agent skill-reading behavior differed across arms. Whole-product
usage is measured, but retrieval alone is not causally isolated.

## Further primary papers and the next mechanism

These papers were inspected beyond their abstracts, including method and
evaluation sections. Their published gains have not been reproduced here.

| Paper | Transferable idea | Boundary |
| --- | --- | --- |
| [KG²RAG, NAACL 2025](https://aclanthology.org/2025.naacl-long.449.pdf), §§2.2–2.3, 3.1 | Seed retrieval followed by graph expansion and organization can acquire related facts whose similarity to the initial question is low. Its shuffled-entity evaluation also tests dependence on supplied evidence. | Their graph is LLM-extracted; organization uses graph filtering and a cross-encoder. HotpotQA F1 is not executable engineering success. We have not adopted/reproduced their complete system. |
| [PathRAG, 2025 preprint](https://arxiv.org/html/2502.14902v1), §§4–5 | Retain useful relationships while pruning redundant expansion; an unordered pile of neighboring passages can obscure the connection. | Uses LLM keywords and extracted graphs. Its principal comparisons use LLM judges without ground-truth answers. Those win rates cannot establish our exact-value correctness or commercial ROI. |
| [RAPTOR, ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/8a2acd174940dbca361a6398a4f9df91-Paper-Conference.pdf), §3 and Appendix A | Different abstraction levels serve different questions; construction costs must be measured. | Recursive clustering/summaries add indexing cost. Broad thematic QA differs from exact configuration precedence and random labels; adding a summary hierarchy is not the first remedy for observed dependent reads. |

The earlier diminishing-return relevance objective is insufficient for
prerequisites. For example, if two passages a and b are jointly required,
task utility can satisfy F({a}) = F({b}) = 0 and F({a,b}) = 1. The marginal
value of b increases after acquiring a, violating the diminishing-return
assumption. A relevance surrogate may therefore prefer many plausible
fragments while failing to assemble one sufficient evidence set.

The cross-disciplinary analogy is database query planning: a retrieved record
reveals keys for related records, and a deterministic backend can sometimes
resolve those explicit references before another model decision. This is an
engineering hypothesis, not a theorem of universally superior retrieval.
Semantic dependencies without explicit links still need reasoning; links can
also lead to irrelevant or obsolete examples.

## Isolated one-hop prototype

A reversible external source snapshot tests one-hop expansion from original
selected blocks. It follows only same-document explicit fragment links to
unambiguous indexed section IDs/slugs. It returns fitting whole source bodies,
deduplicates them, retains source relationships and reports deferred references.
Code-fence examples and external URLs are not followed. There is no query-time
LLM, generated answer, source-file read or network fetch. Global/per-section/k
caps remain; explicit document caps are respected. In this prototype only,
an unspecified evidence document cap becomes min(k,8).

Five local checks cover cycles/one-hop scope, duplicate links, fenced/external
links, ambiguous/missing targets, Unicode, and budget deferral. Replaying the
three old manual tool arguments returns all five required original sections
in roughly 1,500 source characters. This replay is a local diagnostic, not
an autonomous-agent outcome or an independent held-out result.

The next frozen comparison selected aliases svc004, svc028 and svc008 with
seed 20261026, excluding the previous three. It uses the same manual and a
separately qualified oracle, fresh Cairn/raw attempts, and unchanged model,
tools and permissions. All three happen to have maintenance disabled; earlier
maintenance coverage is not replaced. No source/protocol tuning is allowed
after their answers. The prototype remains outside the product.

All six fresh answers passed exact fields/types plus manual original-source,
derivation and citation review. Each prototype agent obtained its documentation
in one `repo_context` call, with no follow-up document reads. A subsequent
three-session control uses the unchanged preceding Cairn snapshot on the same
three tasks. It also passes 3/3; it is a later, unbalanced-order control, not
an independent replication or a pure one-variable ablation.

| Same three aliases | One-hop prototype MCP | Raw source | Previous Cairn MCP |
| --- | ---: | ---: | ---: |
| Accepted | 3/3 | 3/3 | 3/3 |
| I | 512,162 | 470,826 | 667,838 |
| K | 452,864 | 378,752 | 585,472 |
| U | 59,298 | 92,074 | 82,366 |
| O | 4,932 | 5,738 | 4,620 |
| All tool invocations | 12 | 15 | 19 |

Against raw, I increases 8.78%, U decreases 35.60%, and O decreases 14.05%.
Against the preceding Cairn snapshot, I decreases 23.31% and U decreases
28.01%, while O increases 6.75%. Actual document-call reduction is supported
by traces; all-tool counts also include skills and inline arithmetic checks.
The prototype combines link expansion, unspecified document-cap changes and
guidance, so this comparison cannot isolate one of those components.

With r = cached/uncached input price and q = output/uncached input price,
the prototype-minus-raw token-cost difference is

    ΔC / p_u = −32,776 + 74,112 r − 806 q.

Thus r ≤ 0.44225 is a sufficient condition for token cost no higher for any
q ≥ 0, excluding indexing and latency. This is sensitivity analysis of observed
usage, not an actual price or invoice. It does not satisfy the stronger
price-independent I/U/O screen because I is higher. A cache discount can
change a deployment decision, but it cannot be silently assumed.

[The nine-session record](../../benchmarks/repo-quality/linked-evidence-results-20261025.json)
retains the fresh raw comparison and same-case preceding-Cairn control.
Further limits include at most 32 relationship/deferred diagnostic records
without a truncation flag, unresolved custom HTML fragments, reference
definitions outside selected blocks and cross-document links. Large navigation
pages are unqualified. These are reasons to keep it an external prototype.

## Interface-cost diagnostic and infrastructure failure

A separate external CLI adapter invokes the same frozen dispatch/backend and
prints its complete source JSON through shell stdout. It is a fixture-specific
diagnostic, not a newly released `docsgraph` command. The first four-session
CLI/raw screen failed both CLI tasks: the child agent's read-only sandbox could
not reach the local embedding server. Each agent honestly returned unverified
null fields; neither retrieved source. The raw answers passed source review.
Low token counts from these failed CLI sessions are **not** savings. Every
original answer and failure remains in `codex/cli-probe/`.

Environment recovery was qualified before another model attempt. A temporary,
per-command named profile extends read-only filesystem permissions and enables
the command network proxy with only `127.0.0.1` allowed. The exact backend query
then returns all five source sections inside the sandbox. A write probe is
denied, and `http://example.com` returns a proxy 403 with `not_allowed` and
`baseline_policy`. No global config, authentication or approval bypass changes.
This follows the [official permission-profile configuration](https://developers.openai.com/codex/config-reference/).

Four new recovery sessions are separately frozen with the same local-only
profile in both CLI and raw arms, the unchanged adapter/source and the first
two known aliases. They do not overwrite the failed attempts. This tests an
interface/harness bundle, including prompt instructions, schema delivery and
JSON serialization; it cannot establish that one serialization field was
responsible. It also differs from the earlier disabled-network permission
profile and must not be pooled with that screen.

Both recovered answers pass exact fields and manual derivation/citation review.
The follow-up freezes the same source, prompts, adapter, permissions and two
tasks, reverses CLI/raw order per case, and retains every attempt. Both repeat
answers also pass. No further source tuning or trial selection followed.

| Qualified CLI screen | CLI accepted / raw | I CLI / raw | U CLI / raw | O CLI / raw |
| --- | --- | ---: | ---: | ---: |
| First qualified round | 2/2 / 2/2 | 160,189 / 320,202 | 21,949 / 28,106 | 2,383 / 2,952 |
| Unchanged reverse-order repeat | 2/2 / 2/2 | 161,831 / 306,344 | 33,447 / 38,696 | 2,459 / 3,307 |
| Pooled qualified attempts | 4/4 / 4/4 | 322,020 / 626,546 | 55,396 / 66,802 | 4,842 / 6,259 |

Each qualified round separately meets the I/U/O screen. Pooled I decreases
48.60%, U 17.07%, and O 22.64%. There are **two unique task texts**, not four
independent tasks. U varies substantially between rounds; these samples do not
establish a distributional noninferiority bound. Indexing, query compute,
storage and live-deployment prices are still outside the token-only claim.
Raw has normal shell/rg access and chooses its own workflow; it is not forced
into a literal-search-only MCP baseline.

The [complete CLI diagnostic record](../../benchmarks/repo-quality/cli-interface-results-20261025.json)
includes all three rounds, including infrastructure failures, source hashes,
protocols, actual usage and permission qualification. Across all attempted
CLI sessions, including the failed original environment, acceptance is 4/6
versus raw 6/6; only qualified steady-state attempts are 4/4 each. Recovery is
a disclosed change in environment, not a hidden replacement of failed answers.

The supported product hypothesis is connected original evidence acquired
through a lightweight interface. The result does **not** isolate embedding
quality, one JSON field, the link algorithm or skill behavior as the sole
cause. It also does not prove superiority over a cheap raw-source helper that
bundles explicit links. That stronger baseline, unfamiliar semantic needs,
cross-document scope, real engineering deliverables and portable provider
configuration remain necessary before commercial adoption. The controlled
manual puts simple identifiers and all normative records near its beginning;
padding it does not automatically create a hard retrieval problem.

## Parity and the remaining gate

Ignoring latency/indexing temporarily, input cost is

    p_u U + p_c K = (p_u − p_c) U + p_c I.

For nonnegative output prices and 0 ≤ p_c ≤ p_u, no increase in each of I,
U and O is a price-independent sufficient condition for token-cost parity.
It is not necessary at a particular price. The first three screens fail it;
the qualified CLI screen and its fixed repeat pass it on their narrow workload.
Lower O alone does not establish cheaper sessions. Index cost,
latency, repeated trials and acceptance remain separate requirements.

There is no demonstrated ultimate method. The supported next question is
whether bounded acquisition of **connected original evidence** can remove a
real dependency stage without losing scope or task acceptance. If the external
prototype fails outside this fixture, retain those results rather than merge
another unproven default. The experimental source and a reviewable
`link-spike/prototype.patch` remain external; the product still contains the
70-file budget-block snapshot. This phase ends after the predeclared repeat,
with no default interface change or remote publication.

Local artifact root:
`/Users/ksher/self-projects/cairn-evaluations/rescue-20261024/parity-20261025/`.
Complete prompts/JSONL/answers are in sibling `navigation-round/codex/`;
tracked summaries do not substitute for portable replay infrastructure.
