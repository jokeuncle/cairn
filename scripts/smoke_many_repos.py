"""Run broad repository smoke tests for Cairn repo-document mode.

This is not an accuracy benchmark. It stress-tests discovery, indexing,
repo search, drilldown, failure isolation, and latency across many public
repositories with deterministic fake plugins.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cairn.cli.config import IndexConfig
from cairn.embed.fake import FakeEmbedder
from cairn.mcp.server import dispatch_repo_tool
from cairn.repo import repo_status, sync_repo, write_default_config
from cairn.summarize.fake import FakeSummarizer

RepoSpec = dict[str, str]


SMOKE_REPOS: tuple[RepoSpec, ...] = (
    {"name": "uv", "url": "https://github.com/astral-sh/uv"},
    {"name": "pydantic-ai", "url": "https://github.com/pydantic/pydantic-ai"},
    {"name": "mcp-python-sdk", "url": "https://github.com/modelcontextprotocol/python-sdk"},
    {"name": "fastapi-template", "url": "https://github.com/fastapi/full-stack-fastapi-template"},
    {"name": "flask", "url": "https://github.com/pallets/flask"},
    {"name": "httpx", "url": "https://github.com/encode/httpx"},
    {"name": "requests", "url": "https://github.com/psf/requests"},
    {"name": "pytest", "url": "https://github.com/pytest-dev/pytest"},
    {"name": "mkdocs", "url": "https://github.com/mkdocs/mkdocs"},
    {"name": "pydantic", "url": "https://github.com/pydantic/pydantic"},
    {"name": "rich", "url": "https://github.com/Textualize/rich"},
    {"name": "typer", "url": "https://github.com/fastapi/typer"},
    {"name": "click", "url": "https://github.com/pallets/click"},
    {"name": "starlette", "url": "https://github.com/encode/starlette"},
    {"name": "black", "url": "https://github.com/psf/black"},
    {"name": "ruff", "url": "https://github.com/astral-sh/ruff"},
    {"name": "poetry", "url": "https://github.com/python-poetry/poetry"},
    {"name": "httpie", "url": "https://github.com/httpie/cli"},
    {"name": "vite", "url": "https://github.com/vitejs/vite"},
    {"name": "react", "url": "https://github.com/facebook/react"},
    {"name": "tailwindcss", "url": "https://github.com/tailwindlabs/tailwindcss"},
    {"name": "express", "url": "https://github.com/expressjs/express"},
    {"name": "prisma", "url": "https://github.com/prisma/prisma"},
    {"name": "svelte", "url": "https://github.com/sveltejs/svelte"},
    {"name": "react-router", "url": "https://github.com/remix-run/react-router"},
    {"name": "mdbook", "url": "https://github.com/rust-lang/mdBook"},
    {"name": "ripgrep", "url": "https://github.com/BurntSushi/ripgrep"},
    {"name": "fd", "url": "https://github.com/sharkdp/fd"},
    {"name": "clap", "url": "https://github.com/clap-rs/clap"},
    {"name": "github-cli", "url": "https://github.com/cli/cli"},
    {"name": "helm", "url": "https://github.com/helm/helm"},
    {"name": "k6", "url": "https://github.com/grafana/k6"},
    {"name": "fastapi", "url": "https://github.com/fastapi/fastapi"},
    {"name": "textual", "url": "https://github.com/Textualize/textual"},
    {"name": "openai-python", "url": "https://github.com/openai/openai-python"},
    {
        "name": "anthropic-sdk-python",
        "url": "https://github.com/anthropics/anthropic-sdk-python",
    },
    {
        "name": "mcp-typescript-sdk",
        "url": "https://github.com/modelcontextprotocol/typescript-sdk",
    },
)

SMOKE_QUERIES: tuple[str, ...] = (
    "installation",
    "configuration",
    "testing",
    "deployment",
    "authentication",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("/tmp/cairn-many-repo-smoke"),
        help="Directory for shallow clones and generated indexes.",
    )
    parser.add_argument("--refresh", action="store_true", help="Delete clones first.")
    parser.add_argument("--limit", type=int, default=len(SMOKE_REPOS))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero unless every selected repo succeeds, sync has zero "
            "document failures, every query has hits, and every drilldown works."
        ),
    )
    parser.add_argument(
        "--min-ok-repos",
        type=int,
        default=None,
        help="Minimum successful repositories required before exiting 0.",
    )
    parser.add_argument(
        "--max-sync-failures",
        type=int,
        default=None,
        help="Maximum allowed per-document sync failures.",
    )
    parser.add_argument(
        "--min-queries-with-hits",
        type=int,
        default=None,
        help="Minimum number of query rows that must return at least one hit.",
    )
    parser.add_argument(
        "--min-drilldowns-ok",
        type=int,
        default=None,
        help="Minimum number of top-hit drilldowns that must succeed.",
    )
    parser.add_argument(
        "--queries",
        nargs="*",
        default=list(SMOKE_QUERIES),
        help="Smoke queries to run against every repo.",
    )
    return parser.parse_args()


def ensure_clone(spec: RepoSpec, workdir: Path, *, refresh: bool) -> Path:
    root = workdir / spec["name"]
    if refresh and root.exists():
        shutil.rmtree(root)
    if root.exists():
        return root
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "git",
                "-c",
                "http.version=HTTP/1.1",
                "clone",
                "--depth",
                "1",
                spec["url"],
                str(root),
            ],
            check=True,
        )
    except Exception:
        if root.exists():
            shutil.rmtree(root)
        raise
    return root


def latency_summary(values: Iterable[float]) -> dict[str, float]:
    collected = list(values)
    if not collected:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(collected)
    p95_index = min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))
    return {
        "avg": round(statistics.fmean(collected), 2),
        "p50": round(statistics.median(collected), 2),
        "p95": round(ordered[p95_index], 2),
        "max": round(max(collected), 2),
    }


async def evaluate_repo(
    spec: RepoSpec,
    args: argparse.Namespace,
    embedder: FakeEmbedder,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        root = ensure_clone(spec, args.workdir, refresh=bool(args.refresh))
        write_default_config(root, force=True)
        sync_results = await sync_repo(
            root,
            summarizer=FakeSummarizer(),
            embedder=embedder,
            index_config=IndexConfig(),
        )
        status = repo_status(root)
        query_rows: list[dict[str, Any]] = []
        latencies: list[float] = []
        drilldown_ok = 0
        hit_queries = 0
        for query in args.queries:
            query_started = time.perf_counter()
            env = await dispatch_repo_tool(
                "search_documents",
                {"query": query, "k": args.k, "sections_per_doc": 1},
                root,
                embedder,
            )
            elapsed_ms = (time.perf_counter() - query_started) * 1000
            latencies.append(elapsed_ms)
            hits = env.get("data", {}).get("hits", []) if env.get("ok") else []
            hit_queries += bool(hits)
            drill_ok = False
            if hits:
                drill = await dispatch_repo_tool(
                    "get_section",
                    {
                        "doc": hits[0]["doc"],
                        "id": hits[0]["id"],
                        "level": "synopsis",
                    },
                    root,
                    embedder,
                )
                drill_ok = bool(drill.get("ok"))
                drilldown_ok += drill_ok
            query_rows.append(
                {
                    "query": query,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "hit_count": len(hits),
                    "top_doc": hits[0]["doc"] if hits else None,
                    "top_title": hits[0]["title"] if hits else None,
                    "drilldown_ok": drill_ok,
                }
            )
        total_elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "name": spec["name"],
            "url": spec["url"],
            "ok": True,
            "elapsed_ms": round(total_elapsed_ms, 2),
            "sync": {
                "total": len(sync_results),
                "ok": sum(1 for result in sync_results if result.ok),
                "failed": sum(1 for result in sync_results if not result.ok),
            },
            "status": {
                "indexed": status.indexed_count,
                "stale": status.stale_count,
                "missing": status.missing_count,
                "errors": status.error_count,
            },
            "search": {
                "queries": len(query_rows),
                "with_hits": hit_queries,
                "drilldown": drilldown_ok,
                "latency_ms": latency_summary(latencies),
            },
            "rows": query_rows,
        }
    except Exception as exc:
        return {
            "name": spec["name"],
            "url": spec["url"],
            "ok": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": str(exc),
        }


async def run() -> None:
    args = parse_args()
    selected = SMOKE_REPOS[: max(0, args.limit)]
    embedder = FakeEmbedder(dim=64)
    rows = [await evaluate_repo(spec, args, embedder) for spec in selected]
    ok_rows = [row for row in rows if row.get("ok")]
    report = {
        "repos": len(rows),
        "ok": sum(1 for row in rows if row.get("ok")),
        "failed": sum(1 for row in rows if not row.get("ok")),
        "indexed_docs": sum(row.get("status", {}).get("indexed", 0) for row in ok_rows),
        "sync_failures": sum(row.get("sync", {}).get("failed", 0) for row in ok_rows),
        "query_count": sum(row.get("search", {}).get("queries", 0) for row in ok_rows),
        "queries_with_hits": sum(row.get("search", {}).get("with_hits", 0) for row in ok_rows),
        "drilldowns_ok": sum(row.get("search", {}).get("drilldown", 0) for row in ok_rows),
        "rows": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    failures = smoke_gate_failures(
        report,
        strict=bool(args.strict),
        min_ok_repos=args.min_ok_repos,
        max_sync_failures=args.max_sync_failures,
        min_queries_with_hits=args.min_queries_with_hits,
        min_drilldowns_ok=args.min_drilldowns_ok,
    )
    if failures:
        print("strict smoke gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise SystemExit(1)


def smoke_gate_failures(
    report: dict[str, Any],
    *,
    strict: bool,
    min_ok_repos: int | None = None,
    max_sync_failures: int | None = None,
    min_queries_with_hits: int | None = None,
    min_drilldowns_ok: int | None = None,
) -> list[str]:
    """Return unmet smoke thresholds for CI/release gating."""
    repos = int(report.get("repos", 0))
    query_count = int(report.get("query_count", 0))
    required_ok_repos = repos if strict and min_ok_repos is None else min_ok_repos
    allowed_sync_failures = (
        0 if strict and max_sync_failures is None else max_sync_failures
    )
    required_hit_queries = (
        query_count
        if strict and min_queries_with_hits is None
        else min_queries_with_hits
    )
    required_drilldowns = (
        query_count if strict and min_drilldowns_ok is None else min_drilldowns_ok
    )

    failures: list[str] = []
    ok_repos = int(report.get("ok", 0))
    failed_repos = int(report.get("failed", 0))
    sync_failures = int(report.get("sync_failures", 0))
    queries_with_hits = int(report.get("queries_with_hits", 0))
    drilldowns_ok = int(report.get("drilldowns_ok", 0))

    if strict and failed_repos:
        failures.append(f"{failed_repos} repositories failed")
    if required_ok_repos is not None and ok_repos < required_ok_repos:
        failures.append(f"ok repos {ok_repos} < required {required_ok_repos}")
    if allowed_sync_failures is not None and sync_failures > allowed_sync_failures:
        failures.append(
            f"sync failures {sync_failures} > allowed {allowed_sync_failures}"
        )
    if required_hit_queries is not None and queries_with_hits < required_hit_queries:
        failures.append(
            f"queries with hits {queries_with_hits} < required {required_hit_queries}"
        )
    if required_drilldowns is not None and drilldowns_ok < required_drilldowns:
        failures.append(
            f"drilldowns ok {drilldowns_ok} < required {required_drilldowns}"
        )
    return failures


if __name__ == "__main__":
    asyncio.run(run())
