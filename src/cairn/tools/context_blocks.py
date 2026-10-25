"""Budgeted, source-exact block selection; no generated summaries or answers."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from markdown_it import MarkdownIt
from pydantic import BaseModel, Field

from cairn.tools.search_semantic import _query_terms


class EvidenceSource(BaseModel):
    doc: str
    source: str
    id: str
    title: str
    path: list[str]
    anchor: str
    body: str
    query_ranks: list[int | None] = Field(default_factory=list)


@dataclass(frozen=True)
class _Block:
    start: int
    end: int
    kind: str


def _blocks(text: str) -> tuple[list[_Block], dict[int, set[int]]]:
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    blocks: list[_Block] = []
    dependencies: dict[int, set[int]] = {}
    for token in MarkdownIt("commonmark").parse(text):
        if token.level != 0 or token.map is None or token.nesting == -1:
            continue
        start, end = token.map
        if blocks and offsets[start] < blocks[-1].end:
            continue
        if token.type == "html_block":
            visible = re.sub(
                r"<!--.*?-->", "", text[offsets[start] : offsets[end]], flags=re.DOTALL
            )
            if not re.sub(r"<[^>]+>", "", visible).strip():
                continue
        content = token.content
        if (
            token.type == "fence"
            and token.info.strip().lower() in {"text", "console", "plaintext"}
            and re.search(r"^[Uu]sage:", content, re.MULTILINE)
        ):
            stop = end - 1 if lines[end - 1].strip().startswith(token.markup) else end
            boundaries = [
                i
                for i in range(start + 1, stop)
                if re.match(r"^\s{0,8}(?:--[\w-]+|-\w(?:,\s+--[\w-]+)?)", lines[i])
                or (
                    re.match(r"^\S.*:\s*$", lines[i])
                    and not lines[i].startswith(("Usage:", "usage:"))
                )
            ]
            if len(boundaries) >= 3 and any(lines[i].strip() == "Options:" for i in boundaries):
                usage = len(blocks)
                first = boundaries[0]
                blocks.append(_Block(offsets[start + 1], offsets[first], "cli_usage"))
                group: int | None = None
                for a, b in zip(boundaries, [*boundaries[1:], stop], strict=True):
                    is_group = bool(re.match(r"^\S.*:\s*$", lines[a]))
                    index = len(blocks)
                    blocks.append(
                        _Block(offsets[a], offsets[b], "cli_group" if is_group else "cli_option")
                    )
                    if is_group:
                        group = index
                        dependencies[index] = {usage}
                    else:
                        dependencies[index] = {usage} | ({group} if group is not None else set())
                continue
        blocks.append(_Block(offsets[start], offsets[end], token.type.removesuffix("_open")))
    return blocks, dependencies


def _facet_relevance(text: str, terms: list[str], rank: int | None) -> float:
    if rank is None:
        return 0.0
    lowered = text.lower()
    return sum(term in lowered for term in terms) / max(1, len(terms)) / (rank + 1)


def pack_evidence(
    sources: list[EvidenceSource],
    *,
    query: str,
    max_chars: int,
    max_section_chars: int,
    max_sections: int | None = None,
    sections_per_doc: int | None = None,
    queries: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Choose complementary whole blocks with explicit source spans and limits.

    Adjacent paragraph context is an extraction heuristic, not a guarantee that
    every prerequisite or exception has been included. No task oracle is used.
    """
    terms = _query_terms(query)
    focused_terms = [_query_terms(focus) for focus in queries or []]
    qualities: dict[tuple[int, frozenset[int]], list[float]] = {}
    units: list[list[_Block]] = []
    candidates: list[tuple[int, set[int], set[str]]] = []
    for section, source in enumerate(sources):
        dependencies: dict[int, set[int]]
        if len(source.body) <= max_section_chars:
            blocks, dependencies = [_Block(0, len(source.body), "section_body")], {}
        else:
            blocks, dependencies = _blocks(source.body)
        units.append(blocks)
        first_candidate = len(candidates)
        for index, block in enumerate(blocks):
            if (
                block.kind == "cli_group"
                and len(
                    [
                        line
                        for line in source.body[block.start : block.end].splitlines()
                        if line.strip()
                    ]
                )
                <= 1
            ):
                continue
            package = {index} | dependencies.get(index, set())
            if block.kind not in {"section_body", "cli_option", "cli_group", "cli_usage"}:
                for neighbor in (index - 1, index + 1):
                    if 0 <= neighbor < len(blocks) and blocks[neighbor].kind == "paragraph":
                        package.add(neighbor)
            text = "\n".join(source.body[blocks[i].start : blocks[i].end] for i in sorted(package))
            if text.strip():
                candidates.append(
                    (section, package, {term for term in terms if term in text.lower()})
                )
                if focused_terms:
                    qualities[section, frozenset(package)] = [
                        _facet_relevance(
                            text,
                            focus,
                            source.query_ranks[i] if i < len(source.query_ranks) else None,
                        )
                        for i, focus in enumerate(focused_terms)
                    ]
        local = candidates[first_candidate:]
        if not focused_terms and local and not any(matched for _, _, matched in local):
            # Without lexical support, retain source order rather than choosing
            # an arbitrary short paragraph and calling it relevant.
            candidates[first_candidate:] = next(
                (
                    [candidate]
                    for candidate in local
                    if sum(blocks[i].end - blocks[i].start for i in candidate[1])
                    <= min(max_chars, max_section_chars)
                ),
                [],
            )

    frequency = Counter(term for _, _, matched in candidates for term in matched)
    weights = {term: math.log1p(len(candidates) / count) for term, count in frequency.items()}
    chosen: dict[int, set[int]] = {}
    document_counts: Counter[str] = Counter()
    used: Counter[int] = Counter()
    covered: set[str] = set()
    covered_facets = [0.0] * len(focused_terms)
    total = 0
    while candidates:
        best: tuple[int, int, set[int], set[str], int] | None = None
        best_score = -1.0
        for position, (section, package, matched) in enumerate(candidates):
            if section not in chosen:
                if max_sections is not None and len(chosen) >= max_sections:
                    continue
                if (
                    sections_per_doc is not None
                    and document_counts[sources[section].doc] >= sections_per_doc
                ):
                    continue
            added = package - chosen.get(section, set())
            blocks = units[section]
            cost = sum(blocks[i].end - blocks[i].start for i in added)
            if not cost or total + cost > max_chars or used[section] + cost > max_section_chars:
                continue
            if len(chosen.get(section, set()) | added) > 8:
                continue
            if focused_terms:
                quality = qualities[section, frozenset(package)]
                gain = sum(max(0.0, value - covered_facets[i]) for i, value in enumerate(quality))
            else:
                gain = sum(weights[t] for t in sorted(matched - covered))
            if not focused_terms and section not in chosen:
                gain += (len(sources) - section) / max(1, len(sources))
            if gain <= 0:
                continue
            # Include span/key overhead rather than pretending source characters
            # are the entire response cost. This is not a model-token estimate.
            serialized = sum(
                len(
                    json.dumps(
                        {
                            "text": sources[section].body[blocks[i].start : blocks[i].end],
                            "span": {"start": blocks[i].start, "end": blocks[i].end},
                            "kind": blocks[i].kind,
                        },
                        ensure_ascii=False,
                    )
                )
                for i in added
            )
            if section not in chosen:
                serialized += len(
                    json.dumps(sources[section].model_dump(exclude={"body", "query_ranks"}))
                )
            score = gain / max(1, serialized)
            if score > best_score:
                best_score = score
                best = position, section, added, matched, cost
        if best is None:
            break
        position, section, added, matched, cost = best
        if section not in chosen:
            document_counts[sources[section].doc] += 1
        chosen.setdefault(section, set()).update(added)
        used[section] += cost
        total += cost
        covered.update(matched)
        if focused_terms:
            package = candidates[position][1]
            quality = qualities[section, frozenset(package)]
            covered_facets = [max(a, b) for a, b in zip(covered_facets, quality, strict=True)]
        candidates.pop(position)

    result: list[dict[str, Any]] = []
    for section in sorted(chosen):
        source = sources[section]
        blocks = units[section]
        selected = [blocks[i] for i in sorted(chosen[section])]
        result.append(
            {
                **source.model_dump(exclude={"body", "query_ranks"}),
                "level": "evidence",
                "content_scope": "selected_blocks_of_section_body",
                "source_characters": len(source.body),
                "returned_source_characters": used[section],
                "omitted_content": used[section] < len(source.body),
                "evidence_blocks": [
                    {
                        "text": source.body[b.start : b.end],
                        "kind": b.kind,
                        "span": {"start": b.start, "end": b.end, "unit": "section_characters"},
                    }
                    for b in selected
                ],
            }
        )
    return result
