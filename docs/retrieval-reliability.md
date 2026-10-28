# Retrieval repair: measured results and limits

This records the first repair phase. See the later
[real-agent cost diagnosis](agent-cost-diagnosis.md) for Codex comparisons,
the current verification count, and the remaining lack of a cost advantage.

Evaluation date: 2026-10-24. Baseline: `e73210be5ccc6f6c3619dfeb677686ae9b7239a2`
(`0.1.0a12`). Results below describe the local, uncommitted repair, not a
published release. The acceptance decision is **useful documentation retrieval;
autonomous complex engineering reliability not established**.

## What changed

- Preserve headingless Markdown and preambles, excluding YAML frontmatter,
  without changing existing heading IDs. Old indexes rebuild on the next sync.
- Search complete section bodies; normalize sparse matching against the whole
  query and choose evidence using distinct term coverage.
- Return cited sections once in default `repo_context`, with bounded original
  evidence. Diagnostic relationships/rankings remain available with
  `include_details=true`; complete original sections remain explicit reads.
- Accept returned `cairn://doc/section` citations directly in MCP section inputs.
  A genuine agent previously passed these as IDs, received errors, and wrongly
  concluded the documentation was missing. Conflicting namespaces are rejected.

No query-time answer generation, new runtime dependency, repository-specific
ranking rule, or source document modification was introduced. See
[ADR-0004](decisions/0004-lossless-ingest-compact-context.md) for the contract.

## Controlled retrieval and QA

Local real models: Qwen3-4B-Instruct-2507 Q4_K_M for summaries and answers;
nomic-embed-text-v1.5 Q4_K_M, 768 dimensions, with explicit document/query task
prefixes for embeddings. No fake embedder was used for these quality results.
Answers used temperature 0, seed 42, and a 200-token output budget.

HTTPX has 24 frozen retrieval questions and a fixed alternating 12-question QA
subset. It is the repair/development set. Six questions each over Starlette and
MkDocs were frozen before their first runs. These are **small selected document
collections**, not full-repository or randomly sampled production benchmarks.
Source revisions, paths, questions and protocol are in
[the benchmark directory](../benchmarks/repo-quality/README.md).

The QA counts check the requested key facts and were reviewed against answers
and source text. They do not mean every sentence or code example is correct.
Literal fact checks alone can accept an incorrect relationship; they are only a
screening metric. All QA inputs retain source headings and paths. An earlier
experiment stripped Cairn headings but retained BM25 headings; both original
and repaired code were rerun using the corrected protocol. Earlier scores are
superseded, not mixed into this table.

| Corpus / approach | Requested QA facts complete | Median raw response tokens |
|---|---:|---:|
| HTTPX original default | 3/12 | 8,051.5 |
| HTTPX repaired default | 11/12 | 1,431.5 |
| HTTPX repaired full | 11/12 | 1,446 |
| HTTPX same-embedder vector chunks | 11/12 | 3,966.5 |
| HTTPX section BM25 | 11/12 | 1,180 |
| Starlette repaired default | 6/6 | 1,339 |
| Starlette repaired full | 6/6 | 1,917.5 |
| Starlette vector chunks / BM25 | 6/6 each | 3,858 / 1,444 |
| MkDocs repaired default | 4/6 | 1,661.5 |
| MkDocs repaired full | 5/6 | 2,315.5 |
| MkDocs vector chunks / BM25 | 4/6 each | 4,259 / 1,892.5 |

Tokens use the answer model's tokenizer and include library response metadata.
The HTTPX default response shrank about 82%. The actual stdio MCP response also
includes a trace: its repaired HTTPX median was **1,967 tokens** over 24 queries.
These are retrieval payloads, not total session tokens, latency or money saved.

The fixed HTTPX QA target (11/12) and actual MCP median budget (<2,000) were met.
The other two corpora total 10/12 with default context, 11/12 with explicit full
context; both flat baselines achieve 10/12. This shows some transfer, not a
general accuracy advantage over BM25. No pre-repair held-out comparison was
run, so the held-out numbers do not measure a causal before/after improvement.

