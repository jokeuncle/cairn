"""Typer-based command-line interface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from cairn import __version__
from cairn.cli.config import load_embed_config, load_index_config, load_llm_config
from cairn.embed.base import Embedder
from cairn.engine.indexer import Indexer
from cairn.entity.heuristic import HeuristicExtractor
from cairn.ingest import parser_for_path
from cairn.inspection import write_inspector
from cairn.providers import make_embedder, make_summarizer
from cairn.repo import (
    RepoStatus,
    find_repo_root,
    load_repo_document_index,
    repo_status,
    sync_repo,
    write_default_config,
)
from cairn.summarize.base import Summarizer
from cairn.tools.base import DocumentIndex
from cairn.tools.find_mentions import find_mentions as find_mentions_tool
from cairn.tools.get_related import get_related as get_related_tool
from cairn.tools.outline import outline as outline_tool
from cairn.tools.search_keyword import Mode
from cairn.tools.search_keyword import search_keyword as search_keyword_tool
from cairn.tools.search_semantic import search_semantic as search_semantic_tool
from cairn.xref.heuristic import HeuristicXRefExtractor

app = typer.Typer(
    name="cairn",
    help="Local-first documentation graph for AI agents.",
    no_args_is_help=True,
)
query_app = typer.Typer(help="Run a single retrieval tool from the command line.")
mcp_app = typer.Typer(help="Generate MCP client configuration snippets.")
app.add_typer(query_app, name="query")
app.add_typer(mcp_app, name="mcp")

McpClient = Literal["claude", "cursor", "codex", "goose"]


# ---------------------------------------------------------------------------
# Plugin construction
# ---------------------------------------------------------------------------


def _make_summarizer(use_fake: bool) -> Summarizer:
    return make_summarizer(use_fake)


def _make_embedder(use_fake: bool) -> Embedder:
    return make_embedder(use_fake)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def init(
    yes: Annotated[
        bool,
        typer.Option(
            "-y",
            "--yes",
            help="Create .cairn/config.toml without prompting.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing .cairn/config.toml."),
    ] = False,
    markitdown: Annotated[
        bool,
        typer.Option(
            "--markitdown",
            help="Include MarkItDown-backed Office/data/web globs in config.",
        ),
    ] = False,
) -> None:
    """Initialize Cairn for repository documentation indexing."""
    root = Path.cwd()
    config_file = root / ".cairn" / "config.toml"
    if config_file.exists() and not force:
        typer.echo(f"already initialized: {config_file}")
        return
    if not yes and not typer.confirm(f"Create {config_file}?"):
        raise typer.Exit(code=1)
    written = write_default_config(root, force=force, enable_markitdown=markitdown)
    typer.echo(f"initialized: {written}")


@app.command()
def sync(
    fake: Annotated[
        bool,
        typer.Option(
            "--fake",
            help="Use deterministic FakeSummarizer + FakeEmbedder (no network).",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Rebuild every configured document."),
    ] = False,
) -> None:
    """Index every configured repository document under .cairn/documents/."""
    asyncio.run(_run_sync(fake, force))


async def _run_sync(use_fake: bool, force: bool) -> None:
    root = find_repo_root()
    results = await sync_repo(
        root,
        summarizer=_make_summarizer(use_fake),
        embedder=_make_embedder(use_fake),
        index_config=load_index_config(),
        force=force,
        progress=lambda message: typer.echo(message, err=True),
    )
    failed = sum(1 for item in results if not item.ok)
    successful = len(results) - failed
    rebuilt = sum(1 for item in results if item.ok and item.rebuilt)
    skipped = successful - rebuilt
    typer.echo(
        "synced: "
        f"{successful}/{len(results)} documents "
        f"({rebuilt} rebuilt, {skipped} up to date, {failed} failed)"
    )
    if failed:
        raise typer.Exit(code=1)


@app.command()
def status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON."),
    ] = False,
) -> None:
    """Show repository documentation index status."""
    root = find_repo_root()
    status_obj = repo_status(root)
    if json_output:
        typer.echo(status_obj.model_dump_json(indent=2))
        return
    typer.echo(_format_repo_status(status_obj))


@app.command()
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON."),
    ] = False,
) -> None:
    """Check repo setup, index freshness, and model configuration."""
    checks = _doctor_checks()
    ok = all(item["ok"] for item in checks)
    payload = {
        "ok": ok,
        "version": __version__,
        "checks": checks,
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(_format_doctor(payload))
    if not ok:
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the Cairn version."""
    typer.echo(__version__)


