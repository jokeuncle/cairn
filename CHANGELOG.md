# Changelog

All notable changes to Cairn. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [0.1.0a2] — 2026-06-11

Second alpha. Adds document-level incremental rebuild, validates the
full stack end-to-end against a real LLM (Volcengine Doubao Seed 2.0),
and lands the OSS housekeeping needed for a public repo.

### Added

- **v0.2.5 — Incremental rebuild.** `cairn index <source>` now skips
  the rebuild when the existing manifest's `source_hash` matches the
  incoming source. `--force` overrides. `Indexer.index_path` returns an
  `IndexResult(manifest_path, rebuilt)` so callers can distinguish a
  no-op from a real build.
- **Real-LLM validation.** `examples/real-llm-doubao.md` captures the
  exact summaries Cairn produced against Doubao via the
  OpenAI-compatible endpoint at `https://ark.cn-beijing.volces.com/api/v3`
  — the local-first promise extends to any OpenAI-compatible cloud
  endpoint with zero code changes.
- **OSS housekeeping.** `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1),
  GitHub Actions CI (ruff + mypy --strict + pytest on Python 3.11/3.12/
  3.13), release workflow that builds wheel + sdist on tag, issue and
  PR templates.

### Changed

- All repository URLs point at `github.com/jokeuncle/cairn`.
- README gains the CI status badge.

## [0.1.0a1] — 2026-06-11

First public alpha. The full structure-aware retrieval pyramid is
assembled end-to-end. All eight MCP tools spec'd in
`docs/specs/mcp-tools.md` are shipped. Markdown and PDF ingestion both
work. A `cairn-bench` harness produces reproducible numbers against a
naive vector-RAG baseline.

### Phase 1 — Walking skeleton (v0.1)

#### Added
- `cairn.core.types`: Pydantic v2 frozen models for `Span`, `SectionNode`,
  `SummarySet`, `Mention`, `Entity`, `XRef`, `Document`. Mypy strict.
- `cairn.core.errors`: `CairnError` hierarchy with structured-envelope
  conversion for the MCP wire layer.
- `cairn.ingest.markdown.MarkdownParser`: CommonMark-compliant Markdown
  parser. Stable slug-based hierarchical section ids. Byte spans.
  Front-matter handling. `raw_text` excludes descendant section bodies.
- `cairn.index.tree`: `TreeBuilder` writes deterministic `tree.json`;
  `Tree` provides `get` / `require` / `roots` / `children_of` /
  `descendants_of` / `ancestors_of` / `outline`.
- `cairn.summarize`: `Summarizer` Protocol + `SummaryLevel` enum +
  `FakeSummarizer` (deterministic, no network) +
  `OpenAICompatibleSummarizer` (Ollama default).
- `cairn.summarize.cache.SummaryCache`: atomic file-system cache keyed
  by `sha256(model || level || section_hash)`.
- `cairn.index.summaries`: `SummaryBuilder` (async, bounded concurrency,
  cache-aware) + `Summaries` reader.
- `cairn.embed`: `Embedder` Protocol + `FakeEmbedder` (BoW hash) +
  `OpenAICompatibleEmbedder` (Ollama default).
- `cairn.index.vectors`: LanceDB-backed `VectorBuilder` + `Vectors` reader
  with cosine similarity search and scope-prefix filter.
- `cairn.tools`: five retrieval tools — `outline`, `get_section`, `expand`,
  `search_semantic`, `search_keyword`. `DocumentIndex` composite loader
  with `doc_id` mismatch detection. `ToolResponse` model with
  `tokens_returned`.
- `cairn.engine`: top-level `Manifest` schema; `Indexer` orchestrator that
  runs all sub-index builders end-to-end.
- `cairn.mcp`: stdio MCP server, dispatch-tool seam, hand-written JSON
  schemas for every tool.
- `cairn.cli`: typer-based CLI — `version`, `index`, `serve`, `outline`,
  `query semantic`, `query keyword`. Env-driven Ollama defaults.

### Phase 2 — Structure-aware retrieval (v0.2)

#### Added
- **v0.2.0** — `cairn.entity` (`EntityExtractor` Protocol +
  `HeuristicExtractor` for code/defined kinds + `FakeEntityExtractor`).
  `cairn.index.entities` (`EntityBuilder` + `Entities` reader with
  canonical / surface-form / by-section / by-kind lookup).
  `cairn.tools.find_mentions` (6th MCP tool).
- **v0.2.2** — `cairn.xref` (`XRefExtractor` Protocol +
  `HeuristicXRefExtractor` covering link / textual / entity-mediated
  edges + `FakeXRefExtractor`). `cairn.index.xrefs` (`XRefBuilder` with
  dedup-by-confidence + `XRefs` reader with outgoing/incoming queries).
  `cairn.tools.get_related` (7th MCP tool) with tree + xref channels.
- **v0.2.3** — `cairn.ingest.pdf.PdfParser` (pymupdf baseline) with
  outline-based and font-heuristic extraction paths.
  `cairn.ingest.parser_for_path` dispatcher; CLI's `cairn index`
  auto-picks the parser for `.md` and `.pdf`.
- **v0.2.4** — `cairn.tools.read_range` (8th MCP tool) completes the
  v0.1 spec catalog. `SummaryBuilder` default levels now include
  `digest`; `get_section(level="digest")` works out of the box.
- **v0.2.6** — `cairn.bench` framework: `BenchSuite` TOML loader,
  `NaiveRAG` baseline (structure-blind 512-word chunks over LanceDB),
  `BenchRunner` orchestrator, recall@k metric, markdown + JSON reports.
  `cairn bench` CLI command. Starter suite in `benchmarks/` with 10
  hand-curated questions over `ARCHITECTURE.md`. Headline (Fake plugins,
  k=8): Cairn returns **25.2% of the tokens** naive RAG returns at
  equal recall.
- **v0.2.7** — `cairn.bench.judge.LLMJudge`: opt-in LLM-as-judge for QA
  accuracy. `cairn bench --judge` runs answer-generation + judging via
  any OpenAI-compatible endpoint. `BenchSummary` carries QA-accuracy
  rows when judging ran.

### Documentation
- `PRODUCT.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `ROADMAP.md`,
  `CONTRIBUTING.md`, `LICENSE` (Apache-2.0).
- `docs/specs/mcp-tools.md`: authoritative tool schemas.
- `docs/canvas.html`: single-file visual explainer comparing Naive RAG,
  RAPTOR, BookRAG, A-RAG, and Cairn.
- `docs/decisions/0001-foundation.md`: founding ADR.
- `examples/hero-demo.md`: self-referential reproducible demo (Cairn
  navigates its own architecture document).
- `benchmarks/README.md`: how to run + how to author suites.

### Tooling
- pyproject: ruff (E F I B UP SIM RUF), mypy strict, pytest with
  asyncio_mode=auto, hypothesis, respx for HTTP mocking.
- 354 unit tests, ~1.2 s total. Mypy strict clean across 57 source
  files. Ruff clean. No network in unit tests.
