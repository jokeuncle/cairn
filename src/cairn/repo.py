"""Repository-level documentation indexing workflow.

This module powers the CodeGraph-like UX for project documents:
``cairn init -y``, ``cairn sync``, ``cairn status``, and repo-scoped MCP
serving. It keeps repository state in ``.cairn/`` and stores one normal Cairn
document index per discovered source file under ``.cairn/documents/<doc_id>/``.
"""

from __future__ import annotations

import json
import math
import re
import tomllib
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from slugify import slugify

from cairn import __version__
from cairn.core.errors import ConfigError, IndexNotFoundError, ToolError
from cairn.embed.base import Embedder
from cairn.engine.indexer import Indexer
from cairn.engine.manifest import read_manifest
from cairn.entity.heuristic import HeuristicExtractor
from cairn.index.vectors import l2_normalize
from cairn.ingest import parser_for_path, supported_extensions
from cairn.summarize.base import Summarizer
from cairn.tools.base import DocumentIndex, estimate_tokens_of_payload
from cairn.tools.search_semantic import IncludeField, _evidence_snippet, _query_terms
from cairn.xref.heuristic import HeuristicXRefExtractor

CAIRN_DIR: Final = ".cairn"
CONFIG_FILENAME: Final = "config.toml"
REPO_MANIFEST_FILENAME: Final = "manifest.json"
REPO_MANIFEST_VERSION: Final = 1

DEFAULT_INCLUDE: Final[tuple[str, ...]] = (
    "*.md",
    "*.markdown",
    "*.mdown",
    "*.mkd",
    "*.pdf",
    "*/README.md",
    "*/README.markdown",
    "docs/**/*.md",
    "docs/**/*.markdown",
    "docs/**/*.mdown",
    "docs/**/*.mkd",
    "docs/**/*.pdf",
)
MARKITDOWN_INCLUDE: Final[tuple[str, ...]] = (
    "*.docx",
    "*.pptx",
    "*.xlsx",
    "*.html",
    "*.htm",
    "*.epub",
    "docs/**/*.docx",
    "docs/**/*.pptx",
    "docs/**/*.xlsx",
    "docs/**/*.xls",
    "docs/**/*.html",
    "docs/**/*.htm",
    "docs/**/*.csv",
    "docs/**/*.json",
    "docs/**/*.xml",
    "docs/**/*.epub",
)
DEFAULT_EXCLUDE: Final[tuple[str, ...]] = (
    ".git/**",
    ".cairn/**",
    ".codegraph/**",
    ".hypothesis/**",
    ".mypy_cache/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
    ".venv/**",
    ".tox/**",
    ".nox/**",
    "venv/**",
    "node_modules/**",
    "dist/**",
    "build/**",
    "site/**",
    "__pycache__/**",
)
NATIVE_SUFFIXES: Final = frozenset({".md", ".markdown", ".mdown", ".mkd", ".pdf"})
SUPPORTED_SUFFIXES: Final = supported_extensions()
_REPO_SEARCH_CACHE_MAX: Final = 4

DocState = Literal["indexed", "stale", "missing", "error", "orphaned"]


class IndexSettings(Protocol):
    """Indexing knobs needed by repo sync without importing the CLI layer."""

    summary_concurrency: int
    embed_batch_size: int


class RepoConfig(BaseModel):
    """Configuration stored in ``.cairn/config.toml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    include: tuple[str, ...] = DEFAULT_INCLUDE
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE
    documents_dir: str = "documents"
    primary_doc: str | None = None
    enable_markitdown: bool = False
    search_sections_per_doc: int = Field(default=1, ge=1, le=8)


class DiscoveredDocument(BaseModel):
    """One source document discovered from repo config globs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: Path
    relative_source: str
    out_dir: Path


class RepoDocumentStatus(BaseModel):
    """Status for one repo document index."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: str
    doc_dir: str
    state: DocState
    section_count: int | None = None
    source_hash: str | None = None
    indexed_hash: str | None = None
    indexed_at: datetime | None = None
    error: str | None = None


class RepoStatus(BaseModel):
    """Computed repository documentation index status."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path
    config_path: Path
    documents: tuple[RepoDocumentStatus, ...]
    primary_doc: str | None

    @property
    def indexed_count(self) -> int:
        return sum(1 for doc in self.documents if doc.state == "indexed")

    @property
    def stale_count(self) -> int:
        return sum(1 for doc in self.documents if doc.state == "stale")

    @property
    def missing_count(self) -> int:
        return sum(1 for doc in self.documents if doc.state == "missing")

    @property
    def error_count(self) -> int:
        return sum(1 for doc in self.documents if doc.state == "error")


