# Changelog

All notable changes to Cairn. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once it reaches 1.0.

## Unreleased

No unreleased changes yet.

## [0.1.0a6] — 2026-06-26

### Changed

- **`find_mentions` now returns every section a term occurs in, not just the
  defining site.** The offline entity extractor was rewritten as a two-pass,
  deterministic pipeline (`heuristic:regex-v2`, ADR-0003): pass 1 builds a
  per-document vocabulary from code identifiers, `**bold**` terms, definitional
  section headings, and multi-word Title-Case proper nouns; pass 2 scans every
  section body for whole-word occurrences. Precision gates keep the result
  clean — `code` terms count only inside code spans, and single lowercase
  English words are rejected as entities — cutting noise roughly 3× on
  documentation-heavy files while surfacing real symbols and glossary terms.
  Re-index (`cairn sync --force`) to upgrade existing indexes; the new
  extractor name is recorded in `entities.json`. Entity schema and the MCP tool
  catalog are unchanged.

## [0.1.0a5] — 2026-06-26

### Added

- **MCP server instructions.** The stdio server now advertises an MCP
  `instructions` string — a document-mode and a repository-mode variant — so
  clients can inject "when to reach for Cairn" guidance into the agent's system
  prompt. This is the highest-leverage lever for getting agents to choose Cairn
  over ad-hoc grepping. See ADR-0002.

### Changed

- **Intent-first MCP tool descriptions.** Every tool description was rewritten
  from a capability statement ("Dense vector search.") to an intent trigger
  ("Use when the user asks about a concept…"). `repo_context` is now flagged as
  the repository entry point, stale "v0.2+"/reserved wording was removed from
  tools that work today, and envelope/`trace.steps` plumbing was dropped from
  the repo-document tool descriptions. Tool names and schemas are unchanged
  (the frozen catalog is untouched). See ADR-0002 and `docs/specs/mcp-tools.md`.
- **Concurrent Doubao embeddings.** `DoubaoVisionEmbedder` now issues up to
  `concurrency` (default 8) `/embeddings/multimodal` requests in flight instead
  of strictly serial, preserving input order and cancelling in-flight siblings
  cleanly when one request fails.

### Fixed

- **Circular import between `cairn.providers` and the CLI layer.** Runtime
  configuration moved from `cairn.cli.config` to `cairn.core.config` so lower
  layers can read it without importing the CLI package (CLAUDE.md P6).
  `cairn.providers` (and evaluation scripts) can now be imported standalone.
  `cairn.cli.config` remains as a backward-compatible re-export.

## [0.1.0a4] — 2026-06-23

### Added

- Product website under `docs/index.html`, deployed to GitHub Pages on `main`
  pushes and after successful release workflows.

### Changed

- Repo-scoped MCP config now defaults to dynamic workspace resolution
  (`args = ["serve"]`) instead of pinning the repo where `docsgraph install` ran.
  Use `--repo` for a fixed-repo server, or per-call `projectPath` for explicit
  cross-repo queries.
- PyPI project metadata and README now point the project homepage to the
  GitHub Pages site.
- GitHub Actions workflows now use current major versions to avoid deprecated
  Node runtime warnings.
- First-run website and contributor docs now prefer the `docsgraph` command and
  deterministic `--fake` smoke-test path.
- Added support and editor-configuration metadata for contributor onboarding.
- Added a GitHub Sponsor entry plus website and support-page links for optional
  project sponsorship.

## [0.1.0a3] — 2026-06-22

### Added

- **Doubao multimodal embeddings.** `CAIRN_EMBED_PROVIDER=doubao-vision`
  targets Volcengine ARK's `/embeddings/multimodal` shape and defaults to
  `doubao-embedding-vision-251215` with 2048-dimensional vectors.
- **Static graph inspector.** `docsgraph inspect <doc-dir> --out inspector.html`
  writes a standalone HTML relationship explorer for sections, entities,
  tree edges, mentions, and cross-references.
- **Semantic hit evidence.** `search_semantic` now returns an explanatory
  `evidence` window by default, including CJK-friendly query-term extraction.
- **Hosted API stability knobs.** LLM and embedding clients now support
  timeout and retry env vars. Indexing and benchmark runs honor summary
  concurrency and embedding batch-size env vars.
- **Benchmark/index progress output.** CLI indexing and benchmark runs now
  emit stage progress so hosted-model runs do not sit silently during long
  summary-generation phases.
- **Repository documentation workflow.** `docsgraph init -y`, `docsgraph sync`,
  `docsgraph status`, repo-scoped `docsgraph serve`, and repo-scoped
  `docsgraph inspect`
  turn a project directory into a multi-document MCP knowledge layer. Repo MCP
  adds `list_documents`, cross-document `search_documents`, `repo_context`,
  `repo_graph`, `repo_impact`, and routes normal tools by optional `doc`.
  Repo sync isolates per-document failures so one bad source does not block the
  rest of the repository index.
- **Configurable repo search policy.** `.cairn/config.toml` exposes
  `include`, `exclude`, `enable_markitdown`, `primary_doc`, and
  `search_sections_per_doc` so repositories can tune coverage, conversion,
  and cross-document search diversity without changing code.
