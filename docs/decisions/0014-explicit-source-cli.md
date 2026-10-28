# ADR-0014: Explicit original-source CLI commands

- **Status:** Rejected; implementation withdrawn after the real-Agent screen
- **Date:** 2026-10-25
- **Related:** ADR-0013 and its cross-project confirmation

The shared JSON-argument CLI works, but real Agents repeatedly combine source
budgets with another context view: seven errors in the first ten-session screen
and one in the subsequent four-session confirmation. The second study improves
uncached input and output but still increases cumulative input. A smaller
representation alone has not passed the predeclared whole-task cost gate.

Add `docsgraph source search QUESTION` and `docsgraph source read CITATION`.
Choosing the `source` namespace explicitly requests original evidence or a full
section body. Ordinary CLI/MCP tools retain progressive-disclosure defaults.
Search uses the existing evidence handler and unchanged default budgets/ranking;
read uses the existing full-body handler. Section bodies exclude descendants.
Native CLI options validate budgets and allow repeated focused questions. Both
commands delegate to the same shared CLI dispatcher and preserve complete
payloads, citations, scope, omissions, warnings, provider checks and failures.
Text is the default within this explicit source view; JSON remains selectable.
No new retrieval algorithm, model, dependency, storage format or MCP tool.

Verify actual cached reads and provider-free lexical source queries, source
boundaries/budgets, and native invalid-option rejection. Run the complete suite
and build/install a fresh wheel. Freeze a four-session comparison on the two
now-known HTTPX/Starlette tasks, with fresh raw controls and reversed order from
the preceding study. This is an interface development screen, not heldout
generalization. Predeclare source CLI as primary; require both correct with
valid sources and aggregate I/U/O each no greater than fresh raw. Preserve all
valid failures and do not switch candidates after results. If the gate fails,
do not promote the interface as commercially cheaper. No publication or global
configuration change is part of this experiment.

## Outcome

The [four-session development screen](../research/2026-10-25-source-cli.md)
accepts both tasks in both arms. Native arguments remove view/budget errors,
but cumulative input rises12.62%, uncached input23.31%, and output14.98%.
The Agent-token cost difference is positive for every nonnegative cached-input
and output price ratio. Reject the candidate and withdraw the two shortcuts
and their three tests from the retained product. The measured prototype remains
in the frozen external wheel; generic `query tool`, lexical mode, the renderer
and all preceding repairs remain. This is not a claim that native CLI arguments
always increase cost.