class RepoSyncResult(BaseModel):
    """Outcome for one document during ``cairn sync``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: str
    manifest_path: Path | None = None
    rebuilt: bool
    ok: bool = True
    error: str | None = None


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
    signature: tuple[tuple[str, str, str, str, int], ...]
    records: tuple[_RepoSectionRecord, ...]
    skipped: tuple[dict[str, str], ...]
    doc_dims: dict[str, int]
    df: dict[str, int]
    avg_token_count: float
    graph_neighbors: dict[tuple[str, str], tuple[tuple[tuple[str, str], float], ...]]


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


_REPO_SEARCH_CACHES: dict[Path, _RepoSearchCache] = {}
_DEFAULT_RANK_PROFILE = _RepoRankProfile()


def cairn_dir(root: Path) -> Path:
    return root / CAIRN_DIR


def config_path(root: Path) -> Path:
    return cairn_dir(root) / CONFIG_FILENAME


def repo_manifest_path(root: Path) -> Path:
    return cairn_dir(root) / REPO_MANIFEST_FILENAME


def find_repo_root(start: Path | None = None) -> Path:
    """Find the nearest ancestor with ``.cairn/config.toml``."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if config_path(candidate).exists():
            return candidate
    msg = "Cairn repo config not found. Run `cairn init -y` first."
    raise ConfigError(msg, details={"start": str(current)})


def write_default_config(
    root: Path,
    *,
    force: bool = False,
    enable_markitdown: bool = False,
) -> Path:
    """Create ``.cairn/config.toml`` with conservative repo-doc defaults."""
    path = config_path(root)
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    include = DEFAULT_INCLUDE
    if enable_markitdown:
        include = (*DEFAULT_INCLUDE, *MARKITDOWN_INCLUDE)
    cfg = RepoConfig(
        include=include,
        primary_doc="readme",
        enable_markitdown=enable_markitdown,
    )
    path.write_text(_render_config(cfg), encoding="utf-8")
    return path


def load_repo_config(root: Path) -> RepoConfig:
    path = config_path(root)
    if not path.exists():
        msg = "Cairn repo config not found. Run `cairn init -y` first."
        raise ConfigError(msg, details={"path": str(path)})
    with path.open("rb") as fh:
        payload = tomllib.load(fh)
    try:
        return RepoConfig.model_validate(payload)
    except ValueError as exc:
        msg = f"invalid Cairn repo config: {path}"
        raise ConfigError(msg, details={"path": str(path)}) from exc


def discover_documents(root: Path, config: RepoConfig) -> tuple[DiscoveredDocument, ...]:
    """Discover configured source documents in deterministic order."""
    candidates: list[Path] = []
    seen: set[Path] = set()
    allowed_suffixes = SUPPORTED_SUFFIXES if config.enable_markitdown else NATIVE_SUFFIXES
    for pattern in config.include:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            rel = _relative_posix(root, resolved)
            if _is_excluded(rel, config.exclude):
                continue
            if resolved.suffix.lower() not in allowed_suffixes:
                continue
            seen.add(resolved)
            candidates.append(resolved)

    used_ids: set[str] = set()
    docs: list[DiscoveredDocument] = []
    for path in sorted(candidates, key=lambda p: _relative_posix(root, p)):
        rel = _relative_posix(root, path)
        doc_id = _unique_doc_id(_doc_id_for_relative_path(rel), used_ids)
        used_ids.add(doc_id)
        docs.append(
            DiscoveredDocument(
                id=doc_id,
                source=path,
                relative_source=rel,
                out_dir=document_dir(root, config, doc_id),
            )
        )
    return tuple(docs)


def document_dir(root: Path, config: RepoConfig, doc_id: str) -> Path:
    return cairn_dir(root) / config.documents_dir / doc_id


