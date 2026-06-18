"""MCP stdio server — wraps the 5 retrieval tools.

The dispatch function is exposed separately so unit tests can exercise it
without spawning a stdio transport.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from cairn.core.errors import CairnError, ToolError
from cairn.embed.base import Embedder
from cairn.mcp.schemas import CAIRN_TOOLS, REPO_TOOLS
from cairn.repo import load_repo_document_index, repo_status, search_repo_documents
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


async def dispatch_tool(
    name: str,
    arguments: dict[str, Any] | None,
    index: DocumentIndex,
    embedder: Embedder,
) -> dict[str, Any]:
    """Run a named tool and return the MCP envelope dict.

    Never raises: all CairnError subclasses are caught and converted to the
    ``{"ok": False, "error": {...}}`` shape documented in mcp-tools.md §0.
    """
    args: dict[str, Any] = dict(arguments or {})
    try:
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
            raise ToolError(msg, details={"name": name})
        return {
            "ok": True,
            "tokens_returned": resp.tokens_returned,
            "data": resp.data,
        }
    except CairnError as exc:
        return {"ok": False, "error": exc.to_envelope()}
    except TypeError as exc:
        # Pydantic / Python TypeError from wrong kwarg names → 400-like error.
        msg = f"invalid arguments for tool {name!r}: {exc}"
        return {
            "ok": False,
            "error": {
                "code": "INVALID_INPUT",
                "message": msg,
                "details": {"arguments": args},
            },
        }


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
    ) -> list[TextContent]:
        envelope = await dispatch_tool(name, arguments, index, embedder)
        text = json.dumps(envelope, ensure_ascii=False)
        return [TextContent(type="text", text=text)]

    return server


async def dispatch_repo_tool(
    name: str,
    arguments: dict[str, Any] | None,
    repo_root: Path,
    embedder: Embedder,
) -> dict[str, Any]:
    """Run a tool against one document from a repo-scoped Cairn index."""
    args: dict[str, Any] = dict(arguments or {})
    try:
        if name == "list_documents":
            state = args.get("state")
            status = repo_status(repo_root)
            docs = [
                doc.model_dump(mode="json")
                for doc in status.documents
                if state is None or doc.state == state
            ]
            return {
                "ok": True,
                "tokens_returned": 0,
                "data": {
                    "root": str(status.root),
                    "primary_doc": status.primary_doc,
                    "documents": docs,
                },
            }
        if name == "search_documents":
            result = await search_repo_documents(repo_root, embedder=embedder, **args)
            return {
                "ok": True,
                "tokens_returned": result["tokens_returned"],
                "data": result["data"],
            }

        doc_id = args.pop("doc", None)
        if doc_id is not None and not isinstance(doc_id, str):
            msg = "`doc` must be a string when provided"
            raise ToolError(msg, details={"doc": doc_id})
        index = load_repo_document_index(repo_root, doc_id=doc_id)
        return await dispatch_tool(name, args, index, embedder)
    except CairnError as exc:
        return {"ok": False, "error": exc.to_envelope()}


def build_repo_server(repo_root: Path, embedder: Embedder) -> Server:
    """Construct an MCP Server for a repo-scoped Cairn documentation index."""
    server: Server = Server(SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return REPO_TOOLS

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[TextContent]:
        envelope = await dispatch_repo_tool(name, arguments, repo_root, embedder)
        text = json.dumps(envelope, ensure_ascii=False)
        return [TextContent(type="text", text=text)]

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
