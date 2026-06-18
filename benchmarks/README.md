# cairn-bench

A starter benchmark suite. **The framework is the contribution; the
included dataset is a template.** Real evaluation needs more curated
documents and many more questions; we ship 10 hand-written questions over
Cairn's own `ARCHITECTURE.md` to make the wiring reproducible.

Latest deterministic run (`cairn bench benchmarks/architecture.toml --fake`,
k=8):

| metric | naive vector RAG | Cairn |
|---|---:|---:|
| mean recall@8 | 25.00% | 25.00% |
| mean tokens returned | 3,670 | 1,388 (37.8% of naive) |

## Running

```bash
# Zero-setup, deterministic (uses FakeEmbedder + FakeSummarizer)
cairn bench benchmarks/architecture.toml --fake

# With Ollama (real semantic search)
ollama serve
ollama pull nomic-embed-text
ollama pull llama3.2:3b
cairn bench benchmarks/architecture.toml

# With Volcengine Doubao
CAIRN_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 \
CAIRN_LLM_MODEL=doubao-seed-2-0-code-preview-260215 \
CAIRN_LLM_API_KEY=<your-ark-key> \
CAIRN_EMBED_PROVIDER=doubao-vision \
CAIRN_EMBED_API_KEY=<your-ark-key> \
cairn bench benchmarks/architecture.toml
```

By default the bench runs at `k=8`. Override with `--k 5` (for example) to
make recall harder.

For hosted APIs, tune `CAIRN_SUMMARY_CONCURRENCY`, `CAIRN_EMBED_BATCH_SIZE`,
`CAIRN_LLM_TIMEOUT`, `CAIRN_LLM_MAX_RETRIES`, `CAIRN_EMBED_TIMEOUT`, and
`CAIRN_EMBED_MAX_RETRIES` to match provider limits.

The bench writes both a Markdown summary to stdout and a JSON report to
`/tmp/cairn-bench/<suite>.json` (overridable via `--out`).

## What it measures

- **Recall@k** of `expected_anchors` against the top-k retrieved
  section ids.
- **Tokens returned** by retrieval (the cost the agent would pay to put
  the result in its context window).
- **Optional QA correctness** when `--judge` is enabled and questions include
  `reference` answers.

Both are tracked for Cairn (`search_semantic` over the structure-aware
index) and for a naive vector-RAG baseline (512-word chunks → LanceDB
cosine search; structure-blind). The naive baseline assigns each chunk to
its containing section by midpoint byte, so recall is computed against
the same coordinate system Cairn returns.

## Authoring your own suite

```toml
name = "My document set"

[[documents]]
id = "handbook"
source = "../docs/handbook.md"

[[documents.questions]]
id = "q-001"
question = "What is the team's release cadence?"
expected_anchors = ["release-cadence"]  # substring of the target section id
tags = ["policy"]
```

Tips:

- `expected_anchors` use **substring matching**, so short suffixes are
  enough. Find candidates with `cairn outline <doc-dir>` after indexing.
- Multiple anchors mean "the answer is spread across these sections"; a
  question gets full recall only when *every* listed anchor appears in
  the top-k.
- Use `tags` to slice results in your own analysis.

## What this benchmark does **not** do

- **No statistical claims.** Ten questions on one document is a
  demonstration, not a benchmark. The headline numbers in the README
  come from this dataset and are reproducible, not generalisable.
- **No external-standard adapter yet.** Cairn's core target is navigating one
  large structured document via stable anchors, while most public retrieval
  benchmarks model query-to-document retrieval over a corpus. Adapter work is
  required before those numbers are comparable.

## Standard benchmark path

There is no single public benchmark that exactly matches Cairn's
structure-aware, single-document navigation contract. The closest useful
standards are:

- [BEIR](https://github.com/beir-cellar/beir): broad zero-shot information
  retrieval across heterogeneous corpora. Good for testing query-to-document
  retrieval, but needs a Cairn adapter that maps corpus documents or passages
  to stable section anchors.
- [MTEB](https://github.com/embeddings-benchmark/mteb): embedding benchmark
  suite. Useful for validating the chosen embedder, not Cairn's graph/index
  layer by itself.
- [LongBench](https://github.com/THUDM/LongBench) and
  [LongBench v2](https://longbench2.github.io/): long-context understanding
  tasks. Relevant to Cairn's "large document" thesis, but requires an
  answer-generation harness rather than recall-only retrieval.
- [RAGBench](https://arxiv.org/abs/2407.11005): closer to end-to-end RAG
  quality because it evaluates retrieved evidence and generated answers.

Recommended OSS sequence:

1. Keep `cairn-bench` as the product-specific anchor-recall benchmark.
2. Add a BEIR adapter for retrieval sanity (`nDCG@10`, `Recall@100`) using the
   same embedder across Cairn and baselines.
3. Add a LongBench/RAGBench adapter for answer quality with `--judge` and
   source-grounded evidence checks.