def load_repo_document_index(
    root: Path,
    *,
    doc_id: str | None = None,
) -> DocumentIndex:
    """Load a repo document by id, or the configured primary document."""
    config = load_repo_config(root)
    status = repo_status(root, config=config)
    selected = doc_id or _choose_primary_doc(status)
    if selected is None:
        msg = "no indexed Cairn documents found. Run `cairn sync` first."
        raise IndexNotFoundError(msg, details={"root": str(root)})
    doc = next((item for item in status.documents if item.id == selected), None)
    if doc is None or doc.state == "missing":
        msg = f"repo document is not indexed: {selected!r}"
        raise IndexNotFoundError(msg, details={"doc": selected})
    return DocumentIndex.load(root / doc.doc_dir)


async def sync_repo(
    root: Path,
    *,
    summarizer: Summarizer,
    embedder: Embedder,
    index_config: IndexSettings,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
) -> tuple[RepoSyncResult, ...]:
    """Index every configured repo document, reusing per-document no-op checks."""
    config = load_repo_config(root)
    docs = discover_documents(root, config)
    if not docs:
        msg = "no documents matched .cairn/config.toml include patterns"
        raise ConfigError(msg, details={"root": str(root)})

    results: list[RepoSyncResult] = []
    for number, doc in enumerate(docs, start=1):
        _emit(progress, f"doc {number}/{len(docs)} {doc.id}: {doc.relative_source}")

        def doc_progress(message: str, doc_id: str = doc.id) -> None:
            _emit(progress, f"{doc_id}: {message}")

        indexer = Indexer(
            parser=parser_for_path(doc.source),
            summarizer=summarizer,
            embedder=embedder,
            entity_extractor=HeuristicExtractor(),
            xref_extractor=HeuristicXRefExtractor(),
            summary_concurrency=index_config.summary_concurrency,
            embed_batch_size=index_config.embed_batch_size,
            progress=doc_progress,
        )
        try:
            result = await indexer.index_path(
                doc.source,
                out_dir=doc.out_dir,
                doc_id=doc.id,
                force=force,
            )
            results.append(
                RepoSyncResult(
                    id=doc.id,
                    source=doc.relative_source,
                    manifest_path=result.manifest_path,
                    rebuilt=result.rebuilt,
                )
            )
        except Exception as exc:
            _emit(progress, f"{doc.id}: failed: {exc}")
            results.append(
                RepoSyncResult(
                    id=doc.id,
                    source=doc.relative_source,
                    rebuilt=False,
                    ok=False,
                    error=str(exc),
                )
            )

    write_repo_manifest(root, repo_status(root, config=config))
    return tuple(results)


async def search_repo_documents(
    root: Path,
    *,
    embedder: Embedder,
    query: str,
    k: int = 8,
    include: Iterable[IncludeField] = ("synopsis", "head", "evidence"),
    sections_per_doc: int | None = None,
) -> dict[str, Any]:
    """Search across every indexed document in a repository Cairn index."""
    if k < 1 or k > 32:
        msg = f"k must be in [1, 32]; got {k}"
        raise ToolError(msg, details={"k": k})
    if not query.strip():
        msg = "query must not be empty"
        raise ToolError(msg)

    config = load_repo_config(root)
    effective_sections_per_doc = (
        config.search_sections_per_doc
        if sections_per_doc is None
        else sections_per_doc
    )
    if effective_sections_per_doc < 1 or effective_sections_per_doc > 8:
        msg = f"sections_per_doc must be in [1, 8]; got {sections_per_doc}"
        raise ToolError(msg, details={"sections_per_doc": sections_per_doc})

    include_set = set(include)
    bad = include_set - {"synopsis", "head", "evidence"}
    if bad:
        msg = f"invalid include values: {sorted(bad)}"
        raise ToolError(msg, details={"invalid": sorted(bad)})

    vectors = await embedder.embed([query])
    if not vectors:
        msg = "embedder returned no vector for query"
        raise ToolError(msg)
    query_vec = vectors[0]

    candidates = _repo_search_candidates(root, config)
    cache = await _get_repo_search_cache(root, candidates)
    lexical_query = _build_repo_lexical_query(query, cache=cache)
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

    for record in cache.records:
        if record.doc_id in incompatible_docs:
            continue
        scored = _score_repo_record(
            record,
            query=lexical_query,
            cache=cache,
            vector_score=_cosine_score(normalized_query, record.vector),
        )
        hits_by_key[(record.doc_id, record.section_id)] = scored

    hits = list(hits_by_key.values())
    _apply_graph_scores(hits, cache)
    hits.sort(key=lambda item: item.score, reverse=True)
    selected_records = _diversify_repo_hits(
        hits,
        limit=k,
        sections_per_doc=effective_sections_per_doc,
    )
    selected = [
        _repo_scored_payload(
            hit,
            query=query,
            include_set=include_set,
        )
        for hit in selected_records
    ]
    payload: dict[str, Any] = {
        "query": query,
        "hits": selected,
        "sections_per_doc": effective_sections_per_doc,
        "searched_documents": len(candidates),
        "skipped_documents": skipped,
        "cursor": None,
    }
    return {
        "tokens_returned": estimate_tokens_of_payload(payload),
        "data": payload,
    }


