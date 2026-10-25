# Alpha0.1.0a13 release validation

This release adds experimental cached document links, bounded reference analysis,
provider-free lexical CLI queries, evidence/ingest repairs and explicit embedding
roles. It does not establish a commercial success-rate or cost advantage.

## Regression checks

- Python3.11/3.12/3.13: each620 tests pass; five existing PyMuPDF/SWIG deprecation
  warnings per run. Ruff and strict mypy pass on all three Python targets.
-37 pinned public checkouts:3,754 documents indexed, no sync failures;
 185/185 queries return hits and185/185 permit source drilldown.
-32 development queries over UV, MCP Python SDK, Pydantic AI and FastAPI template:
  top1 29/32; top3/top5/drilldown32/32. Unchanged strict aggregate thresholds
  are0.90/1.0/1.0/1.0. Fake summaries/embeddings test lexical and wiring behavior,
  not semantic retrieval or Agent task economics.

[Machine-readable results](../../benchmarks/repo-quality/release-validation-20261025.json)
pin source revisions, per-repository outcomes and code differences from earlier
Agent builds. These are development gates; source files and outcomes were
inspected during repair. They are not a blind generalization estimate.

The installed release wheel also syncs51/51 Cairn documents with no errors;
`doctor --fake`, MCP config, cached graph and impact CLI checks pass. The legacy
10-question architecture starter returns lower recall for Cairn (25% versus45%)
with1,362 versus4,374 returned tokens. Its questions/anchors were not changed
after the architecture document evolved. This unfavorable fake-provider result
is retained, not advertised as quality parity or Agent savings.
[Raw starter result](../../benchmarks/repo-quality/release-starter-results-20261025.json).

## Retained failure and targeted adjudication

| Code and labels | Top1 | Top3 | Top5 / drilldown |
|---|---:|---:|---:|
| Original0.1.0a12, original labels |29/32|32/32|32/32|
| Candidate before namespace guard, original labels |27/32|31/32|32/32|
| Same candidate, corrected labels only |29/32|31/32|32/32|
| Final candidate, original labels |29/32|32/32|32/32|
| Final candidate, corrected labels |29/32|32/32|32/32|
| Original0.1.0a12, corrected labels |30/32|32/32|32/32|

The original failed gate and finite rejected ablations are retained in the local
release evidence directory. Full cached-body recall and query-wide BM25 remain.
[ADR-0018](../decisions/0018-bounded-source-namespace-confidence.md) adds bounded
confidence for explicit whole-token source namespaces, with three metamorphic
regressions for verb prefixes, path normalization and false matches. Product
code contains no repository-specific names, questions or expected answers.

A separate real Agent, blind to ranks/scores/old labels, reviewed four targeted
source questions selected after the failures. It accepted three omitted UV
source aliases and rejected TLS/login and MCP client/server confusions. Its
source-only command transcript was manually audited; one missing-python command
and subsequent python3 recovery are retained. This adjudication is not a new
comparative performance run. The aliases and evidence were frozen before the
final gate. Label corrections are reported separately from product changes.
[Correction record](../../benchmarks/repo-quality/source-label-correction-20261025.json).

The original-release control read the same public Markdown; an unrelated
.claude skill dangling symlink caused a copy warning, retained in its log. The
comparison is a development diagnostic, not an isolated causal experiment.

## Real Agent evidence and release boundary

The frozen [document-link](2026-10-25-document-links.md) and
[reference-analysis](2026-10-25-reference-impact.md) studies contain14 completed
comparative real Agent sessions, four target instances of one task family, two
pinned public repositories. All accepted answers and source witnesses passed;
both predeclared cost gates failed. A separate infrastructure abort is retained.
These observations do not demonstrate a blind workload or commercial advantage.

The reference-analysis wheel and release contain the same75 product modules.
Graph/impact implementations are byte-identical. Package metadata and the late
source-namespace guard differ. Earlier Agent token results apply to their frozen
wheels; the late guard has regression/public-gate coverage rather than a new
comparative Agent cost study. No earlier result has been relabeled as a final
release measurement. See the [experiment ledger](README.md) for prior studies.

Initial indexing still costs model calls and storage; cached reference/lexical
queries need no provider. Unavailable/stale sources, caps and partial evidence
remain explicit. Markdown reference reachability is not code dependency impact.

## Fresh dependency resolution

The first main-branch CI run failed before pytest: a fresh pip install selected
MCP2.3 and LanceDB0.40, whose APIs differ from the locally locked MCP1.28 and
LanceDB0.33. The release now declares MCP>=1.28,<2 and LanceDB>=0.33,<0.34.
PyArrow lacks uniform distributed typing metadata, so only its third-party
import is marked untyped; Cairn strict checks remain enabled. The failed CI
run is retained publicly; tagging waits for clean re-resolution and green CI.
[Initial CI failure](https://github.com/jokeuncle/cairn/actions/runs/40180107704).
The [MCP migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
recommends retaining the <2 bound until migrating. No product-module source
changed for this compatibility fix. A clean unlocked Python3.13 install resolves
MCP1.30, LanceDB0.33 and PyArrow26; all620 tests and133-file strict mypy pass.
Eight deprecation warnings are retained in that fresh run. An actual MCP SDK
stdio handshake, tool-schema listing, cached graph and impact calls also pass
with these freshly resolved dependencies.

## Release and rollback

The authorized release is the experimental prerelease0.1.0a13 through the
existing GitHub tag/OIDC pipeline. Publication must pass CI, distribution checks,
PyPI installation verification and Pages deployment. Halt tagging on any failed
local or CI gate; do not weaken thresholds. Inspect public package metadata and
site content after publication. Reverting Pages requires a normal revert commit;
package rollback means pinning the already-published0.1.0a12, never overwriting an
immutable PyPI version. No automatic model/provider migration or new index format
is introduced beyond the documented tree producer rebuild.