@app.command()
def index(
    source: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    doc_id: Annotated[
        str | None,
        typer.Option(help="Override the document id (defaults to filename stem)."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(help="Output directory. Defaults to .cairn/documents/<doc_id>/."),
    ] = None,
    fake: Annotated[
        bool,
        typer.Option(
            "--fake",
            help="Use deterministic FakeSummarizer + FakeEmbedder (no network).",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Rebuild even if the source file is unchanged since last index.",
        ),
    ] = False,
) -> None:
    """Index a source document — build Tree + Summaries + Vectors."""
    asyncio.run(_run_index(source, doc_id, out, fake, force))


async def _run_index(
    source: Path,
    doc_id: str | None,
    out: Path | None,
    use_fake: bool,
    force: bool,
) -> None:
    parser = parser_for_path(source)
    resolved_doc_id = doc_id or source.stem
    out_dir = out or Path.cwd() / ".cairn" / "documents" / resolved_doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    index_cfg = load_index_config()

    indexer = Indexer(
        parser=parser,
        summarizer=_make_summarizer(use_fake),
        embedder=_make_embedder(use_fake),
        entity_extractor=HeuristicExtractor(),
        xref_extractor=HeuristicXRefExtractor(),
        summary_concurrency=index_cfg.summary_concurrency,
        embed_batch_size=index_cfg.embed_batch_size,
        progress=lambda message: typer.echo(message, err=True),
    )
    result = await indexer.index_path(
        source, out_dir=out_dir, doc_id=doc_id, force=force
    )
    if result.rebuilt:
        typer.echo(f"indexed: {result.manifest_path}")
    else:
        typer.echo(f"already up to date: {result.manifest_path}")


@app.command()
def serve(
    doc_dir: Annotated[
        Path | None,
        typer.Argument(
            file_okay=False,
            dir_okay=True,
            readable=True,
            help=(
                "Built document directory. Omit to serve the current repo's "
                ".cairn documents."
            ),
        ),
    ] = None,
    fake: Annotated[
        bool,
        typer.Option(
            "--fake",
            help="Use FakeEmbedder for query embedding (no network at query time).",
        ),
    ] = False,
    repo: Annotated[
        Path | None,
        typer.Option(
            "--repo",
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Repository root or child path containing .cairn/config.toml.",
        ),
    ] = None,
) -> None:
    """Start the MCP stdio server against a document or repo index."""
    from cairn.mcp.server import serve_repo_stdio, serve_stdio

    if repo is not None and doc_dir is not None:
        typer.echo("error: pass either a document directory or --repo, not both", err=True)
        raise typer.Exit(code=2)
    if repo is not None:
        asyncio.run(serve_repo_stdio(find_repo_root(repo), embedder=_make_embedder(fake)))
        return
    if doc_dir is None:
        asyncio.run(serve_repo_stdio(find_repo_root(), embedder=_make_embedder(fake)))
        return
    if not doc_dir.exists() or not doc_dir.is_dir():
        typer.echo(f"error: document directory not found: {doc_dir}", err=True)
        raise typer.Exit(code=2)
    asyncio.run(serve_stdio(doc_dir, embedder=_make_embedder(fake)))


@mcp_app.command("config")
def mcp_config(
    client: Annotated[
        McpClient,
        typer.Option(
            "--client",
            case_sensitive=False,
            help="Client snippet to print: claude, cursor, codex, or goose.",
        ),
    ] = "claude",
    repo: Annotated[
        Path | None,
        typer.Option(
            "--repo",
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Repository root. Defaults to the nearest .cairn/config.toml.",
        ),
    ] = None,
    command: Annotated[
        str,
        typer.Option(
            "--command",
            help="Executable path clients should run.",
        ),
    ] = "cairn",
    fake: Annotated[
        bool,
        typer.Option(
            "--fake",
            help="Include --fake for deterministic local smoke tests.",
        ),
    ] = False,
) -> None:
    """Print a copy-pasteable MCP stdio configuration snippet."""
    root = find_repo_root(repo)
    args = ["serve", "--repo", str(root)]
    if fake:
        args.append("--fake")
    typer.echo(_format_mcp_config(client, command=command, args=args))


@app.command()
def outline(
    doc_dir: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, dir_okay=True, readable=True),
    ],
    depth: Annotated[int, typer.Option(min=1, max=6)] = 2,
    focus: Annotated[
        str | None, typer.Option(help="Restrict to a subtree.")
    ] = None,
) -> None:
    """Print the document outline as JSON."""
    asyncio.run(_run_outline(doc_dir, depth, focus))


