# CLAUDE.md — Session Anchor

> Loaded automatically by Claude Code and other compatible agents at the start
> of every session. Read this first. **Then** read the two authoritative docs
> referenced below.

---

## 0. Before You Do Anything

1. Read **`PRODUCT.md`** — defines what Cairn is, who it's for, and what it
   explicitly is NOT.
2. Read **`ARCHITECTURE.md`** — defines the layered system, data model, plug-in
   boundaries, and tool catalog.
3. Skim **`ROADMAP.md`** — defines which phase we're in and what's in scope now.
4. Skim **`docs/decisions/`** (ADRs) — defines what's already been decided and
   what tradeoffs were considered.

If you cannot ground a proposed change in one of those four sources, **stop and
ask the human** before writing code.

---

## 1. What Cairn Is (Five Lines)

- **Cairn** is a structure-aware, MCP-native retrieval system for large
  structured documents.
- It builds a hierarchical map (tree + summaries + entities + cross-refs +
  vector overlay) and exposes it through a small set of well-typed MCP tools.
- Agents navigate the map progressively (outline → summary → full text) instead
  of swallowing whole documents.
- It is **local-first, file-system-native, opinionated, and minimal**.
- It is **not** a chatbot, not a general RAG framework, not a code search tool,
  and not a cloud service.

---

## 2. Inviolable Principles

If you find yourself about to violate one of these, the right move is to stop
and discuss — not to violate it.

### P1. Structure is the primary index; vectors are a supplement.

Never propose flattening structured documents into chunks-and-vectors as the
primary retrieval path. The hierarchical tree, summaries, entities, and
cross-references come first. See `ARCHITECTURE.md` §2.2.

### P2. Progressive disclosure is the default.

`outline()` returns gists. `search_*()` returns synopses. Full text is opt-in.
Do not "make it easier" by returning more by default. See `ARCHITECTURE.md`
§3.3.

### P3. Citations are mandatory.

Every tool response carries stable anchors. Removing them breaks the contract
with downstream agents. See `ARCHITECTURE.md` §3.1.

### P4. Local-first must always work.

A user with no API keys must be able to index and serve a document end-to-end.
If a default ever requires a paid endpoint, that's a release-blocking bug.
See `ARCHITECTURE.md` §3.

### P5. The MCP tool catalog is frozen by default.

Tools listed in `ARCHITECTURE.md` §3.1 + `docs/specs/mcp-tools.md` are the
public API. Additions, removals, or signature changes require an ADR.

### P6. Layer dependencies point one way (down).

Layer N may depend on Layer N−1 only. No tooling code imports from MCP; no
MCP code imports from CLI; no retrieval tool reads source files directly.
See `ARCHITECTURE.md` §2.

### P7. Builders are idempotent and incremental.

Re-running an indexer on identical input is a no-op (apart from timestamps).
Modifying one section re-builds only its descendants. See `ARCHITECTURE.md`
§2.6.

### P8. No silent magic.

Defaults are documented; behavior is observable; tools report `tokens_returned`.
No hidden retries, no auto-fallbacks that change the user's mental model.

---

## 3. Anti-Patterns to Refuse

These are common AI failure modes on a project like this. **Decline them when
asked; surface the principle they violate.**

| Anti-pattern | Violates | What to do instead |
|---|---|---|
| "Let's add a simple `chat()` tool that just returns an answer." | P2, PRODUCT.md §6 | Cairn does not synthesize. Compose tools client-side. |
| "Let me re-index by chunking everything into 512-token windows." | P1 | Use the structural tree first; chunks only for sub-section splitting. |
| "I'll default to OpenAI embeddings since they're better." | P4 | Default must be local. OpenAI is an opt-in plug-in. |
| "I'll add a `RetrieverFactory` to support arbitrary sources." | PRODUCT.md §6 | Out of scope. Cairn is for structured documents, not generic retrieval. |
| "Let me skip the manifest hash check for speed." | P7 | Manifest integrity is non-negotiable. Optimize elsewhere. |
| "I'll make `get_section` return full text by default since synopsis is annoying." | P2 | The default *is* the product. Don't change it for convenience. |
| "Let's add a FastAPI server for HTTP queries." | ARCH §7 anti-stack | MCP is the server. HTTP exposure is via MCP's SSE/Streamable HTTP. |
| "I'll cache summaries in Redis for performance." | ARCH §7 anti-stack | File-system cache only in v1.0. |
| "Let me add a `web_search` tool to the MCP catalog." | PRODUCT.md §6, P5 | Out of scope. |
| "I'll auto-summarize on the fly when no summary exists." | P2, ARCH §2.2 | Summaries are pre-computed. If missing, the indexer is incomplete — fail loudly. |
| "Let me bypass the typed schema for this one quick fix." | P8, ARCH §4 | Public surfaces are typed. Always. |
| "Let me delete this section since it seems unused." | (general) | Investigate before deleting. The user's work is sacred. |