- **Safer monorepo discovery defaults.** Simple directory excludes such as
  `node_modules/**`, `dist/**`, and `.pytest_cache/**` now apply at any depth,
  so broad include globs do not accidentally index frontend dependencies,
  caches, or generated build output.
- **Open-source DX commands.** `docsgraph doctor` validates repo setup and index
  freshness; `docsgraph mcp config` prints MCP snippets for Claude, Cursor,
  Codex, and Goose. `docsgraph serve --repo <path>` makes generated configs
  independent from the client's working directory.
- **Agent self-install command.** `docsgraph install` writes the Cairn MCP
  server config for Codex, Claude, Cursor, or Goose, while
  `docsgraph install --dry-run` prints the target path and config without
  touching disk.
- **Public repo smoke evaluator.** `scripts/eval_repos.py` reproduces the
  uv / MCP Python SDK / FastAPI template repo-document smoke tests used for
  release readiness.
- **Strict repo gates.** `scripts/eval_repos.py --strict` and
  `scripts/smoke_many_repos.py --strict` exit non-zero when sync, top-k, hit, or
  drilldown thresholds fail, making repo regressions CI/release-gate friendly.
- **Golden documentation standard.** `docs/golden-docs-standard.md` publishes
  the repo-doc shapes Cairn rewards and the tuning policy maintainers must
  follow when mature-repository smoke runs expose quality gaps.
- **PyPI installation verifier.** `scripts/verify_pypi_install.py` installs a
  released `docsgraph` wheel from the official Python index into a clean
  temporary environment and checks both `docsgraph` and `cairn` console scripts.
- **Optional MarkItDown ingestion.** Installing `docsgraph[markitdown]` lets Cairn
  convert local DOCX, PPTX, XLSX, HTML, CSV, JSON, XML, EPUB, and related files
  to Markdown before indexing them through the canonical Markdown pipeline.

### Changed

- README and benchmark docs now report the latest starter benchmark numbers
  with evidence snippets included in semantic-search payloads.
- Repo-scoped `search_documents` now uses a manifest-backed process cache and
  flat in-memory section scoring, improving repeated MCP queries on docs-heavy
  repositories while preserving deterministic fake-embedder behavior. Repo
  status now records file-level fingerprints, and search/context responses expose
  `stale_documents` when sources changed after the last sync.
- Repo-scoped search internals moved into `cairn.repo_search`, keeping
  `cairn.repo` as the lifecycle/API surface while isolating ranker and cache
  complexity for future performance work.
- Repo-scoped dense-vector scoring is now batched through a warm in-memory
  matrix, reducing Python-loop overhead on large repositories while retaining
  full fallback recall.
- Large repo search now uses a two-stage warm-query path: dense vector seeds,
  cheap lexical/path seeds, and graph neighbors form a wide shortlist before the
  full BM25/graph/explanation ranker runs. Search responses expose ranker mode
  and section counts for observability.
- Repo search locale detection now recognizes script/region path segments such
  as `zh-hant`, `pt-br`, and `en-us`, and shortlist graph scoring no longer
  inflates local neighborhoods when some neighbors are outside the candidate
  set.
- Repo-scoped cold search-cache construction now loads per-document indexes
  concurrently with bounded read parallelism and per-document failure isolation.
- Repo-scoped ranking now intent-gates changelog, release-note, and migration
  history documents so broad topic queries prefer guides/API docs/README-style
  docs while explicit release/version/change queries still retrieve history docs.
- Repo-scoped ranking now supports `preferred_locales` in `.cairn/config.toml`
  and auto-prefers English/locale-neutral docs for English queries when
  multilingual documentation trees contain equivalent pages.
- Repo-scoped MCP dispatch now returns the same structured `INVALID_INPUT`
  envelope for bad tool arguments as single-document dispatch.
- Repo search results now prioritize document diversity before returning
  multiple sections from the same document, reducing duplicate-heavy top-k
  answers in large documentation sets.
- The static inspector now reuses SVG nodes between frames, stops animating
  after layout stabilization, and hides non-neighbor labels by default so large
  relation graphs remain responsive.
- The PyPI distribution name is now `docsgraph`; the primary CLI is
  `docsgraph`, and `cairn` remains a compatibility alias. This keeps the
  Cairn product name while making the installed tool obvious and avoiding the
  unrelated package that already occupies `cairn`.
- Strict mypy now passes across both `src` and `tests`.
- The release workflow now runs lint, type checks, tests, build validation, and
  PyPI Trusted Publishing from the `pypi` GitHub environment on version tags.

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
- `docs/retrieval-architecture-canvas.html`: single-file visual explainer
  comparing Naive RAG, RAPTOR, BookRAG, A-RAG, and Cairn.
- `docs/decisions/0001-foundation.md`: founding ADR.
- `examples/hero-demo.md`: self-referential reproducible demo (Cairn
  navigates its own architecture document).
- `benchmarks/README.md`: how to run + how to author suites.

### Tooling
- pyproject: ruff (E F I B UP SIM RUF), mypy strict, pytest with
  asyncio_mode=auto, hypothesis, respx for HTTP mocking.
- 354 unit tests, ~1.2 s total. Mypy strict clean across 57 source
  files. Ruff clean. No network in unit tests.
