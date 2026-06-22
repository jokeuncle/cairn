"""MCP stdio server — wraps the 5 retrieval tools.

The dispatch function is exposed separately so unit tests can exercise it
without spawning a stdio transport.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from cairn.core.errors import CairnError, ToolError
from cairn.embed.base import Embedder
from cairn.mcp.schemas import CAIRN_TOOLS, REPO_TOOLS
from cairn.repo import (
    load_repo_document_index,
    repo_context,
    repo_graph,
    repo_impact,
    repo_status,
    search_repo_documents,
)
from cairn.tools.base import DocumentIndex
from cairn.tools.find_mentions import find_mentions as find_mentions_tool
from cairn.tools.get_related import get_related as get_related_tool
from cairn.tools.get_section import expand as expand_tool
from cairn.tools.get_section import get_section as get_section_tool
from cairn.tools.outline import outline as outline_tool
from cairn.tools.read_range import read_range as read_range_tool
from cairn.tools.search_keyword import search_keyword as search_keyword_tool
from cairn.tools.search_semantic import search_semantic as search_semantic_tool

SERVER_NAME = "cairn"


def _new_trace(
    tool: str,
    arguments: dict[str, Any],
    *,
    mode: str,
    repo_root: Path | None = None,
    doc: str | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "server": SERVER_NAME,
        "tool": tool,
        "mode": mode,
        "status": "ok",
        "arguments": dict(arguments),
        "steps": [],
    }
    if repo_root is not None:
        trace["repo_root"] = str(repo_root)
    if doc is not None:
        trace["doc"] = doc
    return trace


def _trace_step(trace: dict[str, Any], name: str, **details: Any) -> None:
    step: dict[str, Any] = {"name": name, "status": details.pop("status", "ok")}
    step.update(details)
    trace["steps"].append(step)


def _success_envelope(
    *,
    data: dict[str, Any],
    tokens_returned: int,
    trace: dict[str, Any],
) -> dict[str, Any]:
    trace["status"] = "ok"
    _trace_step(trace, "return_result", tokens_returned=tokens_returned)
    return {
        "ok": True,
        "tokens_returned": tokens_returned,
        "data": data,
        "trace": trace,
    }


def _error_envelope(
    *,
    error: dict[str, Any],
    trace: dict[str, Any],
) -> dict[str, Any]:
    trace["status"] = "error"
    _trace_step(
        trace,
        "return_error",
        status="error",
        code=error.get("code"),
        message=error.get("message"),
    )
    return {"ok": False, "error": error, "trace": trace}


async def dispatch_tool(
    name: str,
    arguments: dict[str, Any] | None,
    index: DocumentIndex,
    embedder: Embedder,
    *,
    trace: dict[str, Any] | None = None,
    mode: str = "document",
) -> dict[str, Any]:
    """Run a named tool and return the MCP envelope dict.

    Never raises: all CairnError subclasses are caught and converted to the
    ``{"ok": False, "error": {...}}`` shape documented in mcp-tools.md §0.
    """
    args: dict[str, Any] = dict(arguments or {})
    trace = trace or _new_trace(name, args, mode=mode)
    try:
        _trace_step(trace, "select_tool", tool=name)
        if name == "outline":
            resp = await outline_tool(index, **args)
        elif name == "get_section":
            resp = await get_section_tool(index, **args)
        elif name == "expand":
            resp = await expand_tool(index, **args)
        elif name == "search_semantic":
            resp = await search_semantic_tool(index, embedder=embedder, **args)
        elif name == "search_keyword":
            resp = await search_keyword_tool(index, **args)
        elif name == "find_mentions":
            resp = await find_mentions_tool(index, **args)
        elif name == "get_related":
            resp = await get_related_tool(index, **args)
        elif name == "read_range":
            resp = await read_range_tool(index, **args)
        else:
            msg = f"unknown tool: {name!r}"
            _trace_step(trace, "select_tool", status="error", tool=name)
            raise ToolError(msg, details={"name": name})
        _trace_step(
            trace,
            "execute_tool",
            tool=name,
            tokens_returned=resp.tokens_returned,
        )
        return _success_envelope(
            tokens_returned=resp.tokens_returned,
            data=resp.data,
            trace=trace,
        )
    except CairnError as exc:
        return _error_envelope(error=exc.to_envelope(), trace=trace)
    except TypeError as exc:
        # Pydantic / Python TypeError from wrong kwarg names → 400-like error.
        msg = f"invalid arguments for tool {name!r}: {exc}"
        return _error_envelope(
            trace=trace,
            error={
                "code": "INVALID_INPUT",
                "message": msg,
                "details": {"arguments": args},
            },
        )


def build_server(index: DocumentIndex, embedder: Embedder) -> Server:
    """Construct an MCP Server with handlers bound to this index + embedder."""
    server: Server = Server(SERVER_NAME)

    # The MCP SDK's decorator helpers are not fully typed; the ignores keep
    # mypy strict happy without polluting the rest of the file.
    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return CAIRN_TOOLS

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> dict[str, Any]:
        return await dispatch_tool(name, arguments, index, embedder)

    return server


async def dispatch_repo_tool(
    name: str,
    arguments: dict[str, Any] | None,
    repo_root: Path,
    embedder: Embedder,
) -> dict[str, Any]:
    """Run a tool against one document from a repo-scoped Cairn index."""
    args: dict[str, Any] = dict(arguments or {})
    trace = _new_trace(name, args, mode="repo", repo_root=repo_root)
    try:
        _trace_step(trace, "select_tool", tool=name)
        if name == "list_documents":
            state = args.get("state")
            status = repo_status(repo_root)
            docs = [
                doc.model_dump(mode="json")
                for doc in status.documents
                if state is None or doc.state == state
            ]
            data = {
                "root": str(status.root),
                "primary_doc": status.primary_doc,
                "documents": docs,
            }
            _trace_step(
                trace,
                "load_repo_status",
                documents=len(status.documents),
                indexed=status.indexed_count,
                stale=status.stale_count,
                missing=status.missing_count,
                errors=status.error_count,
            )
            _trace_step(trace, "filter_documents", state=state, returned=len(docs))
            return _success_envelope(
                tokens_returned=0,
                data=data,
                trace=trace,
            )
        if name == "search_documents":
            result = await search_repo_documents(repo_root, embedder=embedder, **args)
            data = result["data"]
            _trace_step(
                trace,
                "search_documents",
                query=args.get("query"),
                hits=len(data.get("hits", [])),
                searched_documents=data.get("searched_documents"),
                ranker_mode=data.get("ranker", {}).get("mode"),
                scored_sections=data.get("ranker", {}).get("scored_sections"),
            )
            return _success_envelope(
                tokens_returned=result["tokens_returned"],
                data=data,
                trace=trace,
            )
        if name == "repo_context":
            result = await repo_context(repo_root, embedder=embedder, **args)
            data = result["data"]
            relationship_map = data.get("relationship_map", {})
            _trace_step(
                trace,
                "search_documents",
                query=args.get("query"),
                hits=len(data.get("hits", [])),
            )
            _trace_step(
                trace,
                "load_context_sections",
                sections=len(data.get("context_sections", [])),
                level=args.get("level", "synopsis"),
            )
            _trace_step(
                trace,
                "build_relationship_map",
                nodes=len(relationship_map.get("nodes", [])),
                edges=len(relationship_map.get("edges", [])),
            )
            return _success_envelope(
                tokens_returned=result["tokens_returned"],
                data=data,
                trace=trace,
            )
        if name == "repo_graph":
            result = await repo_graph(repo_root, **args)
            data = result["data"]
            _trace_step(
                trace,
                "build_repo_graph",
                nodes=len(data.get("nodes", [])),
                edges=len(data.get("edges", [])),
                doc=args.get("doc"),
            )
            return _success_envelope(
                tokens_returned=result["tokens_returned"],
                data=data,
                trace=trace,
            )
        if name == "repo_impact":
            result = await repo_impact(repo_root, **args)
            data = result["data"]
            _trace_step(
                trace,
                "estimate_repo_impact",
                scope=data.get("scope"),
                affected_surfaces=len(data.get("affected_surfaces", [])),
                related_sections=len(data.get("related_sections", [])),
            )
            return _success_envelope(
                tokens_returned=result["tokens_returned"],
                data=data,
                trace=trace,
            )

        doc_id = args.pop("doc", None)
        if doc_id is not None and not isinstance(doc_id, str):
            msg = "`doc` must be a string when provided"
            _trace_step(trace, "select_document", status="error", doc=doc_id)
            raise ToolError(msg, details={"doc": doc_id})
        trace["mode"] = "repo_document"
        if doc_id is not None:
            trace["doc"] = doc_id
        index = load_repo_document_index(repo_root, doc_id=doc_id)
        _trace_step(trace, "load_document_index", doc=doc_id)
        return await dispatch_tool(
            name,
            args,
            index,
            embedder,
            trace=trace,
            mode="repo_document",
        )
    except CairnError as exc:
        return _error_envelope(error=exc.to_envelope(), trace=trace)
    except TypeError as exc:
        msg = f"invalid arguments for repo tool {name!r}: {exc}"
        return _error_envelope(
            trace=trace,
            error={
                "code": "INVALID_INPUT",
                "message": msg,
                "details": {"arguments": args},
            },
        )


def build_repo_server(repo_root: Path, embedder: Embedder) -> Server:
    """Construct an MCP Server for a repo-scoped Cairn documentation index."""
    server: Server = Server(SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return REPO_TOOLS

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> dict[str, Any]:
        return await dispatch_repo_tool(name, arguments, repo_root, embedder)

    return server


async def serve_stdio(doc_dir: Path, *, embedder: Embedder) -> None:
    """Load a built index and serve MCP over stdio until the peer disconnects."""
    index = DocumentIndex.load(doc_dir)
    server = build_server(index, embedder)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


async def serve_repo_stdio(repo_root: Path, *, embedder: Embedder) -> None:
    """Serve a repo-scoped Cairn document index over MCP stdio."""
    server = build_repo_server(repo_root, embedder)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )
