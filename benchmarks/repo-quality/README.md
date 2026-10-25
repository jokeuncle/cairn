# Repository evidence and QA regression protocol

## Latest working-tree graph and analysis studies

[document-links-results-20261025.json](document-links-results-20261025.json)
records six accepted real-Agent sessions over two reference-audit targets,
including an independent on-demand graph helper and raw originals. The graph
matches80 source document-pair counts. Its strict I/U/O gate fails; a separate
incomplete adapter-shadowing infrastructure attempt is retained outside those
six sessions, with unfinished usage unknown.

[reference-impact-results-20261025.json](reference-impact-results-20261025.json)
records eight accepted sessions on two new target instances of that known task
template: native analysis, graph-only Cairn, matched independent analysis helper
and raw originals. The helper computes the same graph mathematics without
Cairn/index/models/oracles. All42 possible target documents qualify against
independent original-source checks. The native arm fails its strict cost gate.
All847 frozen artifacts, including workspace sources, match after completion.

These14 sessions are four target-document instances of one graph-analysis
template on two pinned public projects, not14 independent tasks or customer
workloads. Both native Agents also fetch the full graph and independently
recompute results. Three invalid-hop errors in the matched control stay included.
Source/menu differences, skill reads, nested queries and autonomous verification
choices are disclosed; observed command events are not model turns or a count
of all nested CLI calls. Do not compare different-target phases as a causal
before/after feature ablation.

Source/runner/oracle/answer/events/review artifacts are under
`/Users/ksher/self-projects/cairn-evaluations/rescue-20261024/document-links-20261025/`
(the accepted comparison is `recovery-round/`) and
`/Users/ksher/self-projects/cairn-evaluations/rescue-20261024/reference-impact-20261025/`.
The machine-specific paths are evidence locations, not portable installation
requirements. See the [public ledger](../../docs/research/README.md),
[graph report](../../docs/research/2026-10-25-document-links.md), and
[analysis report](../../docs/research/2026-10-25-reference-impact.md).

The older protocols and their failures below remain unchanged. Initial index
construction/storage, warm model setup and controlled summaries are separate
from model-free cached query availability. A price condition is not measured
commercial TCO or generalization certification.

`cases.json` freezes 36 questions over selected documents in HTTPX, Starlette
and MkDocs, with source revisions and document paths. HTTPX is the repair set;
the other two question sets were frozen before their first retrieval/QA runs.
They are small engineering checks, not a general accuracy leaderboard.

Use the existing sync workflow to index a local checkout at the recorded
revision. Select the `docs` paths from the case file in `.cairn/config.toml`
when reproducing the small reference corpus; indexing the whole repository
changes ranking and makes the numbers incomparable.

```sh
# Set CAIRN_EMBED_* for the same embedder used during indexing.
python scripts/eval_repo_quality.py --repo /path/to/httpx --corpus httpx \
  --out /tmp/httpx-quality.json

# Also set CAIRN_LLM_* for an OpenAI-compatible local or hosted answer model.
python scripts/eval_repo_quality.py --repo /path/to/httpx --corpus httpx \
  --qa --out /tmp/httpx-qa.json
```

`--query-prefix` explicitly supplies an embedding model's query task prefix.
For example, the reference nomic model used `search_document: ` at indexing
and `search_query: ` at retrieval, via an `Embedder` protocol adapter. Do not
mix prefixed queries with incompatible document vectors. Other providers may
need neither prefix. Prefix handling in this evaluation script is explicit;
it does not change server configuration.

The reference run uses local Qwen3-4B-Instruct-2507 Q4_K_M for summaries and
answers, nomic-embed-text-v1.5 Q4_K_M (768 dimensions), and top five hits.
Answers use temperature 0, seed 42 and 200 output tokens. The frozen HTTPX QA
subset selects indices 0,2,...,22; the two held-out suites use every question.
Identical existing summaries may be reused only when model, title, body and
summary level match. Query answers must never be used to construct the index.

Required-fact markers are a screening metric. They can miss correct paraphrases
or accept words appearing in the wrong relationship. Review the saved answers
and original sources before reporting QA correctness. A refusal on an answerable
question fails the QA task. Never expose `facts` to the answer model.

Preserve source headings and paths in **every** QA context. A section's name
may itself be the API/configuration answer. Early experiments stripped Cairn's
heading metadata while BM25 retained Markdown headings; those scores are not
the final comparison. The corrected protocol is rerun for both original and
repaired code. Query echoes and ranking explanations are not source evidence.

The full reference comparison also uses independently split, preamble-preserving
BM25 sections and 512-word chunks with the same semantic embedder. Raw response
token counts include metadata and use the answer model's tokenizer. The shipped
script reports the product's token estimate; that is not an exact model token
count or a complete agent-session bill. `--fake` is only an offline retrieval
smoke check and cannot establish semantic quality.

## Recorded repair run and autonomous cases

See [results-20261024.json](results-20261024.json) for the corrected original vs
repaired comparison, [the review](../../docs/retrieval-reliability.md) for
interpretation, and [complex-results-20261024.json](complex-results-20261024.json)
for autonomous MCP outcomes. The QA script above supplies retrieved evidence to
an answer model; its score is **not** an autonomous tool-use score.

`complex-cases.json` freezes three multi-document/multi-constraint tasks before
their first execution. Its checks are reviewer references and must never enter
the agent prompt. The autonomous runner sends only `task`, real MCP schemas and
instructions. It permits 16 tool rounds, 24 total calls, parallel calls within
that budget, and one final synthesis. The reference model uses a 32,768-token
context, temperature 0, seed 42 and 1,800 output tokens per response. Preserve
finish reasons, all tool replies, errors and generated code. Execute reviewed
Python without outbound networking; do not execute deployment commands.

The reference final attempt passed **0/3** complete tasks. Earlier diagnostic
runs with a hidden parallel-call restriction or insufficient per-slot context
are excluded; they remain in the local artifact directory. Never silently retry
valid failures until a successful trace appears. Source revisions/selected
documents are the same as in `cases.json`. These cases establish failures on
this setup, not an estimated population failure rate or a model comparison.

## Later stress tests and actual Codex sessions

`agent-heldout-20261024.json`, `agent-corpora-20261024.json` and
`agent-protocol-20261024.json` freeze six composed tasks and their source
selection for the later 4B stress run. Each of Cairn, independent BM25 and a
literal-search MCP baseline failed all six complete tasks. Literal MCP search
is not the actual `rg` baseline used below. Invalid code/configuration counts as
failure even if an answer contains every required keyword. The model did not
have an execution tool during these runs.

[agent-cost-results-20261024.json](agent-cost-results-20261024.json) records
twelve actual Codex CLI sessions: two tasks, three evidence arms and two
development iterations. Every arm passed both tasks in each iteration; Cairn
did not establish a cost advantage. These are **two independent task texts**,
not twelve held-out tasks. The report includes both iterations, answer and
source hashes, tool budgets, model/runtime settings and usage counters.
Read the [diagnosis](../../docs/agent-cost-diagnosis.md) before interpreting
the totals.

[bulk-source-diagnostic-20261024.json](bulk-source-diagnostic-20261024.json)
records two additional diagnostic sessions with every selected original document
supplied verbatim in the first prompt. Both tasks passed, but input effects
diverged and combined uncached input increased. This is a bulk-source baseline,
not a new product feature or a held-out win. Its protocol and traces are in the
same local artifact directory under `bulk-diagnostic*`.

The Codex protocol uses fresh ephemeral sessions with existing authentication,
`--ignore-user-config --sandbox read-only --json`, disabled web access and no
delegation. It supplies only the task and source-access rules, never oracle
checks. Both MCP arms expose a controlled core-tool subset; the raw arm uses
actual shell/rg over copied selected original Markdown. The second iteration
also exposes the existing `read_range`. All arms can run local Python checks.
This differs from the 4B harness and prevents attributing their outcome gap
solely to model size. CLI usage includes shared harness/skill overhead and
reports cumulative input, cached input and output separately.

Full prompts, answers, JSONL tool events, runners, execution reviews and retained
startup failures are local artifacts under
`/Users/ksher/self-projects/cairn-evaluations/rescue-20261024/navigation-round/codex/`.
`runs/` is iteration 1; `round2/` is iteration 2. These locations are specific
to this machine. The tracked summaries do not substitute for replayable traces
on another machine. A future portable benchmark must reproduce selected corpus
revisions and snapshot hashes, rather than silently testing the latest branch.

After manually auditing a generated primary Python block, the independent
runtime verifier can check the corresponding Python task:

```sh
python scripts/verify_agent_output.py --answer /path/to/answer.txt \
  --case-id httpx-service-client --out /tmp/runtime-review.json \
  --run-audited-code
```

This executes code and is not an untrusted-code sandbox. A passing runtime
check still requires manual explanation/citation review. The independent Ruff
oracle also executes temporary config fixtures; positive controls qualified
it before acceptance. Live deployments and network negotiation are excluded.

