"""Repo-scoped search cache, evidence blending, and ranking.

The public repo lifecycle API stays in :mod:`cairn.repo`. This module owns the
large, performance-sensitive search implementation so repository status/sync
logic does not have to carry ranking internals.
"""

from __future__ import annotations

import asyncio
import heapq
import math
import re
from collections import Counter, defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np

from cairn.index.vectors import l2_normalize
from cairn.tools.base import DocumentIndex
from cairn.tools.search_semantic import IncludeField, _evidence_snippet, _query_terms

_REPO_SEARCH_CACHE_MAX: Final = 4
_REPO_SEARCH_LOAD_CONCURRENCY: Final = 16
_REPO_SEARCH_FULL_SCORE_LIMIT: Final = 2048
_REPO_SEARCH_SHORTLIST_MIN: Final = 768
_REPO_SEARCH_SHORTLIST_PER_RESULT: Final = 96
_REPO_SEARCH_SHORTLIST_PER_DOC_RESULT: Final = 64
_REPO_SEARCH_GRAPH_EXPANSION_LIMIT: Final = 256


class RepoSearchCandidate(Protocol):
    """Status fields needed by repo search without importing ``cairn.repo``."""

    @property
    def id(self) -> str: ...

    @property
    def source(self) -> str: ...

    @property
    def doc_dir(self) -> str: ...

    @property
    def state(self) -> str: ...

    @property
    def indexed_hash(self) -> str | None: ...

    @property
    def source_file_hash(self) -> str | None: ...

    @property
    def indexed_source_file_hash(self) -> str | None: ...

    @property
    def section_count(self) -> int | None: ...


@dataclass(slots=True)
class _RepoSectionRecord:
    doc_id: str
    source: str
    index: DocumentIndex
    section_id: str
    title: str
    body: str
    synopsis: str
    vector: tuple[float, ...]
    haystacks: tuple[str, str, str, str, str]
    token_counts: dict[str, int]
    token_count: int


@dataclass(slots=True)
class _RepoLexicalQuery:
    terms: tuple[str, ...]
    variants: dict[str, tuple[str, ...]]
    weights: dict[str, float]
    phrases: tuple[str, ...]
    max_score: float
    preferred_locales: tuple[str, ...]


@dataclass(slots=True)
class _RepoScoredHit:
    record: _RepoSectionRecord
    score: float
    vector_score: float
    lexical_score: float
    sparse_score: float
    graph_score: float
    base_score: float
    rank_factor: float
    identity_bonus: float


@dataclass(slots=True)
class _RepoSearchCache:
    signature: tuple[tuple[str, str, str, str, str, str, int], ...]
    records: tuple[_RepoSectionRecord, ...]
    skipped: tuple[dict[str, str], ...]
    doc_dims: dict[str, int]
    df: dict[str, int]
    avg_token_count: float
    graph_neighbors: dict[tuple[str, str], tuple[tuple[tuple[str, str], float], ...]]
    record_index_by_key: dict[tuple[str, str], int]
    vector_matrices: dict[int, Any]
    vector_record_indices: dict[int, tuple[int, ...]]


@dataclass(slots=True)
class _RepoSearchDocumentChunk:
    doc_id: str | None
    dim: int | None
    records: list[_RepoSectionRecord]
    skipped: dict[str, str] | None
    df: Counter[str]
    graph_edges: list[tuple[tuple[str, str], tuple[str, str], float]]
    entity_sections: dict[str, set[tuple[str, str]]]


@dataclass(frozen=True, slots=True)
class _RepoRankProfile:
    field_weights: tuple[float, float, float, float, float] = (2.5, 2.0, 3.0, 1.0, 1.0)
    vector_weight: float = 0.22
    lexical_weight: float = 0.50
    sparse_weight: float = 0.28
    graph_weight: float = 0.10
    no_lexical_vector_weight: float = 0.25
    sparse_floor_gate: float = 0.25
    sparse_lexical_gate_multiplier: float = 2.0
    overview_doc_bonus: float = 0.16
    overview_title_bonus: float = 0.12
    overview_shallow_bonus: float = 0.04
    overview_max_bonus: float = 0.22
    focus_support_floor: float = 0.30
    focus_support_weight: float = 0.70
    focus_synopsis_support: float = 0.65
    focus_body_support: float = 0.45
    root_meta_doc_factor: float = 0.55
    coverage_floor: float = 0.45
    coverage_weight: float = 0.55
    doc_identity_bonus_weight: float = 0.25
    history_doc_generic_factor: float = 0.45
    locale_match_factor: float = 1.04
    locale_mismatch_factor: float = 0.72


_REPO_SEARCH_CACHES: dict[Path, _RepoSearchCache] = {}
_DEFAULT_RANK_PROFILE = _RepoRankProfile()
_HISTORY_DOC_TERMS: Final = frozenset(
    {
        "changelog",
        "changes",
        "history",
        "release",
        "releases",
        "migration",
        "migrations",
    }
)
_HISTORY_QUERY_TERMS: Final = frozenset(
    {
        "breaking",
        "change",
        "changes",
        "changelog",
        "deprecated",
        "deprecation",
        "history",
        "migration",
        "migrations",
        "release",
        "released",
        "releases",
        "upgrade",
        "version",
        "versions",
    }
)
_KNOWN_LOCALES: Final = frozenset(
    {
        "ar",
        "de",
        "en",
        "es",
        "fa",
        "fr",
        "hi",
        "id",
        "it",
        "ja",
        "ko",
        "nl",
        "pl",
        "pt",
        "ru",
        "tr",
        "uk",
        "vi",
        "zh",
    }
)