def _repo_search_candidates(
    root: Path,
    config: RepoConfig,
) -> tuple[RepoDocumentStatus, ...]:
    manifest = _read_repo_manifest_status(root)
    if manifest is not None:
        return tuple(doc for doc in manifest if doc.state in {"indexed", "stale"})
    status = repo_status(root, config=config)
    return tuple(doc for doc in status.documents if doc.state in {"indexed", "stale"})


def _read_repo_manifest_status(root: Path) -> tuple[RepoDocumentStatus, ...] | None:
    path = repo_manifest_path(root)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if payload.get("format_version") != REPO_MANIFEST_VERSION:
            return None
        return tuple(
            RepoDocumentStatus.model_validate(item)
            for item in payload.get("documents", [])
        )
    except (OSError, ValueError, TypeError):
        return None


async def _get_repo_search_cache(
    root: Path,
    candidates: Collection[RepoDocumentStatus],
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
    for doc in candidates:
        try:
            index = DocumentIndex.load(root / doc.doc_dir)
            doc_dims[doc.id] = index.vectors.dim
            vectors = {
                entry.id: tuple(entry.vector)
                for entry in await index.vectors.entries()
            }
        except Exception as exc:
            skipped.append({"doc": doc.id, "reason": str(exc)})
            continue

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
                _add_graph_edge(
                    graph_weights,
                    (doc.id, node.id),
                    (doc.id, node.parent),
                    weight=0.55,
                )
        if index.xrefs is not None:
            for ref in index.xrefs:
                if ref.src in vector_section_ids and ref.dst in vector_section_ids:
                    _add_graph_edge(
                        graph_weights,
                        (doc.id, ref.src),
                        (doc.id, ref.dst),
                        weight=max(0.2, min(1.0, ref.confidence)),
                    )
        if index.entities is not None:
            for entity in index.entities:
                key = f"{entity.kind}:{entity.canonical}".lower()
                for mention in entity.mentions:
                    if mention.section_id in vector_section_ids:
                        entity_sections[key].add((doc.id, mention.section_id))

    for section_keys in entity_sections.values():
        if len(section_keys) < 2 or len(section_keys) > 24:
            continue
        ordered = sorted(section_keys)
        for i, src in enumerate(ordered):
            for dst in ordered[i + 1 :]:
                _add_graph_edge(graph_weights, src, dst, weight=0.18)

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
    )
    if (
        resolved_root not in _REPO_SEARCH_CACHES
        and len(_REPO_SEARCH_CACHES) >= _REPO_SEARCH_CACHE_MAX
    ):
        oldest = next(iter(_REPO_SEARCH_CACHES))
        del _REPO_SEARCH_CACHES[oldest]
    _REPO_SEARCH_CACHES[resolved_root] = cache
    return cache


def _repo_search_signature(
    candidates: Collection[RepoDocumentStatus],
) -> tuple[tuple[str, str, str, str, int], ...]:
    return tuple(
        (
            doc.id,
            doc.doc_dir,
            doc.state,
            doc.indexed_hash or "",
            doc.section_count or 0,
        )
        for doc in candidates
    )


def _cosine_score(query: list[float], vector: tuple[float, ...]) -> float:
    if len(query) != len(vector):
        return 0.0
    score = sum(a * b for a, b in zip(query, vector, strict=True))
    return max(0.0, min(1.0, score))


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
    rank_factor = _root_meta_doc_factor(query, record)
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
            neighbor = by_key.get(neighbor_key)
            if neighbor is None:
                continue
            total += neighbor.base_score * weight
            weight_sum += weight
        graph_score = total / weight_sum if weight_sum else 0.0
        hit.graph_score = graph_score
        hit.score = min(
            1.0,
            _combine_repo_scores(
                hit.vector_score,
                hit.lexical_score,
                sparse_score=hit.sparse_score,
                graph_score=graph_score,
            )
            + hit.identity_bonus,
        ) * hit.rank_factor