async def _run_outline(doc_dir: Path, depth: int, focus: str | None) -> None:
    idx = DocumentIndex.load(doc_dir)
    resp = await outline_tool(idx, depth=depth, focus=focus, include=("gist",))
    typer.echo(json.dumps(resp.data, ensure_ascii=False, indent=2))


@query_app.command("semantic")
def query_semantic(
    doc_dir: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, dir_okay=True, readable=True),
    ],
    query: Annotated[str, typer.Argument(help="Query string.")],
    k: Annotated[int, typer.Option(min=1, max=32)] = 8,
    fake: Annotated[bool, typer.Option("--fake")] = False,
) -> None:
    """Run a semantic search and print results as JSON."""
    asyncio.run(_run_search_semantic(doc_dir, query, k, fake))


async def _run_search_semantic(
    doc_dir: Path, query: str, k: int, use_fake: bool
) -> None:
    idx = DocumentIndex.load(doc_dir)
    embedder = _make_embedder(use_fake)
    resp = await search_semantic_tool(idx, embedder=embedder, query=query, k=k)
    typer.echo(json.dumps(resp.data, ensure_ascii=False, indent=2))


@query_app.command("keyword")
def query_keyword(
    doc_dir: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, dir_okay=True, readable=True),
    ],
    terms: Annotated[list[str], typer.Argument(help="One or more search terms.")],
    k: Annotated[int, typer.Option(min=1, max=32)] = 12,
    mode: Annotated[str, typer.Option(help="any | all")] = "any",
) -> None:
    """Run a keyword search and print results as JSON."""
    asyncio.run(_run_search_keyword(doc_dir, terms, k, mode))


async def _run_search_keyword(
    doc_dir: Path, terms: list[str], k: int, mode: str
) -> None:
    if mode not in ("any", "all"):
        typer.echo(f"error: mode must be 'any' or 'all'; got {mode!r}", err=True)
        raise typer.Exit(code=2)
    cast_mode: Mode = mode  # type: ignore[assignment]
    idx = DocumentIndex.load(doc_dir)
    resp = await search_keyword_tool(idx, terms=terms, k=k, mode=cast_mode)
    typer.echo(json.dumps(resp.data, ensure_ascii=False, indent=2))


@query_app.command("mentions")
def query_mentions(
    doc_dir: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, dir_okay=True, readable=True),
    ],
    entity: Annotated[str, typer.Argument(help="Entity name (canonical or surface form).")],
    scope: Annotated[
        str | None,
        typer.Option(help="Restrict to a section-id prefix."),
    ] = None,
) -> None:
    """Locate every section that mentions an entity."""
    asyncio.run(_run_find_mentions(doc_dir, entity, scope))


async def _run_find_mentions(
    doc_dir: Path, entity: str, scope: str | None
) -> None:
    idx = DocumentIndex.load(doc_dir)
    resp = await find_mentions_tool(idx, entity=entity, scope=scope)
    typer.echo(json.dumps(resp.data, ensure_ascii=False, indent=2))


