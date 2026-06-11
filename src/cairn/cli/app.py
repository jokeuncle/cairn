"""Typer-based command-line interface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from cairn import __version__
from cairn.cli.config import load_embed_config, load_llm_config
from cairn.embed.base import Embedder
from cairn.embed.fake import FakeEmbedder
from cairn.embed.openai_compatible import OpenAICompatibleEmbedder
from cairn.engine.indexer import Indexer
from cairn.ingest.markdown import MarkdownParser
from cairn.summarize.base import Summarizer
from cairn.summarize.fake import FakeSummarizer
from cairn.summarize.openai_compatible import OpenAICompatibleSummarizer
from cairn.tools.base import DocumentIndex
from cairn.tools.outline import outline as outline_tool
from cairn.tools.search_keyword import Mode
from cairn.tools.search_keyword import search_keyword as search_keyword_tool
from cairn.tools.search_semantic import search_semantic as search_semantic_tool

app = typer.Typer(
    name="cairn",
    help="Structure-aware, MCP-native retrieval for large documents.",
    no_args_is_help=True,
)
query_app = typer.Typer(help="Run a single retrieval tool from the command line.")
app.add_typer(query_app, name="query")


# ---------------------------------------------------------------------------
# Plugin construction
# ---------------------------------------------------------------------------


def _make_summarizer(use_fake: bool) -> Summarizer:
    if use_fake:
        return FakeSummarizer()
    cfg = load_llm_config()
    return OpenAICompatibleSummarizer(
        base_url=cfg.base_url,
        model=cfg.model,
        api_key=cfg.api_key,
    )


def _make_embedder(use_fake: bool) -> Embedder:
    if use_fake:
        return FakeEmbedder(dim=64)
    cfg = load_embed_config()
    return OpenAICompatibleEmbedder(
        base_url=cfg.base_url,
        model=cfg.model,
        dim=cfg.dim,
        api_key=cfg.api_key,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


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
) -> None:
    """Index a source document — build Tree + Summaries + Vectors."""
    asyncio.run(_run_index(source, doc_id, out, fake))


async def _run_index(
    source: Path,
    doc_id: str | None,
    out: Path | None,
    use_fake: bool,
) -> None:
    parser = MarkdownParser()
    resolved_doc_id = doc_id or source.stem
    out_dir = out or Path.cwd() / ".cairn" / "documents" / resolved_doc_id
    out_dir.mkdir(parents=True, exist_ok=True)

    indexer = Indexer(
        parser=parser,
        summarizer=_make_summarizer(use_fake),
        embedder=_make_embedder(use_fake),
    )
    manifest_path = await indexer.index_path(
        source, out_dir=out_dir, doc_id=doc_id
    )
    typer.echo(f"indexed: {manifest_path}")


@app.command()
def serve(
    doc_dir: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, dir_okay=True, readable=True),
    ],
    fake: Annotated[
        bool,
        typer.Option(
            "--fake",
            help="Use FakeEmbedder for query embedding (no network at query time).",
        ),
    ] = False,
) -> None:
    """Start the MCP stdio server against a built document directory."""
    from cairn.mcp.server import serve_stdio

    asyncio.run(serve_stdio(doc_dir, embedder=_make_embedder(fake)))


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


if __name__ == "__main__":
    app()