async def search_repo_index(
    root: Path,
    *,
    candidates: Collection[RepoSearchCandidate],
    query: str,
    query_vec: list[float],
    k: int,
    include_set: Collection[IncludeField],
    sections_per_doc: int,
    preferred_locales: tuple[str, ...],
) -> dict[str, Any]:
    """Return the repo-search payload for already validated inputs."""
    cache = await _get_repo_search_cache(root, candidates)
    lexical_query = _build_repo_lexical_query(
        query,
        cache=cache,
        preferred_locales=preferred_locales,
    )
    hits_by_key: dict[tuple[str, str], _RepoScoredHit] = {}
    skipped: list[dict[str, str]] = list(cache.skipped)
    query_dim = len(query_vec)
    incompatible_docs = {
        doc_id for doc_id, dim in cache.doc_dims.items() if dim != query_dim
    }
    for doc_id in sorted(incompatible_docs):
        skipped.append(
            {
                "doc": doc_id,
                "reason": f"query embedding dim {query_dim} != index dim {cache.doc_dims[doc_id]}",
            }
        )
    normalized_query = l2_normalize(query_vec)
    vector_scores = _repo_vector_scores(cache, normalized_query, query_dim)
    candidate_indices, ranker_mode, compatible_count = _repo_candidate_indices(
        cache,
        query=lexical_query,
        vector_scores=vector_scores,
        incompatible_docs=incompatible_docs,
        k=k,
        sections_per_doc=sections_per_doc,
    )
    for index in candidate_indices:
        record = cache.records[index]
        scored = _score_repo_record(
            record,
            query=lexical_query,
            cache=cache,
            vector_score=vector_scores[index],
        )
        hits_by_key[(record.doc_id, record.section_id)] = scored

    hits = list(hits_by_key.values())
    _apply_graph_scores(hits, cache)
    hits.sort(key=lambda item: item.score, reverse=True)
    selected_records = _diversify_repo_hits(
        hits,
        limit=k,
        sections_per_doc=sections_per_doc,
    )
    selected = [
        _repo_scored_payload(
            hit,
            query=query,
            lexical_query=lexical_query,
            include_set=include_set,
        )
        for hit in selected_records
    ]
    return {
        "query": query,
        "hits": selected,
        "sections_per_doc": sections_per_doc,
        "searched_documents": len(candidates),
        "ranker": {
            "mode": ranker_mode,
            "total_sections": len(cache.records),
            "compatible_sections": compatible_count,
            "scored_sections": len(candidate_indices),
        },
        "stale_documents": [
            doc.id for doc in candidates if doc.state == "stale"
        ],
        "skipped_documents": skipped,
        "cursor": None,
    }


async def _get_repo_search_cache(
    root: Path,
    candidates: Collection[RepoSearchCandidate],
) -> _RepoSearchCache:
    resolved_root = root.resolve()
    signature = _repo_search_signature(candidates)
    cached = _REPO_SEARCH_CACHES.get(resolved_root)
    if cached is not None and cached.signature == signature:
        return cached

    records: list[_RepoSectionRecord] = []
    skipped: list[dict[str, str]] = []
    doc_dims: dict[str, int] = {}
    df_counter: Counter[str] = Counter()
    graph_weights: dict[tuple[str, str], dict[tuple[str, str], float]] = defaultdict(dict)
    entity_sections: dict[str, set[tuple[str, str]]] = defaultdict(set)
    semaphore = asyncio.Semaphore(_REPO_SEARCH_LOAD_CONCURRENCY)

    async def load(doc: RepoSearchCandidate) -> _RepoSearchDocumentChunk:
        async with semaphore:
            return await _load_repo_search_document(root, doc)

    chunks = await asyncio.gather(*(load(doc) for doc in candidates))
    for chunk in chunks:
        if chunk.skipped is not None:
            skipped.append(chunk.skipped)
            continue
        if chunk.doc_id is not None and chunk.dim is not None:
            doc_dims[chunk.doc_id] = chunk.dim
        records.extend(chunk.records)
        df_counter.update(chunk.df)
        for left, right, weight in chunk.graph_edges:
            _add_graph_edge(graph_weights, left, right, weight=weight)
        for key, section_keys in chunk.entity_sections.items():
            entity_sections[key].update(section_keys)

    for section_keys in entity_sections.values():
        if len(section_keys) < 2 or len(section_keys) > 24:
            continue
        ordered = sorted(section_keys)
        for i, src in enumerate(ordered):
            for dst in ordered[i + 1 :]:
                _add_graph_edge(graph_weights, src, dst, weight=0.18)

    vector_matrices, vector_record_indices = _repo_vector_matrices(records)
    cache = _RepoSearchCache(
        signature=signature,
        records=tuple(records),
        skipped=tuple(skipped),
        doc_dims=doc_dims,
        df=dict(df_counter),
        avg_token_count=(
            sum(record.token_count for record in records) / len(records)
            if records
            else 0.0
        ),
        graph_neighbors={
            key: tuple(neighbors.items())
            for key, neighbors in graph_weights.items()
        },
        record_index_by_key={
            (record.doc_id, record.section_id): index
            for index, record in enumerate(records)
        },
        vector_matrices=vector_matrices,
        vector_record_indices=vector_record_indices,
    )
    if (
        resolved_root not in _REPO_SEARCH_CACHES
        and len(_REPO_SEARCH_CACHES) >= _REPO_SEARCH_CACHE_MAX
    ):
        oldest = next(iter(_REPO_SEARCH_CACHES))
        del _REPO_SEARCH_CACHES[oldest]
    _REPO_SEARCH_CACHES[resolved_root] = cache
    return cache


