# Release Checklist

This checklist is for maintainers preparing a public open-source push or a
tagged alpha release.

Agents should invoke the internal `release-cairn` skill first. The skill
enforces the release workflow order, stale-branch guard, unrelated-change
isolation, and post-publish verification; this checklist remains the detailed
command reference.

## Repository Surface

- README explains the product in the first screen and includes a working
  offline quickstart.
- The PyPI distribution name is `docsgraph`; the primary installed CLI command
  is `docsgraph`, with `cairn` retained as a compatibility alias. Do not publish
  this project as `cairn`, which is already occupied on PyPI by an unrelated
  package.
- `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, and issue/PR templates are present.
- `docs/golden-docs-standard.md` reflects the current repo-search preferences
  and any new broadly tuned ranking/discovery rule.
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

For release metadata, prefer the automated GitHub workflow:

```bash
gh workflow run prepare-release.yml -f version=0.1.0aN
```

That workflow updates `pyproject.toml`, `src/cairn/__init__.py`, README release
text, and `CHANGELOG.md`, then commits the release-prep change to `main`.
Locally, the equivalent command is:

```bash
python scripts/prepare_release.py 0.1.0aN
python scripts/prepare_release.py 0.1.0aN --check
```

Run from the repository root:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/cairn-test-venv-py313 uv run --python 3.13 --extra dev ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/cairn-test-venv-py313 uv run --python 3.13 --extra dev mypy --python-version 3.13 src tests
UV_PROJECT_ENVIRONMENT=/tmp/cairn-test-venv-py313 uv run --python 3.13 --extra dev pytest

rm -rf /tmp/cairn-dist
uv build --out-dir /tmp/cairn-dist
uv publish --dry-run /tmp/cairn-dist/*
```

Expected current gate:

- `ruff check .`: pass
- `mypy --python-version 3.13 src tests`: pass
- `pytest`: pass
- `uv publish --dry-run`: wheel and sdist pass upload validation

## Dogfood Checks

```bash
docsgraph sync --fake
docsgraph status --json
docsgraph doctor --fake
docsgraph mcp config --client codex --fake
docsgraph bench benchmarks/architecture.toml --fake
```

Expected current dogfood:

- Cairn repo: 18/18 docs indexed, 0 errors.
- Starter benchmark: Cairn recall@8 equals naive with 37.7% of naive tokens
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
- `scripts/smoke_many_repos.py --limit 37`: 2931 docs indexed across 37
  repos, 0 sync failures, 185/185 searches with hits, 185/185 drilldowns.

Do not tune ranking solely to one repository. Treat failures as signals about
general discovery, evidence, ranking, or drilldown quality.

Run:

```bash
python scripts/eval_repos.py --repo all --refresh --strict
python scripts/smoke_many_repos.py --limit 37 --refresh --strict
```

Run at least one real-provider eval before claiming production retrieval
quality. Keep credentials in environment variables only; do not pass them on
the command line or write them into files:

```bash
python scripts/eval_repos.py --repo pydantic-ai \
  --provider env \
  --workdir /tmp/cairn-repo-eval-real \
  --refresh \
  --strict
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
When dogfooding MCP against a real provider, install or print the server config
with explicit environment variables rather than relying on a shell startup file:

```bash
docsgraph mcp config --client codex --repo . --env-from-current
docsgraph doctor
```

`doctor` must not report `query_embedding_dim` mismatch before release.

## Website Publishing

The product website lives in `docs/index.html` and static assets under
`docs/assets/`. GitHub Pages deploys the whole `docs/` directory on every
`main` push. It also redeploys after every successful Release workflow, so each
version tag refreshes the product site after PyPI publishing and release
artifact attachment succeed.

Repository homepage URL:

```text
https://jokeuncle.github.io/cairn/
```

Keep the GitHub repository "Website" field pointed at that URL so visitors can
open the product site from the repository sidebar.

Before a release, verify the Pages workflow exists and the site renders locally
from `docs/index.html`; the release workflow will republish the same site
artifact after it succeeds.

## Trusted Publishing

Public PyPI publishing must use GitHub OIDC Trusted Publishing, not a long-lived
API token in a local shell. Configure PyPI before pushing a release tag:

- Project: `docsgraph`
- Owner / repository: `jokeuncle/cairn`
- Workflow: `.github/workflows/release.yml`
- Environment: `pypi`

In GitHub, create the `pypi` environment and require maintainer approval if the
repository is not fully locked down. Revoke any account-wide PyPI token used for
manual bootstrapping after the first project-scoped setup is in place.

After the tag workflow publishes, verify the official source install from a
clean temporary environment:

```bash
python scripts/verify_pypi_install.py --version "$(uv run docsgraph version)" --repo . --sync-repo
```

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
release. It also publishes to PyPI through Trusted Publishing when the `pypi`
environment is approved and the PyPI project trusts this workflow.