def _repo_scored_payload(
    hit: _RepoScoredHit,
    *,
    query: str,
    include_set: Collection[str],
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
    }
    if "synopsis" in include_set and record.synopsis:
        result["synopsis"] = record.synopsis
    if "head" in include_set:
        result["head"] = record.body[:200]
    if "evidence" in include_set:
        result["evidence"] = _evidence_snippet(record.body, query)
    return result


def _repo_hit_payload(
    *,
    query: str,
    include_set: Collection[str],
    doc_id: str,
    source: str,
    index: DocumentIndex,
    section_id: str,
    title: str,
    body: str,
    synopsis: str,
    vector_score: float,
) -> dict[str, Any]:
    lexical_score = _lexical_score(
        query,
        doc_id=doc_id,
        source=source,
        title=title,
        body=body,
        synopsis=synopsis,
    )
    combined_score = _combine_repo_scores(
        vector_score,
        lexical_score,
        sparse_score=0.0,
        graph_score=0.0,
    )
    result: dict[str, Any] = {
        "doc": doc_id,
        "source": source,
        "id": section_id,
        "title": title,
        "score": combined_score,
        "vector_score": vector_score,
        "lexical_score": lexical_score,
        "sparse_score": 0.0,
        "graph_score": 0.0,
        "anchor": index.anchor(section_id),
    }
    if "synopsis" in include_set and synopsis:
        result["synopsis"] = synopsis
    if "head" in include_set:
        result["head"] = body[:200]
    if "evidence" in include_set:
        result["evidence"] = _evidence_snippet(body, query)
    return result