## Paper-informed completeness experiment

[paper-context-results-20261024.json](paper-context-results-20261024.json)
records 13 fresh Codex sessions: two development task texts with Cairn/raw and
three transfer task texts with Cairn/BM25/raw. A later grader correction changes
transfer acceptance to 2/3 per arm and Cairn/raw five-task acceptance to 4/5;
Ruff automatic discovery does not exclude explicit generated files as proposed.
Historical reviews are retained beside corrected execution reviews. This does not establish a success-rate
advantage; across the five Cairn/raw pairs, Cairn still uses more input tokens.
Separate cached/uncached/output counters are retained. The three transfer texts
were already exposed during Qwen development, so this is not untouched held-out
validation. No protocol/source tuning followed their Codex answers.

The [paper review and full interpretation](../../docs/research/2026-10-24-evidence-policy.md)
distinguishes parallel calls from model turns, long-body over-reading, transport
diagnostics and the amended/qualified Uvicorn command parser. A controlled
brief-text/structured-payload experiment failed source-marker retrieval twice;
one separate control failed at startup. All attempts remain recorded. No product
transport shortcut was adopted. Frozen source, protocols, prompts and JSONL
events are under the same local `codex/paper-*` artifact paths; diagnostic
controls are under `rescue-20261024/paper-round/`.

## Budgeted blocks and controlled novel facts

[parity-results-20261025.json](parity-results-20261025.json) retains the five-task
budget-block screen (4/5 per arm) and two-task joint-selection screen (2/2 per
arm). Both use more input than fresh actual rg/raw. The joint candidate failed
its predeclared I/U/O expansion gate; the remaining public tasks were not run.

[closed-book-results-20261025.json](closed-book-results-20261025.json) records a
separately frozen synthetic 2.29 MB manual with new random facts, linked
settings, precedence rules and conflicting legacy examples. Both arms pass
3/3 including manual citation review; Cairn still consumes more input. This
repetitive one-manual mechanism diagnostic is not customer/generalization or
commercial validation. Controlled extractive summaries and real embeddings
are disclosed, alongside index construction costs and full-session usage.

The [current report](../../docs/research/2026-10-25-budget-parity.md) documents
the qualified Ruff automatic-discovery oracle correction, the 555-test
product snapshot, primary-paper implications and the separate external
one-hop source-link prototype. Prototype evidence must not be presented as a
released product feature or successful parity gate before qualification.

[linked-evidence-results-20261025.json](linked-evidence-results-20261025.json)
records the external prototype's three new aliases and same-case preceding
Cairn control. [cli-interface-results-20261025.json](cli-interface-results-20261025.json)
retains a failed sandbox/connectivity round and two qualified CLI/raw rounds,
the second using reversed arm order. Both qualified rounds pass two reused
synthetic tasks and the aggregate I/U/O screen; pooled qualified attempts use
49% less I, 17% less U and 23% less O. There are only two unique task texts,
and all initial CLI failures remain visible. This supports a narrow interface
and acquisition hypothesis, not real-domain/commercial superiority or a
released CLI feature. The product source and external prototype remain distinct.

## Strong structural control and new coding tasks

[strong-control-results-20261025.json](strong-control-results-20261025.json)
records four known-alias sessions and six new Pydantic/Typer coding sessions.
The independent helper parses original Markdown and computes BM25/explicit
links on demand, with no offline vector/LLM index. Both CLI backends obtain the
known-alias evidence in one call; extra process-skill reads confound algorithm
attribution. On the new tasks, all three arms pass 2/2 under qualified execution
and source review. Cairn has lower I but higher U than both controls, so a
price-independent token-parity claim is unsupported. See the
[current interpretation](../../docs/research/2026-10-25-strong-control.md).

## Shared product CLI and cached lexical retrieval

The [ten-session screen](../../docs/research/2026-10-25-lean-cli.md) freezes the
actual installed product CLI across hybrid/lexical and JSON/text, with fresh
raw-source controls. Both known development tasks pass in every arm. The
preselected lexical/text candidate fails the I/U/O cost gate; a lower uncached
input result in the secondary hybrid/text cell is exploratory. All seven CLI
argument errors and differing process-skill reads are retained.

[Machine-readable sessions and independent reviews](lean-cli-results-20261025.json)
include I/K/U/O, source acceptance and invocation counts. Lexical mode proves
endpoint-free cached queries, while indexing/storage and commercial advantage
remain separate questions.