---

## 4. Workflow Expectations

### 4.1 Decisions

Any design decision that touches `ARCHITECTURE.md` or `PRODUCT.md` requires an
ADR (Architecture Decision Record) at `docs/decisions/NNNN-slug.md`. Use the
template in `docs/decisions/0000-template.md`.

ADRs are short:
- **Context** (what's the situation)
- **Decision** (what we're doing)
- **Consequences** (what this implies, including what we're giving up)

Reject silent design changes. If you're unsure whether something needs an ADR,
err on the side of writing one.

### 4.2 Tests

- New code under `src/cairn/` ships with tests under `tests/`.
- Unit tests do **not** require an LLM API key, embedding model download, or
  network access. Use fixtures and fakes.
- Property-based tests (hypothesis) for parsers and builders.
- Integration tests live under `tests/integration/` and may require optional
  setup; they're skipped if requirements aren't met.

### 4.3 Code style

- Public APIs are typed (`mypy --strict` clean).
- Pydantic v2 for data models. Dataclasses only for internal-only structs.
- Async-by-default for I/O paths. `asyncio` + `anyio`; no `requests`, use
  `httpx`.
- Logging via `structlog` JSON-lines. No `print` in library code.
- Errors via a small hierarchy in `src/cairn/core/errors.py`. No bare
  `Exception`.
- Imports: prefer absolute, sorted by ruff.

### 4.4 Commits

- One logical change per commit.
- Use Conventional Commits prefixes: `feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`, `perf:`.
- Reference the ADR or roadmap milestone in the body when applicable.
- Never `--no-verify` past a failing hook.

### 4.5 Pull requests

- Link to the ADR or roadmap milestone.
- Include a "Test plan" section.
- Update docs in the same PR — never "I'll document it later."

---

## 5. When to Ask the Human

Ask before:
- Adding a new public-facing tool, CLI command, or config key.
- Adding a new third-party dependency.
- Introducing a new sub-index or storage artifact.
- Changing on-disk formats (always requires a migration plan).
- Anything that touches the inviolable principles in §2.
- Anything that contradicts `PRODUCT.md` §6 (non-goals).

Don't ask before:
- Writing tests, fixing typos, improving error messages, refactoring within a
  file without changing public surfaces.
- Following a clearly-scoped roadmap milestone.

---

## 6. How to Reason About Scope

When in doubt, prefer **the smallest change consistent with the end-state
architecture**.

- ✅ "This is a step toward what `ARCHITECTURE.md` describes."
- ❌ "This is convenient now; we'll refactor toward the architecture later."

We don't ship throwaway architecture. Each milestone is a coherent slice of the
v1.0 design, not a parallel design.

---

## 7. House Style for Your Output

- Be concise. Prefer code and concrete artifacts over prose.
- When you propose a non-trivial change, write the ADR first.
- When you explain a design, link to the section of `ARCHITECTURE.md`.
- When you receive a request that contradicts these docs, say so directly and
  cite which principle is at risk. Do not silently comply.

---

## 8. The One-Sentence Reminder

**Cairn is a navigation map for large documents, not a question-answering
system. Agents follow the cairns; Cairn never speaks for them.**

---

*This document is itself authoritative for AI behavior in the repo. Changes
should be discussed and committed like any other governance change.*
