"""MCP server — the wire layer.

Exposes the v0.1 retrieval tools as Model Context Protocol tools over stdio.
The translation of :class:`cairn.tools.ToolResponse` and
:class:`cairn.core.errors.CairnError` to MCP envelopes lives here so the
tool functions stay transport-agnostic.
"""

from cairn.mcp.schemas import CAIRN_TOOLS
from cairn.mcp.server import dispatch_tool, serve_stdio

__all__ = ["CAIRN_TOOLS", "dispatch_tool", "serve_stdio"]
