"""Evaluate Cairn's repo-document workflow on public repositories.

This is a smoke benchmark, not a leaderboard. It checks three practical things:

- discovery/sync completes without per-document failures;
- cross-document search puts an acceptable doc in the top-k;
- top hits can be drilled into with normal MCP tools.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

from cairn.cli.config import IndexConfig
from cairn.embed.fake import FakeEmbedder
from cairn.mcp.server import dispatch_repo_tool
from cairn.repo import repo_status, sync_repo, write_default_config
from cairn.summarize.fake import FakeSummarizer

RepoCase = dict[str, Any]


REPOS: dict[str, dict[str, Any]] = {
    "uv": {
        "url": "https://github.com/astral-sh/uv",
        "cases": [
            {
                "id": "install-uv",
                "query": "how to install uv",
                "acceptable": {
                    "docs-getting-started-installation",
                    "docs-reference-installer",
                    "readme",
                    "docs-index",
                },
            },
            {
                "id": "uninstall-uv",
                "query": "how to uninstall uv standalone installer",
                "acceptable": {
                    "docs-getting-started-installation",
                    "docs-reference-installer",
                },
            },
            {
                "id": "tools-run",
                "query": "run Python command line tools with uvx",
                "acceptable": {"docs-guides-tools", "docs-concepts-tools", "readme"},
            },
            {
                "id": "tools-install",
                "query": "install command line tools with uv tool install",
                "acceptable": {
                    "docs-guides-tools",
                    "docs-concepts-tools",
                    "docs-reference-storage",
                    "readme",
                },
            },
            {
                "id": "github-actions",
                "query": "set up uv in GitHub Actions cache",
                "acceptable": {"docs-guides-integration-github"},
            },
            {
                "id": "docker-integration",
                "query": "using uv in Docker image",
                "acceptable": {"docs-guides-integration-docker"},
            },
            {
                "id": "dependency-resolution",
                "query": "dependency resolution rules and resolver behavior",
                "acceptable": {
                    "docs-concepts-resolution",
                    "docs-reference-internals-resolver",
                    "benchmarks",
                },
            },
            {
                "id": "dependency-groups",
                "query": "development dependency groups in projects",
                "acceptable": {
                    "docs-concepts-projects-dependencies",
                    "docs-concepts-projects-config",
                },
            },
            {
                "id": "project-sync",
                "query": "sync project environment from lockfile",
                "acceptable": {
                    "docs-concepts-projects-sync",
                    "docs-guides-projects",
                    "docs-getting-started-first-steps",
                },
            },
            {
                "id": "workspaces",
                "query": "workspace members in uv projects",
                "acceptable": {"docs-concepts-projects-workspaces"},
            },
            {
                "id": "python-versions",
                "query": "install and pin Python versions with uv",
                "acceptable": {
                    "docs-concepts-python-versions",
                    "docs-guides-install-python",
                    "readme",
                },
            },
            {
                "id": "cache",
                "query": "where does uv store cache and tools",
                "acceptable": {"docs-concepts-cache", "docs-reference-storage"},
            },
            {
                "id": "auth-cli",
                "query": "authenticate to package indexes with uv auth login",
                "acceptable": {
                    "docs-concepts-authentication-cli",
                    "docs-concepts-authentication-http",
                    "docs-concepts-authentication-index",
                },
            },
            {
                "id": "publish-package",
                "query": "publish a package to a package index",
                "acceptable": {"docs-guides-package", "docs-pip-packages"},
            },
            {
                "id": "pip-compile",
                "query": "compile requirements with uv pip compile",
                "acceptable": {"docs-pip-compile", "docs-pip-compatibility"},
            },
            {
                "id": "troubleshoot-build",
                "query": "troubleshoot package build failures",
                "acceptable": {
                    "docs-reference-troubleshooting-build-failures",
                    "docs-reference-troubleshooting-index",
                },
            },
        ],
    },
    "mcp-python-sdk": {
        "url": "https://github.com/modelcontextprotocol/python-sdk",
        "cases": [
            {
                "id": "server-tool",
                "query": "how do I create an MCP server tool",
                "acceptable": {"readme", "readme-v2"},
            },
            {
                "id": "http-transport",
                "query": "streamable http server transport",
                "acceptable": {"readme", "readme-v2", "docs-low-level-server"},
            },
            {
                "id": "authorization",
                "query": "authorization oauth provider",
                "acceptable": {"readme", "readme-v2", "docs-authorization"},
            },
            {
                "id": "migration",
                "query": "migration from older sdk version",
                "acceptable": {"docs-migration", "release"},
            },
        ],
    },
    "pydantic-ai": {
        "url": "https://github.com/pydantic/pydantic-ai",
        "cases": [
            {
                "id": "tools",
                "query": "how do tools work in agents",
                "acceptable": {"docs-tools", "docs-tools-advanced"},
            },
            {
                "id": "mcp-server",
                "query": "how to expose an MCP server from pydantic ai",
                "acceptable": {"docs-mcp-server"},
            },
            {
                "id": "openai-models",
                "query": "configure OpenAI model settings",
                "acceptable": {"docs-models", "docs-models-openai"},
            },
            {
                "id": "message-history",
                "query": "reuse message history in conversations",
                "acceptable": {"docs-message-history"},
            },
            {
                "id": "multi-agent",
                "query": "build multi agent handoffs between agents",
                "acceptable": {"docs-multi-agent-applications"},
            },
            {
                "id": "streaming",
                "query": "stream structured responses and events from a run",
                "acceptable": {"docs-agent", "docs-output"},
            },
            {
                "id": "testing-evals",
                "query": "evaluate agents and write tests",
                "acceptable": {
                    "docs-evals",
                    "docs-evals-online-evaluation",
                    "docs-testing-evals",
                },
            },
            {
                "id": "dependencies",
                "query": "inject dependencies into agent runs",
                "acceptable": {"docs-dependencies"},
            },
        ],
    },
    "fastapi-template": {
        "url": "https://github.com/fastapi/full-stack-fastapi-template",
        "cases": [
            {
                "id": "backend-dev",
                "query": "backend development docker compose",
                "acceptable": {"backend-readme", "development"},
            },
            {
                "id": "frontend-dev",
                "query": "frontend development commands",
                "acceptable": {"frontend-readme", "readme", "development"},
            },
            {
                "id": "deployment",
                "query": "deployment docker swarm",
                "acceptable": {"deployment", "readme"},
            },
            {
                "id": "release-notes",
                "query": "release notes",
                "acceptable": {"release-notes", "readme"},
            },
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        choices=[*REPOS.keys(), "all"],
        default="all",
        help="Which public repo suite to run.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("/tmp/cairn-repo-eval"),
        help="Directory for shallow clones and .cairn indexes.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Delete existing clones before cloning.",
    )
    parser.add_argument("--k", type=int, default=5)
    return parser.parse_args()


def ensure_clone(name: str, url: str, workdir: Path, *, refresh: bool) -> Path:
    root = workdir / name
    if refresh and root.exists():
        shutil.rmtree(root)
    if root.exists():
        return root
    workdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(root)],
        check=True,
    )
    return root


def latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))
    return {
        "avg": round(statistics.fmean(values), 2),
        "p50": round(statistics.median(values), 2),
        "p95": round(ordered[p95_index], 2),
        "max": round(max(values), 2),
    }


async def evaluate_repo(
    name: str,
    spec: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    root = ensure_clone(name, str(spec["url"]), args.workdir, refresh=bool(args.refresh))
    write_default_config(root, force=True)
    embedder = FakeEmbedder(dim=64)
    results = await sync_repo(
        root,
        summarizer=FakeSummarizer(),
        embedder=embedder,
        index_config=IndexConfig(),
    )
    status = repo_status(root)
    rows = []
    top1 = 0
    top3 = 0
    top5 = 0
    drilldown = 0
    latencies: list[float] = []
    for case in spec["cases"]:
        started = time.perf_counter()
        env = await dispatch_repo_tool(
            "search_documents",
            {"query": case["query"], "k": args.k, "sections_per_doc": 1},
            root,
            embedder,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        hits = env["data"]["hits"] if env.get("ok") else []
        docs = [hit["doc"] for hit in hits]
        acceptable = set(case["acceptable"])
        top1_hit = bool(docs and docs[0] in acceptable)
        top3_hit = bool(set(docs[:3]) & acceptable)
        top5_hit = bool(set(docs[:5]) & acceptable)
        top1 += top1_hit
        top3 += top3_hit
        top5 += top5_hit
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
            drilldown += drill_ok
        rows.append(
            {
                "id": case["id"],
                "query": case["query"],
                "acceptable": sorted(acceptable),
                "elapsed_ms": round(elapsed_ms, 2),
                "top_docs": docs,
                "top_titles": [hit["title"] for hit in hits],
                "top1_hit": top1_hit,
                "top3_hit": top3_hit,
                "top5_hit": top5_hit,
                "drilldown_ok": drill_ok,
            }
        )
    total = len(spec["cases"])
    return {
        "name": name,
        "url": spec["url"],
        "root": str(root),
        "sync": {
            "total": len(results),
            "ok": sum(1 for result in results if result.ok),
            "failed": sum(1 for result in results if not result.ok),
        },
        "status": {
            "indexed": status.indexed_count,
            "stale": status.stale_count,
            "missing": status.missing_count,
            "errors": status.error_count,
        },
        "cases": total,
        "top1": f"{top1}/{total}",
        "top3": f"{top3}/{total}",
        "top5": f"{top5}/{total}",
        "drilldown": f"{drilldown}/{total}",
        "latency_ms": latency_summary(latencies),
        "rows": rows,
    }


async def run() -> None:
    args = parse_args()
    selected = REPOS if args.repo == "all" else {args.repo: REPOS[args.repo]}
    report = [
        await evaluate_repo(name, spec, args)
        for name, spec in selected.items()
    ]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