async def _load_repo_search_document(
    root: Path,
    doc: RepoSearchCandidate,
) -> _RepoSearchDocumentChunk:
    records: list[_RepoSectionRecord] = []
    df_counter: Counter[str] = Counter()
    graph_edges: list[tuple[tuple[str, str], tuple[str, str], float]] = []
    entity_sections: dict[str, set[tuple[str, str]]] = defaultdict(set)
    try:
        index = DocumentIndex.load(root / doc.doc_dir)
        vectors = {
            entry.id: tuple(entry.vector)
            for entry in await index.vectors.entries()
        }
    except Exception as exc:
        return _RepoSearchDocumentChunk(
            doc_id=None,
            dim=None,
            records=[],
            skipped={"doc": doc.id, "reason": str(exc)},
            df=Counter(),
            graph_edges=[],
            entity_sections={},
        )

    vector_section_ids = set(vectors)
    for node in index.tree:
        vector = vectors.get(node.id)
        if vector is None:
            continue
        summary = index.summaries.get(node.id)
        synopsis = summary.synopsis if summary is not None else ""
        token_counts = _section_token_counts(
            doc_id=doc.id,
            source=doc.source,
            title=node.title,
            synopsis=synopsis,
            body=node.raw_text,
        )
        df_counter.update(token_counts.keys())
        records.append(
            _RepoSectionRecord(
                doc_id=doc.id,
                source=doc.source,
                index=index,
                section_id=node.id,
                title=node.title,
                body=node.raw_text,
                synopsis=synopsis,
                vector=vector,
                haystacks=(
                    _normalize_field_text(doc.id),
                    _normalize_field_text(doc.source),
                    _normalize_field_text(node.title),
                    _normalize_field_text(synopsis),
                    _normalize_field_text(node.raw_text[:2000]),
                ),
                token_counts=dict(token_counts),
                token_count=sum(token_counts.values()),
            )
        )

    for node in index.tree:
        if (
            node.parent is not None
            and node.id in vector_section_ids
            and node.parent in vector_section_ids
        ):
            graph_edges.append(((doc.id, node.id), (doc.id, node.parent), 0.55))
    if index.xrefs is not None:
        for ref in index.xrefs:
            if ref.src in vector_section_ids and ref.dst in vector_section_ids:
                graph_edges.append(
                    (
                        (doc.id, ref.src),
                        (doc.id, ref.dst),
                        max(0.2, min(1.0, ref.confidence)),
                    )
                )
    if index.entities is not None:
        for entity in index.entities:
            key = f"{entity.kind}:{entity.canonical}".lower()
            for mention in entity.mentions:
                if mention.section_id in vector_section_ids:
                    entity_sections[key].add((doc.id, mention.section_id))

    return _RepoSearchDocumentChunk(
        doc_id=doc.id,
        dim=index.vectors.dim,
        records=records,
        skipped=None,
        df=df_counter,
        graph_edges=graph_edges,
        entity_sections=dict(entity_sections),
    )


def _repo_search_signature(
    candidates: Collection[RepoSearchCandidate],
) -> tuple[tuple[str, str, str, str, str, str, int], ...]:
    return tuple(
        (
            doc.id,
            doc.doc_dir,
            doc.state,
            doc.indexed_hash or "",
            doc.source_file_hash or "",
            doc.indexed_source_file_hash or "",
            doc.section_count or 0,
        )
        for doc in candidates
    )


def _repo_vector_matrices(
    records: list[_RepoSectionRecord],
) -> tuple[dict[int, Any], dict[int, tuple[int, ...]]]:
    by_dim: dict[int, list[tuple[int, tuple[float, ...]]]] = defaultdict(list)
    for index, record in enumerate(records):
        by_dim[len(record.vector)].append((index, record.vector))
    matrices: dict[int, Any] = {}
    indices: dict[int, tuple[int, ...]] = {}
    for dim, rows in by_dim.items():
        indices[dim] = tuple(index for index, _ in rows)
        matrices[dim] = np.asarray([vector for _, vector in rows], dtype=np.float32)
    return matrices, indices


def _repo_vector_scores(
    cache: _RepoSearchCache,
    query: list[float],
    query_dim: int,
) -> list[float]:
    scores = [0.0] * len(cache.records)
    matrix = cache.vector_matrices.get(query_dim)
    indices = cache.vector_record_indices.get(query_dim)
    if matrix is None or indices is None:
        return scores
    query_array = np.asarray(query, dtype=np.float32)
    raw_scores = matrix @ query_array
    clipped = np.clip(raw_scores, 0.0, 1.0)
    for record_index, score in zip(indices, clipped.tolist(), strict=True):
        scores[record_index] = float(score)
    return scores


