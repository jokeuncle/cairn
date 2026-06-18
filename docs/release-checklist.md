# Release Checklist

This checklist is for maintainers preparing a public open-source push or a
tagged alpha release.

## Repository Surface

- README explains the product in the first screen and includes a working
  offline quickstart.
- `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, and issue/PR templates are present.
- `.env.example` contains only placeholders.
- `.cairn/config.toml` is committed if the repository wants a stable Cairn
  docs policy; `.cairn/documents/`, `.cairn/manifest.json`, and generated
  inspectors stay ignored.
- GitHub repository settings are ready:
  - Description: `Repository documentation graph for AI agents`
  - Topics: `mcp`, `rag`, `documents`, `ai-agents`, `python`, `retrieval`
  - Enable private vulnerability reporting under Security settings.

## Local Pre-Push Gate

Run from the repository root:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/cairn-test-venv-py313 uv run --python 3.13 --extra dev ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/cairn-test-venv-py313 uv run --python 3.13 --extra dev mypy src tests
UV_PROJECT_ENVIRONMENT=/tmp/cairn-test-venv-py313 uv run --python 3.13 --extra dev pytest

rm -rf /tmp/cairn-dist
UV_PROJECT_ENVIRONMENT=/tmp/cairn-build-venv-py313 \
  uv run --python 3.13 --with build --with twine \
  python -m build --outdir /tmp/cairn-dist
UV_PROJECT_ENVIRONMENT=/tmp/cairn-build-venv-py313 \
  uv run --python 3.13 --with build --with twine \
  python -m twine check /tmp/cairn-dist/*
```

Expected current gate:

- `ruff check .`: pass
- `mypy src tests`: pass
- `pytest`: 408 passing
- `twine check`: wheel and sdist pass

## Dogfood Checks

```bash
cairn sync --fake
cairn status --json
cairn bench benchmarks/architecture.toml --fake
```

Expected current dogfood:

- Cairn repo: 14/14 docs indexed, 0 errors.
- Starter benchmark: Cairn recall@8 equals naive with 37.8% of naive tokens
  under the deterministic fake embedder.

## External Repository Smoke Tests

The current public-readiness smoke set:

- `https://github.com/astral-sh/uv`
- `https://github.com/modelcontextprotocol/python-sdk`
- `https://github.com/fastapi/full-stack-fastapi-template`

Expected current results with fake plugins:

- `uv`: 89/89 docs indexed, 0 errors; 16-case deep eval top1 12/16,
  top3 16/16, top5 16/16, drilldown 16/16.
- `modelcontextprotocol/python-sdk`: 17/17 docs indexed, 0 errors.
- `fastapi/full-stack-fastapi-template`: 7/7 docs indexed, 0 errors.

Do not tune ranking solely to one repository. Treat failures as signals about
general discovery, evidence, ranking, or drilldown quality.

## Secret And Generated-File Audit

```bash
rg -n "API_KEY=.*[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}" \
  . -g '!*.lance/**' -g '!*.sqlite*' -g '!.cairn/documents/**' -g '!/.git/**'
git status --short --untracked-files=all
git diff --check
```

No real keys should appear. Generated runtime data and lock files created by
one-off local `uv run` commands should not be committed unless intentionally
introduced.

## Tagging

For an alpha release:

```bash
git tag v0.1.0aN
git push origin main --tags
```

The release workflow builds wheel/sdist and attaches them to the GitHub
release. PyPI publishing is intentionally disabled until trusted publishing is
configured for the package.
