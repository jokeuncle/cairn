# Strong inexpensive control and new-project executable tasks

Date: 2026-10-25. Continues the [budget/parity study](2026-10-25-budget-parity.md).

## Result and scope

Ten additional real Codex CLI sessions completed: four on two known synthetic
aliases, then six on two newly authored multi-constraint coding tasks in
Pydantic and Typer. Every final deliverable passes independent execution and
manual requirement/source review. On the two new project tasks, Cairn, the
inexpensive helper and actual raw-source search each pass **2/2**.

There is still **no price-independent token-cost parity** on the new tasks.
Cairn has lower cumulative input but higher uncached input than both controls.
The earlier synthetic CLI advantage must not be generalized into a commercial
or algorithmic-superiority claim. The stronger control also exposes process
skill-reading differences unrelated to document retrieval.

A concrete input repair was delivered separately: an explicit, non-executing
[local snippet preparation command](../snippet-preparation.md). The retrieval
prototype remains external; no default retrieval behavior was changed.

## Frozen protocol and sources

All attempts use Codex CLI 0.164.0, `gpt-6.1-sol`, high reasoning, ephemeral
sessions, existing authentication, 24 tool invocations and a 900-second limit.
Final output is requested within 1,800 tokens, not decoder-capped. Permissions
match across arms: read-only filesystem plus a command network proxy allowing
only `127.0.0.1` for the approved embedding backend. Web, delegation, source
edits, installs and credential access are prohibited. Prior external/write
negative controls and a fresh exact backend sandbox query qualify the setup.

The Cairn source is the unchanged 71-file external link prototype. Its CLI
gateway strips diagnostic trace metadata but preserves full source JSON,
citations and omission/recovery signals. The independent helper has no Cairn
imports, embedding calls, LLM calls or offline persistent index. It parses the
selected original Markdown and computes BM25/structural links in memory on
each invocation, under source/section budgets. This query-time work is real;
it is not a zero-compute baseline. It can bundle explicit same-document and
selected cross-document links. Both CLI arms have identical prompt contracts
except adapter paths of equal length; agents are not told the backend identity.
The raw arm uses actual shell/rg over copied selected documentation.

Code, task texts, oracle controls and corpus hashes were frozen before model
answers. No retrieval tuning followed those answers. All ten valid attempts
are retained; no extra trial was selected to replace an unfavorable one.