@query_app.command("related")
def query_related(
    doc_dir: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, dir_okay=True, readable=True),
    ],
    section_id: Annotated[str, typer.Argument(help="Section id to find neighbors of.")],
    kinds: Annotated[
        str,
        typer.Option(help="Comma-separated channels: xref,sibling,parent,child"),
    ] = "xref",
    k: Annotated[int, typer.Option(min=1, max=32)] = 8,
) -> None:
    """Return neighbors of a section across the xref graph and tree."""
    parsed = tuple(s.strip() for s in kinds.split(",") if s.strip())
    asyncio.run(_run_get_related(doc_dir, section_id, parsed, k))


async def _run_get_related(
    doc_dir: Path, section_id: str, kinds: tuple[str, ...], k: int
) -> None:
    idx = DocumentIndex.load(doc_dir)
    resp = await get_related_tool(idx, id=section_id, kinds=kinds, k=k)  # type: ignore[arg-type]
    typer.echo(json.dumps(resp.data, ensure_ascii=False, indent=2))


@app.command()
def inspect(
    doc_dir: Annotated[
        Path | None,
        typer.Argument(
            file_okay=False,
            dir_okay=True,
            readable=True,
            help=(
                "Built document directory. Omit to inspect the current repo's "
                "primary Cairn document."
            ),
        ),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            help=(
                "HTML output path. Defaults to <doc_dir>/inspector.html for "
                "single-doc mode or .cairn/inspector.html for repo mode."
            )
        ),
    ] = None,
    doc: Annotated[
        str | None,
        typer.Option(help="Repo document id to inspect when doc_dir is omitted."),
    ] = None,
) -> None:
    """Generate a standalone HTML inspector for a document index."""
    if doc_dir is None:
        root = find_repo_root()
        idx = load_repo_document_index(root, doc_id=doc)
        out_path = out or root / ".cairn" / "inspector.html"
    else:
        if not doc_dir.exists() or not doc_dir.is_dir():
            typer.echo(f"error: document directory not found: {doc_dir}", err=True)
            raise typer.Exit(code=2)
        idx = DocumentIndex.load(doc_dir)
        out_path = out or doc_dir / "inspector.html"
    written = write_inspector(idx, out=out_path)
    typer.echo(f"inspector: {written}")


@app.command()
def bench(
    suite: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    k: Annotated[int, typer.Option(min=1, max=32)] = 8,
    out: Annotated[
        Path | None,
        typer.Option(help="Where to write the JSON report."),
    ] = None,
    fake: Annotated[
        bool,
        typer.Option("--fake", help="Use FakeSummarizer + FakeEmbedder (deterministic, offline)."),
    ] = False,
    judge: Annotated[
        bool,
        typer.Option(
            "--judge",
            help="Run LLM-as-judge for QA accuracy (uses CAIRN_LLM_* settings).",
        ),
    ] = False,
) -> None:
    """Run a benchmark suite comparing Cairn against a naive vector-RAG baseline."""
    asyncio.run(_run_bench(suite, k, out, fake, judge))


async def _run_bench(
    suite_path: Path,
    k: int,
    out: Path | None,
    use_fake: bool,
    use_judge: bool,
) -> None:
    from cairn.bench.dataset import load_suite
    from cairn.bench.judge import LLMJudge
    from cairn.bench.report import format_markdown_report, write_json_report
    from cairn.bench.runner import BenchOptions, BenchRunner

    suite = load_suite(suite_path)

    judge_client: LLMJudge | None = None
    if use_judge:
        cfg = load_llm_config()
        judge_client = LLMJudge(
            base_url=cfg.base_url,
            model=cfg.model,
            api_key=cfg.api_key,
        )

    index_cfg = load_index_config()
    runner = BenchRunner(
        summarizer=_make_summarizer(use_fake),
        embedder=_make_embedder(use_fake),
        judge=judge_client,
        options=BenchOptions(
            k=k,
            summary_concurrency=index_cfg.summary_concurrency,
            embed_batch_size=index_cfg.embed_batch_size,
        ),
        progress=lambda message: typer.echo(message, err=True),
    )

    import tempfile

    with tempfile.TemporaryDirectory(prefix="cairn-bench-") as work_str:
        work_dir = Path(work_str)
        summary = await runner.run(suite, work_dir=work_dir)

    typer.echo(format_markdown_report(summary))

    out_path = out or Path("/tmp/cairn-bench") / f"{suite_path.stem}.json"
    write_json_report(summary, out_path)
    typer.echo(f"\njson report written → {out_path}", err=True)