def _repo_candidate_indices(
    cache: _RepoSearchCache,
    *,
    query: _RepoLexicalQuery,
    vector_scores: list[float],
    incompatible_docs: set[str],
    k: int,
    sections_per_doc: int,
) -> tuple[tuple[int, ...], str, int]:
    """Choose records that should receive the full ranker pass."""
    compatible = tuple(
        index
        for index, record in enumerate(cache.records)
        if record.doc_id not in incompatible_docs
    )
    compatible_count = len(compatible)
    if compatible_count <= _REPO_SEARCH_FULL_SCORE_LIMIT:
        return compatible, "full", compatible_count

    target = max(
        _REPO_SEARCH_SHORTLIST_MIN,
        k * _REPO_SEARCH_SHORTLIST_PER_RESULT,
        k * sections_per_doc * _REPO_SEARCH_SHORTLIST_PER_DOC_RESULT,
    )
    target = min(target, compatible_count)
    if target >= compatible_count:
        return compatible, "full", compatible_count

    candidate_set: set[int] = set()
    vector_budget = min(target, max(k * 32, target // 2))
    candidate_set.update(
        heapq.nlargest(
            vector_budget,
            compatible,
            key=lambda index: vector_scores[index],
        )
    )
    if query.terms or query.phrases:
        candidate_set.update(
            heapq.nlargest(
                target,
                compatible,
                key=lambda index: _repo_quick_recall_score(
                    query,
                    cache.records[index],
                ),
            )
        )
    if len(candidate_set) < target:
        candidate_set.update(
            heapq.nlargest(
                target,
                compatible,
                key=lambda index: vector_scores[index],
            )
        )

    _expand_repo_candidate_neighbors(
        candidate_set,
        cache,
        limit=min(
            compatible_count,
            target + _REPO_SEARCH_GRAPH_EXPANSION_LIMIT,
        ),
    )
    return tuple(sorted(candidate_set)), "shortlist", compatible_count


def _expand_repo_candidate_neighbors(
    candidate_set: set[int],
    cache: _RepoSearchCache,
    *,
    limit: int,
) -> None:
    for index in tuple(candidate_set):
        record = cache.records[index]
        key = (record.doc_id, record.section_id)
        for neighbor_key, _ in cache.graph_neighbors.get(key, ()):
            neighbor_index = cache.record_index_by_key.get(neighbor_key)
            if neighbor_index is None:
                continue
            candidate_set.add(neighbor_index)
            if len(candidate_set) >= limit:
                return


def _repo_quick_recall_score(
    query: _RepoLexicalQuery,
    record: _RepoSectionRecord,
) -> float:
    if not query.terms and not query.phrases:
        return 0.0
    doc_id, source, title, synopsis, body = record.haystacks
    score = 0.0
    for term in query.terms:
        weight = query.weights.get(term, 0.0)
        variants = query.variants.get(term, ())
        token_variants = tuple(variant for variant in variants if " " not in variant)
        if any(
            variant in doc_id or variant in source or variant in title
            for variant in token_variants
        ):
            score += weight * 6.0
        elif any(variant in synopsis for variant in token_variants):
            score += weight * 2.5
        elif any(variant in body for variant in token_variants):
            score += weight
        term_frequency = max(
            (
                record.token_counts.get(variant, 0)
                for variant in token_variants
            ),
            default=0,
        )
        if term_frequency:
            score += weight * (1.0 + min(3.0, float(term_frequency)) * 0.25)
    if query.phrases:
        combined = " ".join(record.haystacks)
        for phrase in query.phrases:
            if phrase in combined:
                score += _repo_phrase_weight(phrase)
    score += _doc_identity_bonus(query, record.haystacks) * 8.0
    score += _overview_intent_bonus(query, record) * 4.0
    return score * _root_meta_doc_factor(query, record) * _history_doc_factor(
        query,
        record,
    ) * _locale_doc_factor(query, record)


def _section_token_counts(
    *,
    doc_id: str,
    source: str,
    title: str,
    synopsis: str,
    body: str,
) -> Counter[str]:
    text = " ".join(
        (
            doc_id,
            source,
            title,
            title,
            synopsis,
            body[:4000],
        )
    )
    return Counter(_tokenize_search_text(text))


def _tokenize_search_text(text: str) -> list[str]:
    return re.findall(
        r"[a-z0-9][a-z0-9]*",
        text.lower().replace("/", " ").replace("-", " ").replace("_", " "),
    )


def _bm25_sparse_score(
    query: _RepoLexicalQuery,
    record: _RepoSectionRecord,
    cache: _RepoSearchCache,
) -> float:
    if not query.terms or record.token_count <= 0 or cache.avg_token_count <= 0:
        return 0.0
    corpus_size = max(1, len(cache.records))
    k1 = 1.2
    b = 0.75
    raw = 0.0
    max_raw = 0.0
    length_norm = k1 * (
        (1.0 - b) + b * (record.token_count / cache.avg_token_count)
    )
    for term in query.terms:
        tf = max(
            (
                record.token_counts.get(variant, 0)
                for variant in query.variants[term]
                if " " not in variant
            ),
            default=0,
        )
        df = max(
            (
                cache.df.get(variant, 0)
                for variant in query.variants[term]
                if " " not in variant
            ),
            default=0,
        )
        if tf <= 0 or df <= 0:
            continue
        idf = math.log(1.0 + ((corpus_size - df + 0.5) / (df + 0.5)))
        weighted_idf = idf * query.weights[term]
        raw += weighted_idf * ((tf * (k1 + 1.0)) / (tf + length_norm))
        max_raw += weighted_idf * (k1 + 1.0)
    if max_raw <= 0:
        return 0.0
    return max(0.0, min(1.0, raw / max_raw))


def _add_graph_edge(
    graph: dict[tuple[str, str], dict[tuple[str, str], float]],
    left: tuple[str, str],
    right: tuple[str, str],
    *,
    weight: float,
) -> None:
    if left == right:
        return
    graph[left][right] = max(graph[left].get(right, 0.0), weight)
    graph[right][left] = max(graph[right].get(left, 0.0), weight)


def _score_repo_record(
    record: _RepoSectionRecord,
    *,
    query: _RepoLexicalQuery,
    cache: _RepoSearchCache,
    vector_score: float,
) -> _RepoScoredHit:
    focus_support = _focus_field_support(query, record.haystacks)
    coverage = _weighted_term_coverage(query, record.haystacks)
    lexical_score = min(
        1.0,
        _field_supported_lexical_score(
            _lexical_score_from_profile(query, record.haystacks),
            focus_support=focus_support,
        )
        * _coverage_factor(coverage)
        + _overview_intent_bonus(query, record),
    )
    sparse_score = _bm25_sparse_score(query, record, cache)
    rank_factor = _root_meta_doc_factor(query, record) * _history_doc_factor(
        query,
        record,
    ) * _locale_doc_factor(query, record)
    identity_bonus = _doc_identity_bonus(query, record.haystacks)
    base_score = min(
        1.0,
        _combine_repo_scores(
            vector_score,
            lexical_score,
            sparse_score=sparse_score,
            graph_score=0.0,
        )
        + identity_bonus,
    ) * rank_factor
    return _RepoScoredHit(
        record=record,
        score=base_score,
        vector_score=vector_score,
        lexical_score=lexical_score,
        sparse_score=sparse_score,
        graph_score=0.0,
        base_score=base_score,
        rank_factor=rank_factor,
        identity_bonus=identity_bonus,
    )


def _apply_graph_scores(
    hits: list[_RepoScoredHit],
    cache: _RepoSearchCache,
) -> None:
    by_key = {
        (hit.record.doc_id, hit.record.section_id): hit
        for hit in hits
    }
    for hit in hits:
        key = (hit.record.doc_id, hit.record.section_id)
        neighbors = cache.graph_neighbors.get(key, ())
        total = 0.0
        weight_sum = 0.0
        for neighbor_key, weight in neighbors:
            weight_sum += weight
            neighbor = by_key.get(neighbor_key)
            if neighbor is None:
                continue
            total += neighbor.base_score * weight
        graph_score = total / weight_sum if weight_sum else 0.0
        hit.graph_score = graph_score
        hit.score = min(
            1.0,
            _combine_repo_scores(
                hit.vector_score,
                hit.lexical_score,
                sparse_score=hit.sparse_score,
                graph_score=graph_score,
                graph_present=bool(neighbors),
            )
            + hit.identity_bonus,
        ) * hit.rank_factor


def _repo_scored_payload(
    hit: _RepoScoredHit,
    *,
    query: str,
    lexical_query: _RepoLexicalQuery,
    include_set: Collection[IncludeField],
) -> dict[str, Any]:
    record = hit.record
    result: dict[str, Any] = {
        "doc": record.doc_id,
        "source": record.source,
        "id": record.section_id,
        "title": record.title,
        "score": hit.score,
        "vector_score": hit.vector_score,
        "lexical_score": hit.lexical_score,
        "sparse_score": hit.sparse_score,
        "graph_score": hit.graph_score,
        "anchor": record.index.anchor(record.section_id),
        "explanation": _repo_hit_explanation(hit, lexical_query),
    }
    if "synopsis" in include_set and record.synopsis:
        result["synopsis"] = record.synopsis
    if "head" in include_set:
        result["head"] = record.body[:200]
    if "evidence" in include_set:
        result["evidence"] = _evidence_snippet(record.body, query)
    return result


def _repo_hit_explanation(
    hit: _RepoScoredHit,
    query: _RepoLexicalQuery,
) -> dict[str, Any]:
    profile = _DEFAULT_RANK_PROFILE
    signal_scores = {
        "lexical": hit.lexical_score,
        "sparse": hit.sparse_score,
        "vector": hit.vector_score,
        "graph": hit.graph_score,
    }
    dominant_order = {"lexical": 4, "sparse": 3, "vector": 2, "graph": 1}
    dominant_signal = max(
        signal_scores,
        key=lambda name: (signal_scores[name], dominant_order[name]),
    )
    matched_terms = _repo_matched_terms(query, hit.record)
    notes: list[str] = []
    if matched_terms:
        notes.append("matched query terms in doc/source/title/summary/body fields")
    if hit.sparse_score > 0:
        notes.append("BM25-style sparse evidence contributed")
    if hit.graph_score > 0:
        notes.append("tree/xref/entity neighborhood support contributed")
    if hit.identity_bonus > 0:
        notes.append("document or path identity matched the query")
    if hit.rank_factor != 1.0:
        notes.append("rank factor adjusted broad root-document placement")

    return {
        "dominant_signal": dominant_signal,
        "matched_terms": matched_terms,
        "signals": {
            "vector": {
                "score": _round_score(hit.vector_score),
                "weight": profile.vector_weight,
            },
            "lexical": {
                "score": _round_score(hit.lexical_score),
                "weight": profile.lexical_weight,
            },
            "sparse": {
                "score": _round_score(hit.sparse_score),
                "weight": profile.sparse_weight,
            },
            "graph": {
                "score": _round_score(hit.graph_score),
                "weight": profile.graph_weight,
            },
        },
        "rank_factor": _round_score(hit.rank_factor),
        "identity_bonus": _round_score(hit.identity_bonus),
        "notes": notes,
    }


def _repo_matched_terms(
    query: _RepoLexicalQuery,
    record: _RepoSectionRecord,
) -> list[str]:
    if not query.terms:
        return []
    haystack = " ".join(record.haystacks)
    return [
        term
        for term in query.terms
        if any(variant in haystack for variant in query.variants[term])
    ]


def _round_score(value: float) -> float:
    return round(float(value), 4)


def _combine_repo_scores(
    vector_score: float,
    lexical_score: float,
    *,
    sparse_score: float,
    graph_score: float,
    graph_present: bool = False,
) -> float:
    profile = _DEFAULT_RANK_PROFILE
    if lexical_score <= 0 and sparse_score <= 0:
        return vector_score * profile.no_lexical_vector_weight
    trusted_sparse = _trusted_sparse_score(
        lexical_score=lexical_score,
        sparse_score=sparse_score,
    )
    base = (
        (vector_score * profile.vector_weight)
        + (lexical_score * profile.lexical_weight)
        + (trusted_sparse * profile.sparse_weight)
    )
    if not graph_present and graph_score <= 0:
        return min(1.0, base)
    return min(
        1.0,
        (base * (1.0 - profile.graph_weight)) + (graph_score * profile.graph_weight),
    )


def _trusted_sparse_score(*, lexical_score: float, sparse_score: float) -> float:
    if sparse_score <= 0:
        return 0.0
    if lexical_score <= 0:
        return sparse_score * 0.15
    profile = _DEFAULT_RANK_PROFILE
    gate = min(
        1.0,
        max(
            profile.sparse_floor_gate,
            lexical_score * profile.sparse_lexical_gate_multiplier,
        ),
    )
    return sparse_score * gate


def _build_repo_lexical_query(
    query: str,
    *,
    cache: _RepoSearchCache | None = None,
    preferred_locales: tuple[str, ...] = (),
) -> _RepoLexicalQuery:
    terms = tuple(_repo_query_terms(query))
    field_weights = _DEFAULT_RANK_PROFILE.field_weights
    variants = {term: _term_variants(term) for term in terms}
    weights = {
        term: _repo_term_weight(term)
        * _repo_corpus_term_weight(variants[term], cache)
        for term in terms
    }
    max_score = sum(weights[term] * sum(field_weights) for term in terms)
    return _RepoLexicalQuery(
        terms=terms,
        variants=variants,
        weights=weights,
        phrases=tuple(_command_phrases(query)),
        max_score=max_score,
        preferred_locales=_normalized_preferred_locales(
            preferred_locales,
            fallback=_infer_query_locale(query),
        ),
    )


def _repo_corpus_term_weight(
    variants: tuple[str, ...],
    cache: _RepoSearchCache | None,
) -> float:
    if cache is None or not cache.records:
        return 1.0
    token_variants = {variant for variant in variants if " " not in variant}
    if not token_variants:
        return 1.0
    coverage = sum(
        1
        for record in cache.records
        if any(variant in record.token_counts for variant in token_variants)
    )
    if coverage <= 0:
        return 1.0
    corpus_size = len(cache.records)
    idf = math.log(1.0 + ((corpus_size - coverage + 0.5) / (coverage + 0.5)))
    max_idf = math.log(1.0 + ((corpus_size + 0.5) / 0.5))
    if max_idf <= 0:
        return 1.0
    return 0.35 + (0.65 * max(0.0, min(1.0, idf / max_idf)))


def _lexical_score_from_profile(
    query: _RepoLexicalQuery,
    haystacks: tuple[str, str, str, str, str],
) -> float:
    if not query.terms or query.max_score <= 0:
        return 0.0
    weighted = 0.0
    for term in query.terms:
        term_weight = query.weights[term]
        variants = query.variants[term]
        field_weights = _DEFAULT_RANK_PROFILE.field_weights
        for haystack, field_weight in zip(haystacks, field_weights, strict=True):
            if any(variant in haystack for variant in variants):
                weighted += term_weight * field_weight
    combined = _normalize_search_text(" ".join(haystacks))
    for size in range(min(4, len(query.terms)), 1, -1):
        for start in range(0, len(query.terms) - size + 1):
            phrase = " ".join(query.terms[start : start + size])
            if phrase in combined:
                weighted += float(size)
    for phrase in query.phrases:
        if phrase in combined:
            weighted += _repo_phrase_weight(phrase)
    return min(1.0, weighted / query.max_score)


def _repo_query_terms(query: str) -> list[str]:
    generic = {
        "about",
        "do",
        "does",
        "from",
        "how",
        "in",
        "into",
        "it",
        "on",
        "using",
        "what",
        "when",
        "where",
        "which",
        "work",
        "works",
        "with",
    }
    terms = [term for term in _query_terms(query) if term not in generic]
    seen = set(terms)
    for word in re.findall(r"[A-Za-z0-9_][A-Za-z0-9_-]*", query.lower()):
        if (
            len(word) >= 2
            and word not in generic
            and word not in seen
            and _looks_like_compact_identifier(word)
        ):
            seen.add(word)
            terms.append(word)
    return terms


def _normalize_field_text(text: str) -> str:
    lowered = text.lower().replace("/", " ").replace("-", " ").replace("_", " ")
    return _normalize_search_text(lowered)


def _normalize_search_text(text: str) -> str:
    normalized = text.lower().replace("/", " ").replace("-", " ").replace("_", " ")
    return " ".join(re.findall(r"[a-z0-9][a-z0-9]*", normalized))


def _looks_like_compact_identifier(token: str) -> bool:
    return len(token) <= 4 or any(char.isdigit() for char in token) or "_" in token


def _repo_term_weight(term: str) -> float:
    """Down-weight broad verbs that otherwise dominate docs-heavy repos."""
    if term in {
        "run",
        "runs",
        "test",
        "tests",
        "testing",
        "use",
        "using",
        "write",
        "writes",
        "written",
    }:
        return 0.35
    return 1.0


def _overview_intent_bonus(
    query: _RepoLexicalQuery,
    record: _RepoSectionRecord,
) -> float:
    if not query.terms:
        return 0.0
    focus_term = query.terms[0]

    doc_tokens = tuple(_tokenize_search_text(record.doc_id))
    title = _normalize_search_text(record.title)
    profile = _DEFAULT_RANK_PROFILE
    bonus = 0.0
    variants = {
        variant
        for variant in query.variants.get(focus_term, ())
        if " " not in variant
    }
    if not variants:
        return 0.0
    if any(doc_tokens in {(variant,), ("docs", variant)} for variant in variants):
        bonus = max(bonus, profile.overview_doc_bonus)
    if title in variants:
        bonus = max(bonus, profile.overview_title_bonus)

    if bonus > 0 and record.section_id.count("/") <= 1:
        bonus += profile.overview_shallow_bonus
    return min(profile.overview_max_bonus, bonus)


def _focus_field_support(
    query: _RepoLexicalQuery,
    haystacks: tuple[str, str, str, str, str],
) -> float:
    if not query.terms:
        return 1.0
    doc_id, source, title, synopsis, body = haystacks
    profile = _DEFAULT_RANK_PROFILE
    focus_terms = tuple(
        term for term in query.terms if query.weights.get(term, 0.0) > 0
    )[:2]
    if not focus_terms:
        return 1.0
    total = sum(query.weights[term] for term in focus_terms)
    if total <= 0:
        return 1.0
    support = 0.0
    for term in focus_terms:
        variants = {
            variant
            for variant in query.variants.get(term, ())
            if " " not in variant
        }
        if not variants:
            continue
        if any(
            variant in doc_id or variant in source or variant in title
            for variant in variants
        ):
            support += query.weights[term]
        elif any(variant in synopsis for variant in variants):
            support += query.weights[term] * profile.focus_synopsis_support
        elif any(variant in body for variant in variants):
            support += query.weights[term] * profile.focus_body_support
    return max(0.0, min(1.0, support / total))


def _field_supported_lexical_score(score: float, *, focus_support: float) -> float:
    if score <= 0 or focus_support >= 1:
        return score
    profile = _DEFAULT_RANK_PROFILE
    multiplier = profile.focus_support_floor + (
        profile.focus_support_weight * max(0.0, focus_support)
    )
    return score * multiplier


def _weighted_term_coverage(
    query: _RepoLexicalQuery,
    haystacks: tuple[str, str, str, str, str],
) -> float:
    if not query.terms:
        return 1.0
    combined = " ".join(haystacks)
    total = sum(query.weights[term] for term in query.terms)
    if total <= 0:
        return 1.0
    matched = 0.0
    for term in query.terms:
        variants = query.variants.get(term, ())
        if any(variant in combined for variant in variants):
            matched += query.weights[term]
    return max(0.0, min(1.0, matched / total))


def _coverage_factor(coverage: float) -> float:
    profile = _DEFAULT_RANK_PROFILE
    return profile.coverage_floor + (
        profile.coverage_weight * max(0.0, min(1.0, coverage))
    )


def _doc_identity_bonus(
    query: _RepoLexicalQuery,
    haystacks: tuple[str, str, str, str, str],
) -> float:
    if not query.terms:
        return 0.0
    doc_id, source, _, _, _ = haystacks
    focus_terms = tuple(
        term for term in query.terms if query.weights.get(term, 0.0) > 0
    )[:3]
    total = sum(query.weights[term] for term in focus_terms)
    if total <= 0:
        return 0.0
    matched = 0.0
    for term in focus_terms:
        variants = {
            variant
            for variant in query.variants.get(term, ())
            if " " not in variant
        }
        if any(variant in doc_id or variant in source for variant in variants):
            matched += query.weights[term]
    support = matched / total
    return _DEFAULT_RANK_PROFILE.doc_identity_bonus_weight * max(
        0.0,
        min(1.0, support),
    )


def _root_meta_doc_factor(
    query: _RepoLexicalQuery,
    record: _RepoSectionRecord,
) -> float:
    source_path = Path(record.source)
    if source_path.parent != Path(".") or source_path.stem in {"README", "CHANGELOG"}:
        return 1.0
    if source_path.stem != source_path.stem.upper():
        return 1.0
    if _first_term_has_structural_support(query, record.haystacks):
        return 1.0
    return _DEFAULT_RANK_PROFILE.root_meta_doc_factor


def _history_doc_factor(query: _RepoLexicalQuery, record: _RepoSectionRecord) -> float:
    if _query_wants_history(query):
        return 1.0
    if not _is_history_doc(record):
        return 1.0
    return _DEFAULT_RANK_PROFILE.history_doc_generic_factor


def _is_history_doc(record: _RepoSectionRecord) -> bool:
    tokens = set(_tokenize_search_text(f"{record.doc_id} {record.source} {record.title}"))
    return bool(tokens & _HISTORY_DOC_TERMS)


def _query_wants_history(query: _RepoLexicalQuery) -> bool:
    query_terms = set(query.terms)
    if query_terms & _HISTORY_QUERY_TERMS:
        return True
    return any(
        variant in _HISTORY_QUERY_TERMS
        for term in query.terms
        for variant in query.variants.get(term, ())
        if " " not in variant
    )


def _locale_doc_factor(query: _RepoLexicalQuery, record: _RepoSectionRecord) -> float:
    if not query.preferred_locales:
        return 1.0
    doc_locale = _source_locale(record.source)
    if doc_locale is None:
        return 1.0
    profile = _DEFAULT_RANK_PROFILE
    if doc_locale in query.preferred_locales:
        return profile.locale_match_factor
    return profile.locale_mismatch_factor


def _source_locale(source: str) -> str | None:
    for part in Path(source).parts:
        normalized = part.lower().replace("_", "-")
        if normalized in _KNOWN_LOCALES:
            return normalized
        match = re.fullmatch(r"([a-z]{2})(?:-[a-z0-9]{2,8})+", normalized)
        if match and match.group(1) in _KNOWN_LOCALES:
            return match.group(1)
    return None


def _infer_query_locale(query: str) -> str | None:
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", query):
        return None
    if re.search(r"[A-Za-z]", query):
        return "en"
    return None


def _normalized_preferred_locales(
    locales: tuple[str, ...],
    *,
    fallback: str | None,
) -> tuple[str, ...]:
    normalized = tuple(
        locale.lower().replace("_", "-").split("-", 1)[0]
        for locale in locales
        if locale.strip()
    )
    if normalized:
        return tuple(
            locale for locale in normalized if locale in _KNOWN_LOCALES
        )
    if fallback is None:
        return ()
    return (fallback,)


def _first_term_has_structural_support(
    query: _RepoLexicalQuery,
    haystacks: tuple[str, str, str, str, str],
) -> bool:
    if not query.terms:
        return True
    variants = {
        variant
        for variant in query.variants.get(query.terms[0], ())
        if " " not in variant
    }
    if not variants:
        return True
    doc_id, source, title, _, _ = haystacks
    return any(
        variant in doc_id or variant in source or variant in title
        for variant in variants
    )


def _term_variants(term: str) -> tuple[str, ...]:
    variants = {term}
    if term.endswith("ies") and len(term) > 4:
        variants.add(f"{term[:-3]}y")
    if term.endswith("s") and len(term) > 3:
        variants.add(term[:-1])
    if not term.endswith("s") and len(term) > 2:
        variants.add(f"{term}s")
    if term.endswith("y") and len(term) > 3:
        variants.add(f"{term[:-1]}ies")

    if term.startswith(("eval", "evaluat")):
        variants.update(
            {
                "eval",
                "evals",
                "evaluate",
                "evaluates",
                "evaluated",
                "evaluating",
                "evaluation",
                "evaluations",
                "evaluator",
                "evaluators",
            }
        )
    if term.startswith(("depend", "deps")):
        variants.update(
            {
                "dep",
                "deps",
                "depend",
                "depends",
                "dependency",
                "dependencies",
                "dependent",
                "dependents",
            }
        )
    if term.startswith("inject"):
        variants.update(
            {
                "inject",
                "injects",
                "injected",
                "injecting",
                "injection",
                "injections",
            }
        )
    if term.startswith("config"):
        variants.update(
            {"config", "configs", "configure", "configured", "configuration"}
        )
    if term.startswith("auth"):
        variants.update({"auth", "authenticate", "authentication", "authorization"})
    if term.startswith("install"):
        variants.update(
            {
                "install",
                "installs",
                "installed",
                "installer",
                "installers",
                "installing",
                "installation",
            }
        )
    if term.startswith("login"):
        variants.update({"login", "logins", "logged", "logging"})
    if term.startswith("publish"):
        variants.update({"publish", "published", "publishes", "publishing"})
    if term.startswith("store"):
        variants.update({"store", "stored", "stores", "storage"})
    if term.startswith("stream"):
        variants.update({"stream", "streams", "streamed", "streaming"})

    return tuple(sorted(variants, key=lambda item: (len(item), item), reverse=True))


def _repo_phrase_weight(phrase: str) -> float:
    tokens = phrase.split()
    base = 2.0 + min(4.0, float(len(tokens)))
    if any(_looks_like_compact_identifier(token) for token in tokens):
        base += 2.0
    return min(8.0, base)


def _command_phrases(query: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9_][a-z0-9_-]*", query.lower())
    if len(tokens) < 2:
        return []
    generic = {
        "a",
        "an",
        "and",
        "are",
        "for",
        "how",
        "in",
        "is",
        "of",
        "or",
        "the",
        "to",
        "what",
        "where",
        "with",
    }
    phrases: list[str] = []
    seen: set[str] = set()
    for size in range(min(4, len(tokens)), 1, -1):
        for start in range(0, len(tokens) - size + 1):
            window = tokens[start : start + size]
            if any(token in generic for token in window):
                continue
            if not any(_looks_like_compact_identifier(token) for token in window):
                continue
            phrase = " ".join(window)
            if phrase not in seen:
                seen.add(phrase)
                phrases.append(phrase)
    return phrases


def _diversify_repo_hits(
    hits: list[_RepoScoredHit],
    *,
    limit: int,
    sections_per_doc: int,
) -> list[_RepoScoredHit]:
    selected: list[_RepoScoredHit] = []
    counts: dict[str, int] = {}

    def add(hit: _RepoScoredHit) -> None:
        doc_id = hit.record.doc_id
        selected.append(hit)
        counts[doc_id] = counts.get(doc_id, 0) + 1

    for hit in hits:
        doc_id = hit.record.doc_id
        if counts.get(doc_id, 0) > 0:
            continue
        add(hit)
        if len(selected) >= limit:
            return selected

    if sections_per_doc <= 1:
        return selected

    seen = {(hit.record.doc_id, hit.record.section_id) for hit in selected}
    for hit in hits:
        key = (hit.record.doc_id, hit.record.section_id)
        doc_id = key[0]
        if key in seen or counts.get(doc_id, 0) >= sections_per_doc:
            continue
        add(hit)
        seen.add(key)
        if len(selected) >= limit:
            return selected
    return selected