| New project | Pinned source revision | Documentation surface | Runtime |
| --- | --- | --- | --- |
| [Pydantic](https://github.com/pydantic/pydantic/tree/cf67d4b3193c3fe43ede18612ed62785eee11382/docs/concepts) | `cf67d4b3193c3fe43ede18612ed62785eee11382` | Seven Markdown files, 192,386 bytes, 115 sections | 2.13.4 |
| [Typer](https://github.com/fastapi/typer/tree/4e10334990db4e7e1e9a71aff363bcae7f7fc76d/docs/tutorial) | `4e10334990db4e7e1e9a71aff363bcae7f7fc76d` | Nine Markdown files after official snippet expansion, 42,916 bytes, 45 sections | 0.26.7 |

These task texts/projects were not used for preceding retrieval tuning, but
they are public APIs a model may already know. The documentation surfaces are
selected topic files, not full repositories. They are neither real customer
incidents nor a statistically independent large held-out benchmark.

Cairn uses actual local nomic 768-dimensional embeddings, explicit document/
query prefixes and 1,500-byte windows. Summaries are controlled extractive
source words rather than the default LLM provider, as in the preceding study.
Fresh-index construction took 4.13 seconds for Pydantic and 1.35 seconds for Typer,
with the embedding server already running; model startup is excluded. Index
size was respectively 7.09 and 11.95 times these small selected source surfaces.
Those measurements are before amortization, not asymptotic storage bounds.

## Executable acceptance

The Pydantic task combines alias/path precedence with unknown-field rejection,
strict bounds/types, nested cross-field constraints, string normalization,
ordered deduplication, independent defaults, frozen assignment, serialization,
mode-dependent tokens and caller-input preservation. Its independent verifier
runs 28 checks on each complete generated module.

The Typer task combines required root profile/context, eager version handling
despite an earlier invalid option, case-insensitive enum modes, repeated tags,
callback validation/resilient parsing, confirmation/abort and repeated-invocation
isolation. Its verifier runs 11 checks; complete-module/source review also
checks callback guards and citations. Shell completion and real-terminal
integration are not qualified by CliRunner.

Both reference modules pass before any model answer. Four mutations must fail:
unfrozen Pydantic assignment, accepted blank tags, non-eager version handling,
and missing CLI tag validation. The first oracle qualification exposed that a
simple `--version` test did not reject a non-eager mutation. An earlier invalid
profile was added to the task/test before model execution. The failed initial
qualification remains recorded; it was not counted as a model failure.

Every generated module was manually audited before execution. The verifier is
not a hostile-code sandbox. Generated self-test counts are not substituted for
independent checks. Citation targets are resolved against frozen sources and
manually checked for the API explanations.

One source-audit bug was corrected: raw `alias.md#validation` is valid even
though two logical AST paths end in `validation`; the first rendered heading
owns the unsuffixed anchor. Requiring a unique AST leaf falsely rejected the
raw answer. Positive/negative controls qualify the correction, all arms were
rechecked, and the original audit remains available. The live versioned public
URL redirects to the latest site, so it confirms anchor existence only; task
content/runtime remain pinned locally. No code/task acceptance was weakened.

## Known synthetic tasks: cheap control gets the same evidence

| Two known aliases | Cairn CLI | Inexpensive helper CLI |
| --- | ---: | ---: |
| Accepted | 2/2 | 2/2 |
| Cumulative input I | 158,670 | 216,184 |
| Cached input K | 129,152 | 162,304 |
| Uncached input U | 29,518 | 53,880 |
| Output O | 2,446 | 3,110 |
| Documentation calls | 2 | 2 |
| Process-skill calls | 0 | 5 |

Both backends obtain all required documentation in **one call per task**.
The helper agents choose extra skill reads before seeing document results.
Thus lower whole-session usage is observed, but cannot be attributed to a
better retrieval algorithm. Identical task/interface documentation does not
force identical process behavior. No subtraction of skill tokens is presented
as a causal estimate because those reads can change later behavior.

## New-project results

I/K/U/O are full CLI turn usage, including reasoning, generated test code,
failed self-checks and all source/skill interactions. U = I − K. Invocation
counts are not model-turn counts: calls can run together.

| Two new tasks | Cairn CLI | Inexpensive helper | Actual shell/rg |
| --- | ---: | ---: | ---: |
| Accepted | 2/2 | 2/2 | 2/2 |
| I | 468,189 | 589,068 | 529,328 |
| K | 388,352 | 521,728 | 465,920 |
| U | 79,837 | 67,340 | 63,408 |
| O | 9,602 | 9,696 | 12,669 |
| All tool invocations | 22 | 21 | 15 |
| Documentation CLI calls | 15 | 15 | n/a |
| Process-skill calls | 2 | 2 | 5 |

Cairn's I is 20.52% lower than the helper and 11.55% lower than raw. Its U is
18.56% higher than the helper and 25.91% higher than raw. Its O is 0.97% lower
than the helper and 24.21% lower than raw. No componentwise I/U/O advantage
holds. Each case/arm has one attempt, and task integration/self-testing differs;
there is no identified one-component algorithm effect or latency guarantee.

For deployment sensitivity let r = cached/uncached input price and
q = output/uncached input price. Excluding indexing, query compute, storage
and latency, the measured token-cost differences are:

    Cairn − helper: ΔC / p_u = 12,497 − 133,376 r − 94 q
    Cairn − raw:    ΔC / p_u = 16,429 − 77,568 r − 3,067 q

These are accounting identities, not actual prices or invoices. Particular
price ratios may favor Cairn, while other ratios do not. Lower total input
alone is not evidence of lower uncached cost. The benchmark does not establish
commercial superiority, customer willingness to pay or broad generalization.

## Input repair delivered alongside the experiment

The new `scripts/materialize_doc_snippets.py` explicitly prepares local
`docs_src/*.py` includes into separate Markdown, preserving the original code
and source/output hashes with exact Unicode spans. It does not execute code,
fetch remote content, overwrite inputs or change the default parser. Path and
symlink escapes, missing/unknown includes and excessive expansion are rejected.
Changed upstream files require a fresh explicit preparation; dependency changes
are not automatically watched by an index of the old prepared snapshot.

Ten meaningful boundary/provenance checks pass. The actual command was also
run on the nine pinned Typer documents: all 37 original snippets match their
source hashes and output spans, and the source checkout remains unchanged.
This verifies input preparation, not an Agent-cost gain from the new command.
The frozen Agent corpus used the earlier preparation fixture; code content
hashes agree, but the new command was not swapped into completed attempts.

The full product suite passes **565 tests**, Ruff and strict mypy (123 source
files including the new script/test). The 70-file product retrieval source
still matches its preceding snapshot; the external 71-file retrieval candidate
is not merged into defaults.

## Supported next direction

Connected original evidence and a lightweight interface remain useful, but a
cheap structural helper can supply the same synthetic evidence. Semantic
indexing must earn its setup/storage and interaction costs on unfamiliar
semantic needs, not only exact identifiers and explicit links. Compare a cheap
structural path and an explicit semantic fallback under consistent process
instructions; do not silently treat sparse-score thresholds as calibrated
task-success probabilities. Scope-sensitive execution and provenance checks
remain necessary whichever retrieval path is used.

[Machine-readable results](../../benchmarks/repo-quality/strong-control-results-20261025.json)
retain all ten attempts, protocols, source hashes, oracle controls, source-audit
correction and counters. Full local artifacts are under
`/Users/example/project`.
This fixed screen ends without trial replacement, default retrieval changes,
remote publication or a commercial-success claim.
