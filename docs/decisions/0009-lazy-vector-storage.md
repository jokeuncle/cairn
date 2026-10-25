# ADR-0009: Defer vector storage imports and table opening

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Maintainer (real Agent connection reliability)
- **Related:** ARCHITECTURE.md §2/§3; ADR-0005

## Context

A real Codex CLI connection timed out during MCP initialization. An instrumented
retry observed 34 seconds between `initialize` and its response. Python stack
samples located the delay in eagerly importing LanceDB's generated namespace
client models. The imports were unnecessary for handshaking, tool listing,
outlines and original section reads.

## Decision

Import LanceDB/PyArrow only for vector writes or the first vector read. Loading
`Vectors` validates its manifest and database directory, then retains a lazy
table handle. Open the table once under a lock inside the existing worker-thread
paths. Preserve all vector data formats, IDs and numerical operations.

## Consequences and verification

MCP initialization and structural reads no longer require importing vector
storage. The first vector query still pays its actual cold import/open cost.
Corrupt table errors occur on vector use; missing manifests/directories still
fail when loading the handle. This does not hide a bad vector store or replace
semantic search with another retrieval method.

A fresh-process regression blocks storage imports and proves server import,
outline and full-body reads still work. Existing vector build/read/search tests
and the full suite must pass. Repeat actual Codex MCP connectivity checks and
retain the original timeout, traffic log and stack samples.