Known failures include Chinese queries against English sources with this
English-oriented embedder, MkDocs `docs_dir`, and a relative inheritance path
that default context did not recover. Full context fixed the inheritance case
but not the directory question. An HTTP/2 answer with correct requested facts
still used an inaccurate illustrative protocol string. Do not interpret 11/12
as eleven entirely flawless answers.

## Real MCP agent tests

The autonomous agent receives the server's actual tool schemas/instructions,
chooses tool names and arguments, and consumes real MCP replies. This is
separate from supplying a predetermined retrieval result to the QA model.

A known MkDocs source/output-directory probe passed after the citation-input
repair: five model rounds, four tool calls, recovery from one invented section
ID through a sibling read, then correct `docs_dir: docs` and `site_dir: site`.
This is a diagnostic success on a known failure, not another held-out sample.

Three additional frozen, multi-constraint cases combine HTTPX client
configuration, Starlette lifespan/background tasks/thread pools, and MkDocs
inheritance/deployment. Each uses the same 4B model through real MCP with a
32,768-token context, 16 tool rounds, 24 total tool attempts, temperature 0,
seed 42, and 1,800 output tokens per model response. Parallel calls are allowed
within the total budget. There is one valid final attempt per case, with no
retry-until-success selection. Generated Python is reviewed, compiled, and run
locally with outbound networking blocked; deployment commands are never run.

Earlier diagnostic runs hit a hidden driver restriction on parallel calls or
the server's 16K per-sequence context limit. They are retained but excluded from
the comparable final capability results. Increasing the slot context to 32K
and removing the hidden restriction changed the harness, not product code or
the frozen tasks.

Final complex-case outcomes and evidence are recorded in
[`complex-results-20261024.json`](../benchmarks/repo-quality/complex-results-20261024.json).

| Complex case | Model rounds / tool attempts | Final acceptance |
|---|---:|---|
| HTTPX multi-constraint async client | 13 / 12 | Fail: constructing `Timeout` raises `ValueError`; also invalid limits, unregistered hook and missing `trust_env=False`. |
| Starlette lifecycle service | 9 / 8 | Fail: generated test raises `TypeError: 'list' object is not callable`; missing `make_app`, wrong exception behavior and pool capacity. |
| MkDocs inheritance and deployment | 3 / 9 | Fail: wrong Project Pages branch (`master`), missing `use_directory_urls: false`, validation settings substituted for the requested configuration. |

**0/3 passed complete task acceptance.** Both Python outputs compile but fail
execution without editing them. MkDocs YAML parses, but parsing does not
validate its meaning. These results apply to this model/harness and small case
set. There is no matched complex-agent baseline, so they do not establish
whether Cairn helps or harms complex-agent success. They do rule out claiming
that this repair alone made the tested agent dependable for these tasks.

## Interpretation and remaining work

Cairn now preserves previously lost documentation and offers a materially
smaller cited retrieval interface. That is a useful, testable role for the
tool. The experiment does **not** establish reliable autonomous implementation
of complex requirements, superiority over strong lexical retrieval, broad
cross-language support, or production readiness.

The complex Starlette agent read a parent section but skipped the child holding
the 40-token limit; it also read single-task documentation without retrieving
the multiple-task section. A full section contains that node's own body,
excluding descendant bodies. Agents must inspect the outline/children or search
again. HTTPX retrieved the exact timeout documentation but generated an invalid
constructor anyway. Retrieval coverage, navigation completeness and executable
correctness need independent acceptance checks.

Next evidence needed: more independent repositories and larger corpora,
repeated runs, other agent models, a full-session BM25 agent comparator, and
executable acceptance tests in the agent loop. None of those are claimed here.

## Verification and artifacts

The repaired implementation passes 517 tests, Ruff and strict mypy (114 source
files); five test warnings come from the PDF dependency. Wheel and source
distribution are built locally. No release or remote publication is performed.

[Machine-readable retrieval results](../benchmarks/repo-quality/results-20261024.json)
include baseline and comparison metrics. Full prompts, replies, citations,
source hashes, model-server logs, invalid diagnostic traces and generated-code
execution results are retained locally under
`/Users/example/project`.
The original pre-repair evaluation remains in the sibling `20261024/` directory.
These absolute paths identify this run's local artifacts; they are not public
download links. The benchmark protocol and frozen cases are tracked in this
repository so subsequent runs can report their own artifacts and results.
