"""MCP stdio server — wraps the 5 retrieval tools.

The dispatch function is exposed separately so unit tests can exercise it
without spawning a stdio transport.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from cairn.core.errors import CairnError, ConfigError, ToolError
from cairn.dispatch import (
    SERVER_NAME as SERVER_NAME,
)
from cairn.dispatch import (
    _compact_search_data as _compact_search_data,
)
from cairn.dispatch import (
    _error_envelope as _error_envelope,
)
from cairn.dispatch import (
    _new_trace as _new_trace,
)
from cairn.dispatch import (
    _normalize_section_anchors as _normalize_section_anchors,
)
from cairn.dispatch import (
    _success_envelope as _success_envelope,
)
from cairn.dispatch import (
    _trace_step as _trace_step,
)
from cairn.dispatch import (
    dispatch_repo_tool as dispatch_repo_tool,
)
from cairn.dispatch import (
    dispatch_tool as dispatch_tool,
)
from cairn.embed.base import Embedder
from cairn.mcp.schemas import CAIRN_TOOLS, REPO_TOOLS
from cairn.repo import (
    find_repo_root,
    repo_setup_next_steps,
)
from cairn.tools.base import DocumentIndex

ROOTS_LIST_TIMEOUT = timedelta(seconds=5)


# Server-level guidance injected into the client's system prompt (when the
# client surfaces MCP `instructions`). This is the highest-leverage place to
# shape *when* an agent reaches for Cairn instead of grepping raw text. See
# ADR-0002.
DOCUMENT_INSTRUCTIONS = (
    "Cairn is a structure-aware navigation map for this document. Prefer it "
    "over dumping or grepping raw text. Start with `outline` to see the "
    "structure, then `search_semantic`/`search_keyword` to locate relevant "
    "sections, then `get_section` to read at the right level (gist -> "
    "synopsis -> full). Every result carries stable section ids -- cite them. "
    "Cairn returns summaries by default; request `full` only when you need the "
    "exact text."
)
REPO_INSTRUCTIONS = (
    "Cairn indexes this repository's documentation (specs, design docs, "
    "READMEs) as a navigable map. Before reading raw README, docs, specs, or "
    "architecture files for project knowledge, call Cairn. Prefer Cairn for "
    "documentation, product, architecture, setup, naming, protocol, business "
    "workflow, and durable decision-record questions. Start with `repo_context` "
    "(one call: cited summaries and verbatim evidence) or "
    "`search_documents` (cross-document ranked hits), then drill into a specific "
    "doc with `get_section`/`get_related`. If a repo tool reports setup next "
    "steps, show or run those commands instead of falling back to raw file reads. "
    "For exact API/configuration names, values and conditions, use cited original "
    "evidence rather than summaries. repo_context(level='evidence') combines discovery "
    "and budgeted original blocks with source spans; use max_context_chars to bound "
    "the pack and max_section_chars per section. Omissions are explicit. "
    "For independent requirements provide 2-6 focused queries in the same evidence "
    "call; results are deduplicated and selected jointly. Follow dependent needs later. "
    "Use full section reads for missing conditions or complete oversized examples. "
    "Reuse evidence already supplied instead of fetching it again. "
    "Verify every part of multi-part questions. "
    "Full section bodies exclude descendant bodies. Follow returned navigation "
    "links to children and siblings when a section does not cover every requirement. "
    "For uncovered requirements, use short targeted searches. Do not exhaust navigation lists "
    "or re-read the same section unless new evidence requires it. "
    "Use read_range to fetch adjacent sections together when several bodies "
    "are needed, rather than issuing one read per child. "
    "If a cited section covers only part of a question, inspect its parent or "
    "siblings with get_related or search again. Do not infer that something is "
    "undocumented from an incomplete excerpt or one section. "
    "Each repository is isolated: use the current workspace's `.cairn` index, "
    "or pass `projectPath` only when the user explicitly wants another repo. "
    "Do not use Cairn as a mandatory pre-step for small known-file code edits, "
    "source-code symbol tracing, tests, build logs, or exact literal search; use "
    "code/search/shell tools for those. Results are summaries with stable, "
    "citable section ids by default; request `full` text only when needed."
)


def build_server(index: DocumentIndex, embedder: Embedder) -> Server:
    """Construct an MCP Server with handlers bound to this index + embedder."""
    server: Server = Server(SERVER_NAME, instructions=DOCUMENT_INSTRUCTIONS)

    # The MCP SDK's decorator helpers are not fully typed; the ignores keep
    # mypy strict happy without polluting the rest of the file.
    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return CAIRN_TOOLS

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        return await dispatch_tool(name, arguments, index, embedder)

    return server


def _path_from_uri(uri: object) -> Path | None:
    if not isinstance(uri, str) or not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        return Path(path).resolve()
    if parsed.scheme:
        return None
    return Path(uri).expanduser().resolve()


def _first_workspace_uri(params: Any) -> object | None:
    root_uri: object | None = getattr(params, "rootUri", None)
    if root_uri is not None:
        return root_uri
    extras = getattr(params, "model_extra", None)
    if isinstance(extras, dict) and extras.get("rootUri") is not None:
        extra_root_uri: object = extras["rootUri"]
        return extra_root_uri

    folders = getattr(params, "workspaceFolders", None)
    if folders is None and isinstance(extras, dict):
        folders = extras.get("workspaceFolders")
    if not isinstance(folders, list) or not folders:
        return None
    first = folders[0]
    if isinstance(first, dict):
        folder_uri: object = first.get("uri")
        return folder_uri
    return getattr(first, "uri", None)


class RepoRootResolver:
    """Resolve the repo root for a repo-scoped MCP tool call."""

    def __init__(
        self,
        *,
        fixed_root: Path | None = None,
        server: Server | None = None,
        workspace_hint: Path | None = None,
    ) -> None:
        self.fixed_root = fixed_root
        self.server = server
        self.workspace_hint = workspace_hint

    async def resolve(self, args: dict[str, Any], trace: dict[str, Any]) -> Path:
        project_path = args.pop("projectPath", None)
        if project_path is not None:
            if not isinstance(project_path, str) or not project_path:
                msg = "`projectPath` must be a non-empty string when provided"
                raise ToolError(msg, details={"projectPath": project_path})
            try:
                root = find_repo_root(Path(project_path))
            except ConfigError as exc:
                details = dict(exc.details)
                details["projectPath"] = project_path
                details["source"] = "projectPath"
                details["next_steps"] = repo_setup_next_steps(config_missing=True)
                msg = (
                    "Cairn repo config not found for `projectPath`. "
                    "Run `docsgraph init -y` and `docsgraph sync` in that repo."
                )
                raise ConfigError(msg, details=details) from exc
            _trace_step(trace, "resolve_repo_root", source="projectPath", root=str(root))
            return root

        if self.fixed_root is not None:
            _trace_step(trace, "resolve_repo_root", source="fixed", root=str(self.fixed_root))
            return self.fixed_root

        workspace = self.workspace_hint
        source = "workspace_hint"
        if workspace is None:
            workspace, source = self._workspace_from_initialize()
        if workspace is None:
            workspace, source = await self._workspace_from_roots_list()
        if workspace is None:
            workspace = Path.cwd()
            source = "cwd"

        try:
            root = find_repo_root(workspace)
        except ConfigError as exc:
            details = dict(exc.details)
            details["workspace"] = str(workspace)
            details["source"] = source
            details["next_steps"] = repo_setup_next_steps(config_missing=True)
            msg = (
                "Cairn repo config not found for this MCP workspace. "
                "Run `docsgraph init -y` and `docsgraph sync` in the current "
                "project, or pass `projectPath` to query another initialized repo."
            )
            raise ConfigError(msg, details=details) from exc
        _trace_step(trace, "resolve_repo_root", source=source, root=str(root))
        return root

    def _workspace_from_initialize(self) -> tuple[Path | None, str]:
        if self.server is None:
            return None, "initialize"
        try:
            params = self.server.request_context.session.client_params
        except LookupError:
            return None, "initialize"
        if params is None:
            return None, "initialize"
        path = _path_from_uri(_first_workspace_uri(params))
        return path, "initialize"

    async def _workspace_from_roots_list(self) -> tuple[Path | None, str]:
        if self.server is None:
            return None, "roots/list"
        try:
            context = self.server.request_context
        except LookupError:
            return None, "roots/list"
        params = context.session.client_params
        roots_capability = params.capabilities.roots if params is not None else None
        if roots_capability is None:
            return None, "roots/list"
        try:
            result = await context.session.send_request(
                types.ServerRequest(types.ListRootsRequest()),
                types.ListRootsResult,
                request_read_timeout_seconds=ROOTS_LIST_TIMEOUT,
            )
        except Exception:
            return None, "roots/list"
        if not result.roots:
            return None, "roots/list"
        return _path_from_uri(str(result.roots[0].uri)), "roots/list"


async def dispatch_workspace_repo_tool(
    name: str,
    arguments: dict[str, Any] | None,
    resolver: RepoRootResolver,
    embedder: Embedder,
) -> dict[str, Any]:
    """Resolve the current workspace repo, then run a repo-scoped tool."""
    args: dict[str, Any] = dict(arguments or {})
    trace = _new_trace(name, args, mode="repo")
    try:
        repo_root = await resolver.resolve(args, trace)
        return await dispatch_repo_tool(name, args, repo_root, embedder, trace=trace)
    except CairnError as exc:
        return _error_envelope(error=exc.to_envelope(), trace=trace)


def build_repo_server(repo_root: Path | None, embedder: Embedder) -> Server:
    """Construct an MCP Server for a repo-scoped Cairn documentation index."""
    server: Server = Server(SERVER_NAME, instructions=REPO_INSTRUCTIONS)
    resolver = RepoRootResolver(fixed_root=repo_root, server=server)

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return REPO_TOOLS

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        return await dispatch_workspace_repo_tool(name, arguments, resolver, embedder)

    return server


async def serve_stdio(doc_dir: Path, *, embedder: Embedder) -> None:
    """Load a built index and serve MCP over stdio until the peer disconnects."""
    index = DocumentIndex.load(doc_dir)
    server = build_server(index, embedder)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def serve_repo_stdio(repo_root: Path | None, *, embedder: Embedder) -> None:
    """Serve a repo-scoped Cairn document index over MCP stdio."""
    server = build_repo_server(repo_root, embedder)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
