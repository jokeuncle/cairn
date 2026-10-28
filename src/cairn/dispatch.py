"""Transport-neutral document/repository tool dispatch shared by CLI and MCP."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from cairn.agent_guidance import agent_usage_guidance
from cairn.core.errors import CairnError, ToolError
from cairn.embed.base import Embedder
from cairn.repo import (
    load_repo_document_index,
    repo_config_guidance,
    repo_context,
    repo_graph,
    repo_impact,
    repo_setup_next_steps,
    repo_status,
    search_repo_documents,
    search_repo_keyword,
)
from cairn.tools.base import DocumentIndex, estimate_tokens_of_payload
from cairn.tools.find_mentions import find_mentions as find_mentions_tool
from cairn.tools.get_related import get_related as get_related_tool
from cairn.tools.get_section import expand as expand_tool
from cairn.tools.get_section import get_section as get_section_tool
from cairn.tools.outline import outline as outline_tool
from cairn.tools.read_range import read_range as read_range_tool
from cairn.tools.search_keyword import search_keyword as search_keyword_tool
from cairn.tools.search_semantic import search_semantic as search_semantic_tool

SERVER_NAME = "cairn"


def _normalize_section_anchors(
    args: dict[str, Any], *, document_id: str | None, trace: dict[str, Any]
) -> str | None:
    """Resolve existing citation URIs without crossing document namespaces."""
    for field in ("id", "start_id", "end_id", "focus", "scope"):
        value = args.get(field)
        if not isinstance(value, str) or not value.startswith("cairn://"):
            continue
        try:
            parsed = urlparse(value)
            doc = unquote(parsed.netloc, errors="strict")
            section = unquote(parsed.path[1:], errors="strict")
        except ValueError as exc:
            raise ToolError("invalid Cairn section anchor", details={"anchor": value}) from exc
        if not doc or not section or section.startswith("/") or parsed.query or parsed.fragment:
            raise ToolError("invalid Cairn section anchor", details={"anchor": value})
        if document_id is not None and document_id != doc:
            raise ToolError(
                "section anchor conflicts with the selected document",
                details={"doc": document_id, "anchor_doc": doc},
            )
        document_id = doc
        args[field] = section
        _trace_step(trace, "resolve_section_anchor", field=field, doc=doc, id=section)
    return document_id


def _compact_search_data(data: dict[str, Any]) -> dict[str, Any]:
    """Keep source evidence and recovery signals; ranking diagnostics are opt-in."""
    fields = {
        "doc",
        "source",
        "id",
        "title",
        "anchor",
        "synopsis",
        "head",
        "evidence",
        "metadata",
        "navigation_only",
    }
    compact: dict[str, Any] = {
        "query": data.get("query"),
        "hits": [
            {key: value for key, value in hit.items() if key in fields}
            for hit in data.get("hits", [])
        ],
        "searched_documents": data.get("searched_documents"),
    }
    for key in ("stale_documents", "skipped_documents", "next_steps", "cursor", "retrieval_mode"):
        if data.get(key):
            compact[key] = data[key]
    if data.get("embedding_mismatch") is not None:
        compact["embedding_mismatch"] = data["embedding_mismatch"]
    return compact


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
    embedder: Embedder | None,
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
        _normalize_section_anchors(args, document_id=index.doc_id, trace=trace)
        if name == "outline":
            resp = await outline_tool(index, **args)
        elif name == "get_section":
            resp = await get_section_tool(index, **args)
        elif name == "expand":
            resp = await expand_tool(index, **args)
        elif name == "search_semantic":
            if embedder is None:
                raise ToolError("semantic search requires an embedding provider")
            _trace_step(
                trace,
                "embed_query",
                embedder=embedder.name,
                dim=embedder.dim,
            )
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


async def dispatch_repo_tool(
    name: str,
    arguments: dict[str, Any] | None,
    repo_root: Path,
    embedder: Embedder | None,
    *,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a tool against one document from a repo-scoped Cairn index."""
    args: dict[str, Any] = dict(arguments or {})
    trace = trace or _new_trace(name, args, mode="repo", repo_root=repo_root)
    trace["repo_root"] = str(repo_root)
    try:
        _trace_step(trace, "select_tool", tool=name)
        anchor_doc = _normalize_section_anchors(args, document_id=args.get("doc"), trace=trace)
        if anchor_doc is not None:
            args["doc"] = anchor_doc
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
                "usage_guidance": agent_usage_guidance(),
            }
            if not any(doc.state in {"indexed", "stale"} for doc in status.documents):
                data["next_steps"] = repo_setup_next_steps()
            guidance = repo_config_guidance(status)
            if guidance is not None:
                data["config_guidance"] = guidance
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
                tokens_returned=estimate_tokens_of_payload(data),
                data=data,
                trace=trace,
            )
        if name == "search_documents":
            include_details = args.pop("include_details", False)
            if not isinstance(include_details, bool):
                raise ToolError("include_details must be a boolean")
            if args.get("retrieval", "hybrid") == "lexical":
                _trace_step(trace, "lexical_query", query=args.get("query"))
            elif embedder is not None:
                _trace_step(trace, "embed_query", embedder=embedder.name, dim=embedder.dim)
            result = await search_repo_documents(repo_root, embedder=embedder, **args)
            data = result["data"]
            _trace_step(
                trace,
                "search_documents",
                query=args.get("query"),
                hits=len(data.get("hits", data.get("context_sections", []))),
                searched_documents=data.get("searched_documents"),
                ranker_mode=data.get("ranker", {}).get("mode"),
                scored_sections=data.get("ranker", {}).get("scored_sections"),
            )
            if not include_details:
                data = _compact_search_data(data)
            return _success_envelope(
                tokens_returned=estimate_tokens_of_payload(data),
                data=data,
                trace=trace,
            )
        if name == "repo_context":
            if args.get("retrieval", "hybrid") == "lexical":
                _trace_step(trace, "lexical_query", query=args.get("query"))
            elif embedder is not None:
                _trace_step(trace, "embed_query", embedder=embedder.name, dim=embedder.dim)
            result = await repo_context(repo_root, embedder=embedder, **args)
            data = result["data"]
            relationship_map = data.get("relationship_map", {})
            _trace_step(
                trace,
                "search_documents",
                query=args.get("query"),
                hits=len(data.get("hits", data.get("context_sections", []))),
            )
            _trace_step(
                trace,
                "load_context_sections",
                sections=len(data.get("context_sections", [])),
                level=args.get("level", "synopsis"),
            )
            if args.get("include_details", False):
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
            if data.get("view") == "references":
                _trace_step(
                    trace, "analyze_document_references",
                    reverse_references=len(data["reverse_references"]),
                    witnesses=len(data["witnesses"]), complete=data["complete"],
                )
            else:
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
        if name == "search_keyword" and args.get("doc") is None:
            args.pop("doc", None)
            result = await search_repo_keyword(repo_root, **args)
            data = result["data"]
            _trace_step(
                trace,
                "search_repo_keyword",
                returned=len(data.get("hits", [])),
                searched_documents=data.get("searched_documents"),
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
