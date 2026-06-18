"""``search_semantic`` retrieval tool.

Spec: ``docs/specs/mcp-tools.md`` §4.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Literal

from cairn.core.errors import ToolError
from cairn.embed.base import Embedder
from cairn.tools.base import DocumentIndex, ToolResponse, estimate_tokens_of_payload

IncludeField = Literal["synopsis", "head", "evidence"]

_HEAD_CHARS: int = 200
_EVIDENCE_CHARS: int = 360
_MAX_EVIDENCE_TERMS: int = 40
_VALID_INCLUDE: frozenset[str] = frozenset({"synopsis", "head", "evidence"})


async def search_semantic(
    index: DocumentIndex,
    *,
    embedder: Embedder,
    query: str,
    scope: str | None = None,
    k: int = 8,
    include: Sequence[IncludeField] = ("synopsis", "head", "evidence"),
) -> ToolResponse:
    """Dense vector search across the document.

    The MCP server passes an :class:`Embedder` instance; tools receive it as
    a typed dependency so they can be unit-tested with a fake.
    """
    if k < 1 or k > 32:
        msg = f"k must be in [1, 32]; got {k}"
        raise ToolError(msg, details={"k": k})
    if not query.strip():
        msg = "query must not be empty"
        raise ToolError(msg)
    bad = [x for x in include if x not in _VALID_INCLUDE]
    if bad:
        msg = f"invalid include values: {bad}"
        raise ToolError(msg, details={"invalid": bad})

    vectors = await embedder.embed([query])
    if not vectors:
        msg = "embedder returned no vector for query"
        raise ToolError(msg)
    query_vec = vectors[0]
    if len(query_vec) != index.vectors.dim:
        msg = (
            f"query embedding dim {len(query_vec)} != "
            f"index dim {index.vectors.dim}"
        )
        raise ToolError(msg)

    hits = await index.vectors.search(query_vec, k=k, scope_prefix=scope)

    include_set = set(include)
    results: list[dict[str, Any]] = []
    for hit in hits:
        node = index.tree.get(hit.id)
        if node is None:
            # Stale vector index entry: skip rather than fail the whole call.
            continue
        summary = index.summaries.get(hit.id)
        result: dict[str, Any] = {
            "id": hit.id,
            "title": node.title,
            "score": hit.score,
            "anchor": index.anchor(hit.id),
        }
        if "synopsis" in include_set and summary is not None and summary.synopsis:
            result["synopsis"] = summary.synopsis
        if "head" in include_set:
            result["head"] = node.raw_text[:_HEAD_CHARS]
        if "evidence" in include_set:
            result["evidence"] = _evidence_snippet(node.raw_text, query)
        results.append(result)

    payload: dict[str, Any] = {
        "query": query,
        "scope": scope,
        "hits": results,
        "cursor": None,
    }
    return ToolResponse(
        data=payload,
        tokens_returned=estimate_tokens_of_payload(payload),
    )


def _evidence_snippet(text: str, query: str) -> dict[str, Any]:
    """Return the strongest lexical evidence window for a semantic hit.

    Semantic rank is vector-based, but a short lexical window gives humans and
    agents a cheap explanation of what in the section may have caused the hit.
    When there is no term overlap, fall back to the start of the section.
    """
    clean_text = text.strip()
    if not clean_text:
        return {"text": "", "matched_terms": [], "span": {"start": 0, "end": 0}}

    terms = _query_terms(query)
    best_start = 0
    best_score = 0
    lowered = clean_text.lower()
    if terms:
        candidate_starts: set[int] = {0}
        for term in terms:
            for match in re.finditer(re.escape(term), lowered):
                candidate_starts.add(max(0, match.start() - _EVIDENCE_CHARS // 3))
        for start in candidate_starts:
            end = min(len(clean_text), start + _EVIDENCE_CHARS)
            window = lowered[start:end]
            score = sum(window.count(term) for term in terms)
            if score > best_score:
                best_score = score
                best_start = start

    start = best_start
    end = min(len(clean_text), start + _EVIDENCE_CHARS)
    snippet = clean_text[start:end]
    if start > 0:
        snippet = "..." + snippet.lstrip()
    if end < len(clean_text):
        snippet = snippet.rstrip() + "..."

    matched = [term for term in terms if term in lowered[start:end]]
    return {
        "text": snippet,
        "matched_terms": matched,
        "span": {"start": start, "end": end},
    }


def _query_terms(query: str) -> list[str]:
    query = query.lower()
    stop = {
        "a",
        "an",
        "and",
        "are",
        "for",
        "how",
        "is",
        "of",
        "or",
        "the",
        "to",
        "what",
        "where",
    }
    seen: set[str] = set()
    out: list[str] = []

    def add(term: str) -> None:
        if term in seen or len(out) >= _MAX_EVIDENCE_TERMS:
            return
        seen.add(term)
        out.append(term)

    words = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_-]*", query)
    for word in words:
        if len(word) < 3 or word in stop or word in seen:
            continue
        add(word)

    for seq in re.findall(r"[\u3400-\u9fff]+", query):
        if len(seq) >= 2:
            add(seq)
        # CJK queries often have no whitespace; bounded n-grams give the
        # evidence window useful overlap without changing vector ranking.
        for size in range(min(6, len(seq)), 1, -1):
            for start in range(0, len(seq) - size + 1):
                add(seq[start : start + size])
    return out
