# Explicit source-command interface: rejected development candidate

Date:2026-10-25. Two native `source search/read` shortcuts were implemented, unit-qualified and exercised by real Agents against fresh raw controls. Both arms pass both tasks. The shortcuts increase every measured input/output cost component and are **withdrawn from the product**. The generic `query tool` CLI and explicit lexical retrieval remain.

## Frozen screen and independent verification

Four serial CodexCLI0.164.0 gpt-6.1-sol/high sessions on the now-known HTTPX/Starlette tasks; source CLI is primary, fixed before answers. Order reverses the preceding phase: HTTPX raw→source CLI; Starlette source CLI→raw. Existing ranking/evidence/default budgets, model, corpus bytes and text renderer are unchanged. A shorter native-argument source-interface description replaces the six-tool JSON-argument description. Same900s/24-observed-command budgets; all valid failures retained.

Both complete modules pass20 independent runtime groups each and source/citation/manual safety review. The reference oracle rejects four seeded regressions. The prototype passed587 tests, Ruff and mypy73 sources; all72 installed Python source files matched the measured implementation. Three of those tests cover the withdrawn interface; the retained suite returns to584 on rollback.

| Arm | Accepted | I | K | U=I−K | O | Observed calls | Doc command events/errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| source-cli | 2/2 | 505,941 | 455,296 | 50,645 | 13,928 | 18 | 11/0 |
| raw | 2/2 | 449,262 | 408,192 | 41,070 | 12,113 | 12 | 0/0 |

Source CLI vs raw: input_tokens +12.62%, uncached_input_tokens +23.31%, output_tokens +14.98%. With uncached-input price1, cache ratio r and output ratio q, its Agent-token difference is `9575 + 47104r + 1815q`, strictly positive for nonnegative r/q. This particular observation is worse for every nonnegative token-price combination.

Native arguments remove view/budget errors in these sessions (zero), but the source Agents issue11 documentation command events instead of six in the earlier generic-CLI phase, and perform different local tests. Both source Agents read35,132 skill characters; raw reads35,132 and10,962. This is evidence against promoting the candidate, not proof that native interfaces always cause higher cost. Control variability and one session per arm prevent causal/generalized conclusions.

## Records and decision

No failed answer or costly attempt was discarded. The prototype remains reproducible in its frozen external wheel; it is not added to the retained public interface. See [ADR-0014](../decisions/0014-explicit-source-cli.md).

External root: `/Users/example/project`; `protocol-frozen.json` verifies98 artifacts; `runs/r00..r03` preserves prompts, commands, JSONL, answers, usage and independent reviews. The source snapshot is the pre-withdrawal implementation, not a claim about final product commands.

[Machine-readable results](../../benchmarks/repo-quality/source-cli-results-20261025.json) · [Previous cross-project confirmation](2026-10-25-cross-project-confirmation.md)
