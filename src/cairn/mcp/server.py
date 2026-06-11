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
from cairn.mcp.schemas import CAIRN_TOOLS
from cairn.tools.base import DocumentIndex
from cairn.tools.get_section import expand as expand_tool
from cairn.tools.get_section import get_section as get_section_tool
from cairn.tools.outline import outline as outline_tool
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


async def serve_stdio(doc_dir: Path, *, embedder: Embedder) -> None:
    """Load a built index and serve MCP over stdio until the peer disconnects."""
    index = DocumentIndex.load(doc_dir)
    server = build_server(index, embedder)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )
