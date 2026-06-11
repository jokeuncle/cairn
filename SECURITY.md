# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.0aN (current alpha) | ✅ |
| < 0.1.0 (pre-foundation) | ❌ |

Cairn is in **alpha**. The on-disk index format, the MCP tool schema, and
the Python public APIs are stable within a minor release but may change
between minor releases. We will note breaking changes in `CHANGELOG.md`.

## Reporting a Vulnerability

If you believe you've found a security issue:

1. **Do not** open a public GitHub issue or PR.
2. Email the maintainers at **security@cairn.dev** (placeholder until the
   project has a published address) with:
   - A description of the issue and its impact.
   - Steps to reproduce, ideally a minimal repro.
   - Your suggested severity (optional but appreciated).
3. We will acknowledge receipt within **3 working days** and aim to
   confirm or refute the report within **14 working days**.

## What Counts

We consider the following in scope:

- Cairn's CLI, MCP server, and Python public API in `cairn.*`.
- The `cairn-bench` framework.
- Index file formats and how Cairn handles untrusted input documents
  during ingestion / indexing.

We consider the following **out of scope**:

- Bugs in upstream dependencies (pymupdf, lancedb, mcp, pydantic, …) —
  please report those to their respective projects. We will track and
  upgrade once a fix is available.
- Issues that require write access to the user's `.cairn/` directory or
  that depend on a malicious LLM endpoint configured by the user.

## Local-first defaults

Cairn defaults to **local-only** operation: a local Ollama instance for
summaries and embeddings, a local LanceDB store on disk. No network call
is made under default configuration. Any endpoint override is the user's
explicit opt-in.

## Disclosure

Once a fix is available, we will publish a security advisory referencing
the affected versions and the patched release. Reporters are credited by
name (or by handle, on request) unless they prefer to remain anonymous.
