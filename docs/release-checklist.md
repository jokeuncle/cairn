# Release Checklist

This checklist is for maintainers preparing a public open-source push or a
tagged alpha release.

## Repository Surface

- README explains the product in the first screen and includes a working
  offline quickstart.
- The PyPI distribution name is `cairn-docs`; the installed CLI command remains
  `cairn`. Do not publish this project as `cairn`, which is already occupied
  on PyPI by an unrelated package.
- `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, and issue/PR templates are present.
- `.env.example` contains only placeholders.
- `.cairn/config.toml` is committed if the repository wants a stable Cairn
  docs policy; `.cairn/documents/`, `.cairn/manifest.json`, and generated
  inspectors stay ignored.
- GitHub repository settings are ready:
  - Description: `Repository documentation graph for AI agents`
  - Topics: `mcp`, `mcp-server`, `rag`, `documents`, `documentation`,
    `ai-agents`, `python`, `retrieval`, `repository`
  - Discussions are enabled; Wiki is disabled unless there is a deliberate
    docs plan for it.
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
- `pytest`: 419 passing
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

- `pydantic/pydantic-ai`: 178/178 docs indexed, 0 errors; 8-case deep
  eval top1 8/8, top5 8/8, drilldown 8/8.
- `uv`: 89/89 docs indexed, 0 errors; 16-case deep eval top1 15/16,
  top3 16/16, top5 16/16, drilldown 16/16.
- `modelcontextprotocol/python-sdk`: 17/17 docs indexed, 0 errors; 4-case
  deep eval top1 4/4, drilldown 4/4.
- `fastapi/full-stack-fastapi-template`: 7/7 docs indexed, 0 errors; 4-case
  deep eval top1 4/4, drilldown 4/4.
- `scripts/smoke_many_repos.py --limit 32`: 1076 docs indexed across 32
  repos, 0 sync failures, 160/160 searches with hits, 160/160 drilldowns.

Do not tune ranking solely to one repository. Treat failures as signals about
general discovery, evidence, ranking, or drilldown quality.

Run:

```bash
python scripts/eval_repos.py --repo all --refresh
python scripts/smoke_many_repos.py --limit 32 --refresh
```

Run at least one real-provider eval before claiming production retrieval
quality. Keep credentials in environment variables only; do not pass them on
the command line or write them into files:

```bash
python scripts/eval_repos.py --repo pydantic-ai \
  --provider env \
  --workdir /tmp/cairn-repo-eval-real \
  --refresh
```

For Doubao, the intended environment shape is:

```bash
export CAIRN_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
export CAIRN_LLM_MODEL=doubao-seed-2-0-code-preview-260215
export CAIRN_EMBED_PROVIDER=doubao-vision
export CAIRN_EMBED_MODEL=doubao-embedding-vision-251215
```

The corresponding API key variables must be set locally, but real values must
never appear in git, shell history snippets, benchmark reports, or CI logs.

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
