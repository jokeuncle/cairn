# Docsgraph Diagnostics And Index Contract Design

## Scope

Implement the recommended open-source-quality fixes for repository documentation indexing:
document discovery visibility, sync dry-run, embedder provenance and compatibility checks,
user-facing mismatch errors, doctor configuration transparency, repo-wide keyword search,
Markdown frontmatter metadata, and empty-section evidence handling.

## Behavior Contract

`docsgraph discover` and `docsgraph sync --dry-run` share one discovery report. The report
classifies files as configured/indexed, candidate-but-not-included, excluded, or unsupported,
with deterministic relative paths and reasons. Dry-run never writes document indexes.

Document manifests record embedder provenance for new indexes: mode, provider/name, model
identity when available, and embedding dimension. Legacy manifests remain readable, but doctor
reports missing provenance.

`docsgraph serve` validates fixed document or repository indexes before accepting queries. A
query/index embedder mismatch fails fast with a direct explanation and actionable commands. MCP
repo tools surface the same mismatch details for dynamically resolved workspaces.

`docsgraph doctor` reports repo/index status plus the active CLI query embedder and index
embedder provenance. It does not claim to introspect an already-running MCP process; when that is
not knowable, it says so explicitly and points to the generated MCP command/config.

Repo-scoped `search_keyword` searches all indexed/stale documents when `doc` is omitted and
continues to search one document when `doc` is provided. Hits include `doc` and `source`.

Markdown frontmatter is parsed as generic metadata. Supported fields include title, description,
tags, date, and draft. Metadata contributes to embedding/search text and appears in returned
payloads with match-source attribution where practical.

Empty sections are navigation nodes. They should not be promoted as primary evidence when a
non-empty child can answer better; hits that remain navigation-only are marked as such.

## Verification

Tests cover report classification, dry-run no writes, manifest provenance, doctor/serve mismatch
messages, repo-wide keyword behavior, frontmatter metadata indexing, and empty-section ranking.
Regression runs include the targeted unit tests and the relevant CLI/MCP integration paths.
