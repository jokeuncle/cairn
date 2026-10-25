# Cross-project confirmation: HTTPX and Starlette

Date: 2026-10-25. The actual installed product CLI passes both new complex tasks, and fresh raw-document Agents also pass both. Hybrid/text reduces uncached input and output but increases cumulative input; **the predeclared componentwise I/U/O gate fails**. This is a conditional cost result, not commercial certification.

## Protocol and independent acceptance

This prospectively tests the secondary hybrid/text observation in the [earlier ten-session screen](2026-10-25-lean-cli.md). It does not replace that failed primary result. Four new serial gpt-6.1-sol/high CodexCLI0.164.0 sessions use the same 72-file product wheel. No implementation changed between these phases. Tasktexts, corpus bytes/revisions, runner, oracle and product source were frozen before these answers; 96 hashes matched on completion. Orders: HTTPX Cairn→raw; Starlette raw→Cairn. Same24-observed-command/900s budgets, read-only permission profile and fixed local embedding endpoint only. All valid failures retained.

HTTPX0.28.1: multi-request token refresh, exactly one retry, status/token-validation failure preserving old state, streamed request/response body loading, sync/async authentication, client settings, repeated query tags, input purity and transport cleanup. Starlette1.3.1: pure ASGI, ASCII/duplicate-header validation, request-local ContextVar and finally cleanup, overlapping requests, non-HTTP passthrough, duplicate-cookie preservation and CORS on errors/preflights.

Each module passes20 independently authored runtime groups, plus a complete source/safety/requirements/citation audit. Four seeded reference regressions are rejected: omitted response loading/status check, context leak, and duplicate-header collapse. Starlette emits a qualified deprecation warning for its still-working HTTPX TestClient backend; no installation occurred.

## Observed full-session usage

I=cumulative input, K=cached input, U=I−K; O includes reasoning and all other output. Invocations are observed command events, not model turns.

| Project | Arm | Accepted | I | K | U | O |
|---|---|---:|---:|---:|---:|---:|
| httpx-refresh | hybrid-text | yes | 185,487 | 171,136 | 14,351 | 6,163 |
| httpx-refresh | raw | yes | 229,050 | 189,056 | 39,994 | 5,763 |
| starlette-request-id | raw | yes | 143,817 | 127,232 | 16,585 | 7,904 |
| starlette-request-id | hybrid-text | yes | 217,943 | 198,144 | 19,799 | 5,344 |
| Total | hybrid-text | 2/2 | 403,430 | 369,280 | 34,150 | 11,507 |
| Total | raw | 2/2 | 372,867 | 316,288 | 56,579 | 13,667 |

Hybrid/text vs raw: input_tokens +8.20%, uncached_input_tokens -39.64%, output_tokens -15.80%. The increase in I fails the declared gate, even though U and O fall. HTTPX improves both input measures but adds400 output tokens; Starlette increases both input measures while reducing output. There is no per-project dominance.

Normalize uncached-input token price to1, let r be cached-input price ratio and q output price ratio. Agent-token cost difference Cairn−raw is `−22429 + 52992r − 2160q`. This aggregate is lower for r≤0.4 and any q≥0, but caching/output rates are not assumed and indexing cost is excluded. The sufficient price condition is a calculation, not a provider-price or net-TCO claim.

## Interpretation and limits

- Both new tasks are executable cross-project evidence. They are author-curated, one observation per arm, not a blinded customer workload or an estimate of broad success rate.
- Both Cairn sessions read process skills (19,770 returned characters each); neither raw session does. Raw HTTPX additionally reads four runtime method implementations via allowed `inspect.getsource`. All these choices remain in I/K/U/O. They limit causal attribution to the retrieval algorithm or renderer.
- One Cairn Starlette request supplies an evidence-only budget with another view, fails cleanly, then recovers. It is retained with its cost. Two source-exposing CLI commands are the next bounded interface experiment; no improvement from them is claimed by this report.
- Source selection is seven documents per project,59,954 bytes HTTPX and74,164 bytes Starlette. Controlled extractive summaries and a warm Nomic768/1500bytewindow endpoint are used; no custom query/document prefixes. No default LLM-summary initialization cost, cold model startup or large/multilingual corpus claim.

## Frozen sources and records

[HTTPX0.28.1 documentation](https://github.com/encode/httpx/tree/0.28.1/docs), revision `26d48e0634e6ee9cdc0533996db289ce4b430177`; [Starlette1.3.1 documentation](https://github.com/Kludex/starlette/tree/1.3.1/docs), revision `8ebffd0678570ddd5d5bb11c6f3c3c7fd4682ab9`. Local runtime versions match those task versions.

External root: `/Users/ksher/self-projects/cairn-evaluations/rescue-20261024/cross-project-confirmation-20261025`. `protocol-frozen.json`, `runs/r00..r03`, `oracle-qualification.json`, `trace-diagnostics.json` preserve sources/answers/errors/usage and independent review. No product source mutation, global config/auth changes, publication or deployment during this phase.

[Machine-readable results](../../benchmarks/repo-quality/cross-project-confirmation-results-20261025.json) · [CLI usage](../cli-retrieval.md)
