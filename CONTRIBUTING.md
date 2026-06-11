# Contributing to Cairn

Thank you for your interest in Cairn. This project is **deliberately opinionated**;
your effort is most valuable when it advances the design described in
`PRODUCT.md` and `ARCHITECTURE.md`. Please read both before opening a PR.

---

## Before You Write Code

1. Read `PRODUCT.md` (especially §6 Non-Goals).
2. Read `ARCHITECTURE.md` (the layered design, plug-in boundaries, data model).
3. Skim `ROADMAP.md` to see which phase we're in.
4. Skim `docs/decisions/` to avoid re-litigating settled choices.
5. If your change touches `PRODUCT.md`, `ARCHITECTURE.md`, the MCP tool
   catalog, or on-disk formats: **write an ADR first** (see below).

---

## The ADR Process

We use lightweight [Architecture Decision Records](https://adr.github.io/) for
any design decision that affects:

- Product scope or non-goals
- Layer boundaries or data model
- The MCP tool catalog
- On-disk formats
- Plug-in interfaces
- Third-party dependencies

To propose:

1. Copy `docs/decisions/0000-template.md` to a new file numbered sequentially.
2. Fill in *Context*, *Decision*, *Consequences*, and *Alternatives Considered*.
3. Open a PR titled `ADR: <slug>` — discussion happens in the PR.
4. On merge, the ADR is binding until superseded by another ADR.

ADRs are short (one page is ideal). They document *why*, not *how*.

---

## Development Workflow

### Setup

```bash
# Clone
git clone https://github.com/jokeuncle/cairn.git
cd cairn

# Use uv (preferred) or pip with a venv
uv sync --extra dev
# or:
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Tasks

```bash
# Lint + format
uv run ruff check src tests
uv run ruff format src tests

# Type check
uv run mypy src/cairn

# Tests (unit only; no network, no models)
uv run pytest tests/unit -q

# Tests including integration (requires optional setup)
uv run pytest -q
```

### Branching and commits

- Branch off `main`.
- One logical change per commit.
- Conventional Commits prefix required: `feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`, `perf:`.
- Reference the ADR or roadmap milestone in the commit body when applicable.

### Pull requests

A PR should include:

- A short summary of *what* and *why*.
- A link to the relevant ADR (if any).
- A "Test plan" section: what you ran, what passed.
- Doc updates in the **same** PR — never "I'll document it later."

CI must be green before merge. We rebase-and-merge to keep history linear.

---

## Code Style

Source of truth: `pyproject.toml` (ruff + mypy config).

- Python 3.11+.
- `mypy --strict` clean on `src/cairn/`.
- Public surfaces are typed; pydantic v2 for data models.
- Async-by-default for I/O; `httpx`, not `requests`.
- Logging via `structlog` JSON-lines. No `print` in library code.
- Errors via the hierarchy in `src/cairn/core/errors.py`. No bare `Exception`.

Comments: default to none. Only write a comment when the *why* is non-obvious.
Don't explain what well-named code already says.

---

## Testing Philosophy

- **Unit tests must not require an LLM key, embedding model download, or
  network access.** Use fakes for `Summarizer`, `Embedder`, `VectorStore`.
- **Property-based tests** (hypothesis) for parsers and builders.
- **Integration tests** under `tests/integration/` may require optional setup;
  they're skipped if requirements aren't met.
- Target ≥ 85% line coverage on `src/cairn/`. Coverage gaps need justification.

A good test:

- Has a single behavior under test.
- Builds inputs from named factories, not opaque fixtures.
- Asserts the public contract, not internal state.

---

## Documentation

- User-facing changes update `README.md` and/or `docs/`.
- Architectural changes update `ARCHITECTURE.md` **and** ship an ADR.
- The MCP tool catalog lives in `docs/specs/mcp-tools.md` — changes there are
  always breaking until v1.0.

---

## Reporting Bugs

Please file an issue with:

- Cairn version (`cairn --version`) and Python version.
- A minimal reproducer (ideally a small document and a command).
- Expected vs. actual behavior.
- Any error log lines (JSON-lines from `cairn serve` are very helpful).

---

## Security

Do not file security issues in public. See `SECURITY.md` (added before v0.2)
for the disclosure process. In Phase 0/1, please email the maintainer directly.

---

## Code of Conduct

We follow the [Contributor Covenant](https://www.contributor-covenant.org/).
Be excellent to each other; we're all here to make navigation easier.

---

## A Note for AI Agents

If you are an AI agent helping a human contributor, your operating instructions
live in `CLAUDE.md` at the repo root. Read that first. The principles there
are not suggestions.
