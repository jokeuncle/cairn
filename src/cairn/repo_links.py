"""Explicit document links derived solely from cached Markdown section bodies."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


@dataclass(frozen=True)
class LinkDocument:
    """Internal immutable input; anchors are supplied by the owning index."""

    id: str
    source: str
    state: str
    sections: tuple[tuple[str, str], ...]


def _target_path(source: str, href: str) -> str | None:
    try:
        url = urlsplit(href)
        if url.scheme or url.netloc or not url.path:
            return None
        path = unquote(url.path, errors="strict")
    except (ValueError, UnicodeDecodeError):
        return None
    if "\x00" in path or "\\" in path:
        return None
    path = posixpath.normpath(
        path.lstrip("/")
        if path.startswith("/")
        else posixpath.join(posixpath.dirname(source), path)
    )
    return None if path == ".." or path.startswith("../") else path


def document_reference_graph(
    documents: tuple[LinkDocument, ...],
    *,
    doc: str | None,
    max_references: int,
    include_evidence: bool,
) -> dict[str, Any]:
    """Return deterministic document-pair edges, never heuristic co-mentions.

    Source spans address the original cached section's Unicode characters, not
    a reconstructed document or original-file bytes. URL fragments are opaque.
    """
    known = {item.source: item.id for item in documents}
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    md = MarkdownIt("commonmark")
    for item in documents:
        if posixpath.splitext(item.source)[1].lower() not in {".md", ".markdown", ".mdown", ".mkd"}:
            continue
        env: dict[str, Any] = {}
        # Definitions can occur in a later section. Boundaries prevent adjacent
        # bodies from accidentally becoming one paragraph/list during this pass.
        md.parse("\n\n# cairn-section-boundary\n\n".join(body for _, body in item.sections), env)
        for anchor, body in item.sections:
            offsets = [0]
            for line in body.splitlines(keepends=True):
                offsets.append(offsets[-1] + len(line))
            tokens = md.parse(body, env)
            for number, token in enumerate(tokens):
                if token.type != "inline" or token.map is None:
                    continue
                if number and tokens[number - 1].type == "heading_open":
                    continue
                start, end = (offsets[min(n, len(offsets) - 1)] for n in token.map)
                for child in token.children or ():
                    if child.type != "link_open":
                        continue
                    href = str(child.attrGet("href") or "")
                    target = known.get(_target_path(item.source, href) or "")
                    if target is None or target == item.id:
                        continue
                    if doc is not None and doc not in {item.id, target}:
                        continue
                    key = (item.id, target)
                    if key in pairs:
                        pairs[key]["reference_count"] += 1
                        continue
                    edge: dict[str, Any] = {
                        "source": f"doc:{item.id}",
                        "target": f"doc:{target}",
                        "kind": "document_link",
                        "relation": "link",
                        "source_anchor": anchor,
                        "href": href,
                        "source_span": {"start": start, "end": end, "unit": "section_characters"},
                        "reference_count": 1,
                    }
                    if include_evidence:
                        excerpt_end = min(end, start + 240)
                        edge["evidence"] = body[start:excerpt_end]
                        edge["evidence_span"] = {
                            "start": start,
                            "end": excerpt_end,
                            "unit": "section_characters",
                        }
                        edge["evidence_complete"] = excerpt_end == end
                    pairs[key] = edge
    edges = [pairs[key] for key in sorted(pairs)[:max_references]]
    return {
        "nodes": [
            {
                "id": f"doc:{item.id}",
                "kind": "document",
                "doc": item.id,
                "label": item.id,
                "source": item.source,
                "state": item.state,
            }
            for item in documents
        ],
        "edges": edges,
        "stats": {
            "documents": len(documents),
            "edges": len(edges),
            "total_document_pairs": len(pairs),
            "truncated": len(edges) < len(pairs),
        },
    }
