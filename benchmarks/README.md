# cairn-bench

A starter benchmark suite. **The framework is the contribution; the
included dataset is a template.** Real evaluation needs more curated
documents and many more questions; we ship 10 hand-written questions over
Cairn's own `ARCHITECTURE.md` to make the wiring reproducible.

## Running

```bash
# Zero-setup, deterministic (uses FakeEmbedder + FakeSummarizer)
cairn bench benchmarks/architecture.toml --fake

# With Ollama (real semantic search)
ollama serve
ollama pull nomic-embed-text
ollama pull llama3.2:3b
cairn bench benchmarks/architecture.toml
```

By default the bench runs at `k=8`. Override with `--k 5` (for example) to
make recall harder.

The bench writes both a Markdown summary to stdout and a JSON report to
`/tmp/cairn-bench/<suite>.json` (overridable via `--out`).

## What it measures

- **Recall@k** of `expected_anchors` against the top-k retrieved
  section ids.
- **Tokens returned** by retrieval (the cost the agent would pay to put
  the result in its context window).

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

- **No QA accuracy.** An LLM-judged QA metric is a v0.3 follow-up. The
  current numbers measure how well retrieval surfaces the right
  *sections*; whether a language model gets the answer right from those
  sections is a separate question.
- **No statistical claims.** Ten questions on one document is a
  demonstration, not a benchmark. The headline numbers in the README
  come from this dataset and are reproducible, not generalisable.