def _format_repo_status(status_obj: RepoStatus) -> str:
    lines = [
        f"Cairn repo: {status_obj.root}",
        f"config: {status_obj.config_path}",
        (
            "documents: "
            f"{status_obj.indexed_count} indexed, "
            f"{status_obj.stale_count} stale, "
            f"{status_obj.missing_count} missing, "
            f"{status_obj.error_count} errors"
        ),
        "",
        "| state | doc | sections | source |",
        "|---|---|---:|---|",
    ]
    for doc in status_obj.documents:
        sections = "" if doc.section_count is None else str(doc.section_count)
        lines.append(f"| {doc.state} | `{doc.id}` | {sections} | {doc.source} |")
    return "\n".join(lines)


def _doctor_checks() -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    try:
        root = find_repo_root()
    except Exception as exc:
        return [
            {
                "name": "repo_config",
                "ok": False,
                "message": f"{exc}. Run `cairn init -y` first.",
            }
        ]

    checks.append(
        {
            "name": "repo_config",
            "ok": True,
            "message": f"found {root / '.cairn' / 'config.toml'}",
        }
    )
    try:
        status_obj = repo_status(root)
        unhealthy = (
            status_obj.missing_count
            + status_obj.stale_count
            + status_obj.error_count
        )
        checks.append(
            {
                "name": "repo_index",
                "ok": unhealthy == 0 and status_obj.indexed_count > 0,
                "message": (
                    f"{status_obj.indexed_count} indexed, "
                    f"{status_obj.stale_count} stale, "
                    f"{status_obj.missing_count} missing, "
                    f"{status_obj.error_count} errors"
                ),
            }
        )
        if status_obj.primary_doc:
            primary_ok = any(
                doc.id == status_obj.primary_doc and doc.state == "indexed"
                for doc in status_obj.documents
            )
            checks.append(
                {
                    "name": "primary_doc",
                    "ok": primary_ok,
                    "message": status_obj.primary_doc,
                }
            )
    except Exception as exc:
        checks.append(
            {
                "name": "repo_index",
                "ok": False,
                "message": f"{exc}. Run `cairn sync --fake` to build locally.",
            }
        )

    llm = load_llm_config()
    embed = load_embed_config()
    checks.append(
        {
            "name": "summarizer",
            "ok": bool(llm.model and llm.base_url),
            "message": f"{llm.model} at {llm.base_url}",
        }
    )
    checks.append(
        {
            "name": "embedder",
            "ok": bool(embed.model and embed.base_url and embed.dim > 0),
            "message": f"{embed.provider}:{embed.model} dim={embed.dim}",
        }
    )
    return checks


def _format_doctor(payload: dict[str, object]) -> str:
    checks = payload["checks"]
    assert isinstance(checks, list)
    lines = [f"Cairn doctor: {'ok' if payload['ok'] else 'needs attention'}"]
    for item in checks:
        assert isinstance(item, dict)
        marker = "ok" if item["ok"] else "!!"
        lines.append(f"[{marker}] {item['name']}: {item['message']}")
    if not payload["ok"]:
        lines.append("")
        lines.append("Next steps: run `cairn init -y`, then `cairn sync --fake`.")
    return "\n".join(lines)


def _format_mcp_config(client: McpClient, *, command: str, args: list[str]) -> str:
    server = {"command": command, "args": args}
    if client in {"claude", "cursor"}:
        return json.dumps({"mcpServers": {"cairn": server}}, indent=2)
    if client == "codex":
        quoted_args = ", ".join(json.dumps(arg) for arg in args)
        return "\n".join(
            [
                "[mcp_servers.cairn]",
                f"command = {json.dumps(command)}",
                f"args = [{quoted_args}]",
            ]
        )
    yaml_args = "\n".join(f"      - {json.dumps(arg)}" for arg in args)
    return "\n".join(
        [
            "extensions:",
            "  cairn:",
            "    type: stdio",
            f"    command: {json.dumps(command)}",
            "    args:",
            yaml_args,
        ]
    )


if __name__ == "__main__":
    app()
