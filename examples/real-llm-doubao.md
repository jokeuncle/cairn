# Real-LLM smoke test — Doubao (Volcengine ARK)

End-to-end validation that the OpenAI-compatible summarizer works with a
production-quality model. Run on a 4-section toy markdown document:

```
CAIRN_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 \
CAIRN_LLM_MODEL=doubao-seed-2-0-code-preview-260215 \
CAIRN_LLM_API_KEY=<your-ark-key> \
CAIRN_EMBED_PROVIDER=doubao-vision \
CAIRN_EMBED_API_KEY=<your-ark-key> \
cairn index ./doc.md --out /tmp/doc-real
```

## Captured output

Section: **What is Cairn**

- `gist`: *Cairn is a structure-aware retrieval system mapping large
  documents for AI agents.*
- `synopsis`: *Cairn is a structure-aware retrieval system. It converts
  large documents into navigable maps designed for AI agents. This core
  explanation teaches readers the system's primary identity and key
  purpose.*

Section: **Why it matters**

- `gist`: *Unlike naive RAG, Cairn preserves author structure for
  human-like agent reasoning.*
- `synopsis`: *Naive RAG fragments documents into context-free chunks,
  while Cairn preserves the author's original structural arrangement of
  text. Readers will learn how this fundamental distinction matters:
  Cairn's retention enables AI agents to engage with documents and
  reason about their content the way human readers would, avoiding the
  logical gaps from naive, unstructured chunking.*

Section: **Three sub-indexes**

- `gist`: *v0.1 includes Tree, Summaries, Vectors indexes; v0.2 adds
  Entities, Cross-references.*
- `synopsis`: *Lists index sub-components and their corresponding
  release versions. v0.1 ships with three sub-indexes: Tree, Summaries,
  and Vectors. v0.2 introduces two additional sub-indexes: Entities and
  Cross-references.*

Compare against the same sections with `FakeSummarizer` (BoW
truncation), which returns the first 15/60 words verbatim. The real
model produces actual abstractions; the fake is a structural
placeholder. **The product is the same in both cases** — index, tools,
MCP server, CLI — only the plug-in changes.

## Configuration recap

Volcengine ARK exposes Doubao via an OpenAI-compatible
`/chat/completions` endpoint under `https://ark.cn-beijing.volces.com/api/v3`.
Cairn's `OpenAICompatibleSummarizer`
talks to it with zero code changes; just point the standard env vars at
ARK:

| variable | value |
|---|---|
| `CAIRN_LLM_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` |
| `CAIRN_LLM_MODEL` | `doubao-seed-2-0-code-preview-260215` (or any Doubao chat model) |
| `CAIRN_LLM_API_KEY` | your ARK API key |

For `doubao-embedding-vision-251215`, set
`CAIRN_EMBED_PROVIDER=doubao-vision`. That model is served through
`/embeddings/multimodal` and returns a 2048-dimensional dense vector, so it
does not fit the standard OpenAI `/embeddings` response shape.

For larger documents or benchmark runs, lower `CAIRN_SUMMARY_CONCURRENCY` and
raise `CAIRN_LLM_TIMEOUT` / `CAIRN_EMBED_TIMEOUT` if ARK is rate-limiting or
responding slowly. Both LLM and embedding clients retry 429/5xx and transport
errors by default.

The same pattern works for OpenAI, Together, Anyscale, vLLM, Ollama —
anything speaking the OpenAI wire format.

## Why this matters

This run is what makes Cairn's pitch concrete. The README's headline
numbers (25.2% of naive's tokens at equal recall) come from a
deterministic `FakeEmbedder` to keep the bench reproducible offline.
Pointed at a real model, semantic search starts contributing real wins,
the gist tier produces meaningful one-liners, and the progressive
disclosure default actually saves you real money.