def _combine_repo_scores(
    vector_score: float,
    lexical_score: float,
    *,
    sparse_score: float,
    graph_score: float,
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
    if graph_score <= 0:
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


def _merge_repo_hit(
    hits_by_key: dict[tuple[str, str], dict[str, Any]],
    result: dict[str, Any],
) -> None:
    key = (str(result["doc"]), str(result["id"]))
    existing = hits_by_key.get(key)
    if existing is None or float(result["score"]) > float(existing["score"]):
        hits_by_key[key] = result


def _lexical_score(
    query: str,
    *,
    doc_id: str,
    source: str,
    title: str,
    body: str,
    synopsis: str,
) -> float:
    """Small lexical boost for repo-wide ranking across heterogeneous docs."""
    haystacks = (
        _normalize_field_text(doc_id),
        _normalize_field_text(source),
        _normalize_field_text(title),
        _normalize_field_text(synopsis),
        _normalize_field_text(body[:2000]),
    )
    return _lexical_score_from_profile(_build_repo_lexical_query(query), haystacks)


def _build_repo_lexical_query(
    query: str,
    *,
    cache: _RepoSearchCache | None = None,
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


def repo_status(root: Path, *, config: RepoConfig | None = None) -> RepoStatus:
    """Compute indexed/stale/missing status for configured repo docs."""
    cfg = config or load_repo_config(root)
    docs = discover_documents(root, cfg)
    statuses: list[RepoDocumentStatus] = [
        _document_status(root, doc) for doc in docs
    ]
    statuses.extend(_orphaned_statuses(root, cfg, {doc.id for doc in docs}))
    return RepoStatus(
        root=root,
        config_path=config_path(root),
        documents=tuple(statuses),
        primary_doc=cfg.primary_doc,
    )


def write_repo_manifest(root: Path, status: RepoStatus) -> Path:
    """Write a lightweight repo-level manifest for humans and tools."""
    path = repo_manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "format_version": REPO_MANIFEST_VERSION,
        "cairn_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(root),
        "primary_doc": status.primary_doc,
        "documents": [doc.model_dump(mode="json") for doc in status.documents],
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


def _document_status(root: Path, doc: DiscoveredDocument) -> RepoDocumentStatus:
    manifest_path = doc.out_dir / "manifest.json"
    source_hash: str | None = None
    try:
        parsed = parser_for_path(doc.source).parse(doc.source, doc_id=doc.id)
        source_hash = parsed.source_hash
    except Exception as exc:
        return RepoDocumentStatus(
            id=doc.id,
            source=doc.relative_source,
            doc_dir=_relative_posix(root, doc.out_dir),
            state="error",
            error=str(exc),
        )

    if not manifest_path.exists():
        return RepoDocumentStatus(
            id=doc.id,
            source=doc.relative_source,
            doc_dir=_relative_posix(root, doc.out_dir),
            state="missing",
            source_hash=source_hash,
        )

    try:
        manifest = read_manifest(doc.out_dir)
        index = DocumentIndex.load(doc.out_dir)
    except Exception as exc:
        return RepoDocumentStatus(
            id=doc.id,
            source=doc.relative_source,
            doc_dir=_relative_posix(root, doc.out_dir),
            state="error",
            source_hash=source_hash,
            error=str(exc),
        )

    return RepoDocumentStatus(
        id=doc.id,
        source=doc.relative_source,
        doc_dir=_relative_posix(root, doc.out_dir),
        state="indexed" if manifest.source_hash == source_hash else "stale",
        section_count=len(index.tree),
        source_hash=source_hash,
        indexed_hash=manifest.source_hash,
        indexed_at=manifest.indexed_at,
    )


def _orphaned_statuses(
    root: Path,
    config: RepoConfig,
    discovered_ids: set[str],
) -> Iterable[RepoDocumentStatus]:
    docs_root = cairn_dir(root) / config.documents_dir
    if not docs_root.exists():
        return ()
    out: list[RepoDocumentStatus] = []
    for child in sorted(docs_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name in discovered_ids:
            continue
        try:
            manifest = read_manifest(child)
            index = DocumentIndex.load(child)
            out.append(
                RepoDocumentStatus(
                    id=child.name,
                    source=manifest.source_path,
                    doc_dir=_relative_posix(root, child),
                    state="orphaned",
                    section_count=len(index.tree),
                    indexed_hash=manifest.source_hash,
                    indexed_at=manifest.indexed_at,
                )
            )
        except Exception as exc:
            out.append(
                RepoDocumentStatus(
                    id=child.name,
                    source="",
                    doc_dir=_relative_posix(root, child),
                    state="error",
                    error=str(exc),
                )
            )
    return tuple(out)


def _choose_primary_doc(status: RepoStatus) -> str | None:
    indexed = [doc for doc in status.documents if doc.state in {"indexed", "stale"}]
    if status.primary_doc and any(doc.id == status.primary_doc for doc in indexed):
        return status.primary_doc
    if indexed:
        return indexed[0].id
    return None


def _render_config(config: RepoConfig) -> str:
    lines = [
        "# Cairn repository documentation index.",
        "# Paths are relative to the repository root.",
        f"documents_dir = {_toml_string(config.documents_dir)}",
        f"enable_markitdown = {str(config.enable_markitdown).lower()}",
        f"search_sections_per_doc = {config.search_sections_per_doc}",
    ]
    if config.primary_doc is not None:
        lines.append(f"primary_doc = {_toml_string(config.primary_doc)}")
    lines.extend(
        [
            "",
            "include = [",
            *[f"  {_toml_string(item)}," for item in config.include],
            "]",
            "",
            "exclude = [",
            *[f"  {_toml_string(item)}," for item in config.exclude],
            "]",
            "",
        ]
    )
    return "\n".join(lines)


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _relative_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_excluded(relative_path: str, patterns: tuple[str, ...]) -> bool:
    rel = Path(relative_path)
    rel_posix = rel.as_posix()
    for pattern in patterns:
        if rel.match(pattern) or fnmatchcase(rel_posix, pattern):
            return True
        if _matches_excluded_dir(rel, pattern):
            return True
    return False


def _matches_excluded_dir(relative_path: Path, pattern: str) -> bool:
    """Treat simple ``name/**`` excludes as directory names at any depth."""
    if not pattern.endswith("/**"):
        return False
    dirname = pattern[:-3]
    if not dirname or "/" in dirname:
        return False
    return dirname in relative_path.parts


def _doc_id_for_relative_path(relative_path: str) -> str:
    stem = Path(relative_path).with_suffix("").as_posix()
    return slugify(stem.replace("/", "-")) or "document"


def _unique_doc_id(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    suffix = 2
    while f"{base}-{suffix}" in used:
        suffix += 1
    return f"{base}-{suffix}"


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)
