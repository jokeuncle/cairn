---
name: release-cairn
description: Use when preparing, reviewing, tagging, or publishing a Cairn/docsgraph release, including alpha version bumps, release checklist execution, GitHub release workflow, PyPI Trusted Publishing, post-release verification, and preventing stale-branch or unrelated-change releases.
---

# Release Cairn

Use this skill to ship a public Cairn/docsgraph release from a clean,
up-to-date repository state. The detailed command checklist lives in
`docs/release-checklist.md`; this skill is the execution guardrail for agents.

## Release Rules

- Release from the latest `origin/main`. Fetch first and refuse to publish from
  a stale branch.
- Do not mix unrelated local work into a release. Inspect `git status --short`
  and separate untracked or out-of-scope files before committing.
- Do not publish with secrets, generated indexes, local lock files, build
  artifacts, or dependency folders in the diff.
- Do not publish to PyPI manually from a long-lived token. Tags should trigger
  `.github/workflows/release.yml` with PyPI Trusted Publishing.
- Preserve the distribution name `docsgraph`; never publish this project as
  `cairn`.

## Workflow

1. Establish the baseline.
   - Run `git fetch origin main --tags`.
   - Inspect `git log --oneline --decorate --max-count=20`.
   - If `HEAD` is behind `origin/main`, fast-forward or rebase before release
     work continues.
   - Compare `pyproject.toml`, `src/cairn/__init__.py`, `CHANGELOG.md`, and
     existing tags so the next version is monotonic.

2. Review the working tree.
   - Run `git status --short --untracked-files=all`.
   - Identify unrelated feature work and leave it unstaged.
   - If local tracked work must be moved across a main update, stash tracked
     changes explicitly and keep untracked files visible.
   - Run the review skill or perform a code-review pass before shipping.

3. Update release metadata.
   - Prefer `gh workflow run prepare-release.yml -f version=0.1.0aN`.
   - Locally, run `uv run python scripts/prepare_release.py 0.1.0aN` and then
     `uv run python scripts/prepare_release.py 0.1.0aN --check`.
   - Ensure `CHANGELOG.md` describes the actual public changes and does not
     erase newer release entries.

4. Run the local release gate.
   - `uv run ruff check`
   - `uv run mypy src`
   - `uv run pytest -q`
   - `rm -rf /tmp/cairn-dist && uv build --out-dir /tmp/cairn-dist`
   - `uv publish --dry-run /tmp/cairn-dist/*`
   - Inspect wheel/sdist contents when package data changed.

5. Dogfood Cairn itself.
   - `docsgraph sync --fake`
   - `docsgraph status --json`
   - `docsgraph doctor --fake`
   - `docsgraph mcp config --client codex --fake`
   - `docsgraph bench benchmarks/architecture.toml --fake`
   - For real-provider releases, verify `docsgraph doctor` reports no
     `query_embedding_dim` mismatch with the intended environment.

6. Audit before tagging.
   - Run the secret scan from `docs/release-checklist.md`.
   - Run `git diff --check`.
   - Confirm generated `.cairn/documents/`, `.cairn/manifest.json`,
     `.cairn/sync.lock`, `dist/`, dependency folders, and local client build
     artifacts are not staged unless deliberately part of the release.

7. Publish through GitHub.
   - Commit the release scope.
   - Push the branch or merge to `main` according to project policy.
   - Tag from the release commit: `git tag v0.1.0aN`.
   - Push `main` and tags: `git push origin main --tags`.
   - Watch `.github/workflows/release.yml` until wheel/sdist attach to the
     GitHub release and PyPI Trusted Publishing completes.

8. Verify after publish.
   - Run `uv run python scripts/verify_pypi_install.py --version 0.1.0aN --repo . --sync-repo`.
   - Confirm the GitHub release, PyPI page, and GitHub Pages site reflect the
     same version.
   - If publishing fails after the tag exists, diagnose and rerun the workflow;
     do not create a second tag for the same source unless the source changes.

## Stale Branch Guard

If local `CHANGELOG.md` or version files are older than the latest tag, stop and
sync with `origin/main` before editing. Never release a lower version over a
higher tagged main. This is especially important on long-running feature
branches with uncommitted work.

## References

- `docs/release-checklist.md` for the full command checklist and expected
  release gates.
- `.github/workflows/prepare-release.yml` for automated metadata commits.
- `.github/workflows/release.yml` for build, GitHub release, Pages refresh, and
  PyPI Trusted Publishing.
