"""Repository-level documentation indexing workflow.

This module powers the CodeGraph-like UX for project documents:
``cairn init -y``, ``cairn sync``, ``cairn status``, and repo-scoped MCP
serving. It keeps repository state in ``.cairn/`` and stores one normal Cairn
document index per discovered source file under ``.cairn/documents/<doc_id>/``.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import re
import tomllib
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
from types import ModuleType
from typing import Any, Final, Literal, Protocol, TextIO

from pydantic import BaseModel, ConfigDict, Field
from slugify import slugify

from cairn import __version__
from cairn.core.errors import ConfigError, IndexNotFoundError, ToolError
from cairn.embed.base import Embedder
from cairn.engine.indexer import Indexer
from cairn.engine.manifest import read_manifest
from cairn.entity.heuristic import HeuristicExtractor
from cairn.ingest import parser_for_path, supported_extensions
from cairn.repo_search import search_repo_index
from cairn.summarize.base import Summarizer
from cairn.tools.base import DocumentIndex, estimate_tokens_of_payload
from cairn.tools.search_semantic import IncludeField
from cairn.xref.heuristic import HeuristicXRefExtractor

_fcntl: ModuleType | None
try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows fallback
    _fcntl = None

_msvcrt: ModuleType | None
try:
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - POSIX fallback
    _msvcrt = None

CAIRN_DIR: Final = ".cairn"
CONFIG_FILENAME: Final = "config.toml"
REPO_MANIFEST_FILENAME: Final = "manifest.json"
REPO_MANIFEST_VERSION: Final = 1
SYNC_LOCK_FILENAME: Final = "sync.lock"
SYNC_LOCK_POLL_SECONDS: Final = 0.2

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

DocState = Literal["indexed", "stale", "missing", "error", "orphaned"]


class IndexSettings(Protocol):
    """Indexing knobs needed by repo sync without importing the CLI layer."""

    summary_concurrency: int
    summary_batch_size: int
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
    preferred_locales: tuple[str, ...] = Field(default=())


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
    source_file_hash: str | None = None
    indexed_source_file_hash: str | None = None
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


def cairn_dir(root: Path) -> Path:
    return root / CAIRN_DIR


def config_path(root: Path) -> Path:
    return cairn_dir(root) / CONFIG_FILENAME


def repo_manifest_path(root: Path) -> Path:
    return cairn_dir(root) / REPO_MANIFEST_FILENAME


def sync_lock_path(root: Path) -> Path:
    return cairn_dir(root) / SYNC_LOCK_FILENAME


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
    lock = _RepoSyncLock(root, progress=progress)
    await lock.acquire()
    try:
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
                summary_batch_size=index_config.summary_batch_size,
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
    finally:
        lock.release()


class _RepoSyncLock:
    """Repo-wide sync lock backed by an OS file lock.

    The lock file remains on disk for metadata, but the kernel lock is what
    serializes syncs. If a process exits, the OS releases the lock.
    """

    def __init__(
        self,
        root: Path,
        *,
        progress: Callable[[str], None] | None,
        poll_seconds: float = SYNC_LOCK_POLL_SECONDS,
    ) -> None:
        self.root = root
        self.path = sync_lock_path(root)
        self.progress = progress
        self.poll_seconds = poll_seconds
        self.acquired = False
        self.handle: TextIO | None = None

    async def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            waited = False
            while True:
                try:
                    _try_lock_sync_file(self.handle)
                except BlockingIOError:
                    if not waited:
                        _emit(
                            self.progress,
                            f"sync: waiting for existing sync lock"
                            f"{_sync_lock_owner_suffix(self.path)}",
                        )
                        waited = True
                    await asyncio.sleep(self.poll_seconds)
                else:
                    self.acquired = True
                    _write_sync_lock_payload(self.handle, _sync_lock_payload(self.root))
                    if waited:
                        _emit(self.progress, "sync: acquired sync lock")
                    return
        except BaseException:
            self.handle.close()
            self.handle = None
            raise

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            if self.acquired:
                try:
                    _clear_sync_lock_payload(self.handle)
                finally:
                    _unlock_sync_file(self.handle)
        finally:
            self.acquired = False
            self.handle.close()
            self.handle = None


def _sync_lock_payload(root: Path) -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "root": str(root.resolve()),
        "started_at": datetime.now(UTC).isoformat(),
    }


def _try_lock_sync_file(handle: TextIO) -> None:
    if _fcntl is not None:
        try:
            _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise BlockingIOError from exc
            raise
        return
    if _msvcrt is not None:  # pragma: no cover - Windows-only fallback
        handle.seek(0)
        try:
            _msvcrt.locking(handle.fileno(), _msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError from exc
        return
    msg = "no supported file locking backend available"
    raise RuntimeError(msg)


def _unlock_sync_file(handle: TextIO) -> None:
    if _fcntl is not None:
        _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
        return
    if _msvcrt is not None:  # pragma: no cover - Windows-only fallback
        handle.seek(0)
        _msvcrt.locking(handle.fileno(), _msvcrt.LK_UNLCK, 1)
        return
    msg = "no supported file locking backend available"
    raise RuntimeError(msg)


def _write_sync_lock_payload(handle: TextIO, payload: dict[str, Any]) -> None:
    handle.seek(0)
    handle.truncate()
    json.dump(payload, handle, sort_keys=True)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())


def _clear_sync_lock_payload(handle: TextIO) -> None:
    handle.seek(0)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def _read_sync_lock_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _sync_lock_owner_suffix(path: Path) -> str:
    payload = _read_sync_lock_payload(path)
    if payload is None:
        return ""

    parts: list[str] = []
    pid = payload.get("pid")
    started_at = payload.get("started_at")
    if isinstance(pid, int):
        parts.append(f"pid={pid}")
    if isinstance(started_at, str) and started_at:
        parts.append(f"started={started_at}")
    if not parts:
        return ""
    return f" ({', '.join(parts)})"


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
    payload = await search_repo_index(
        root,
        candidates=candidates,
        query=query,
        query_vec=query_vec,
        k=k,
        include_set=include_set,
        sections_per_doc=effective_sections_per_doc,
        preferred_locales=config.preferred_locales,
    )
    return {
        "tokens_returned": estimate_tokens_of_payload(payload),
        "data": payload,
    }


async def repo_context(
    root: Path,
    *,
    embedder: Embedder,
    query: str,
    k: int = 5,
    sections_per_doc: int | None = None,
    related_k: int = 3,
    level: Literal["gist", "synopsis", "full"] = "synopsis",
    max_section_chars: int = 1600,
) -> dict[str, Any]:
    """Build a compact repo-scoped context pack for an agent query."""
    if related_k < 0 or related_k > 12:
        msg = f"related_k must be in [0, 12]; got {related_k}"
        raise ToolError(msg, details={"related_k": related_k})
    if max_section_chars < 200 or max_section_chars > 8000:
        msg = f"max_section_chars must be in [200, 8000]; got {max_section_chars}"
        raise ToolError(msg, details={"max_section_chars": max_section_chars})

    search = await search_repo_documents(
        root,
        embedder=embedder,
        query=query,
        k=k,
        include=("synopsis", "evidence"),
        sections_per_doc=sections_per_doc,
    )
    hits = list(search["data"]["hits"])
    context_sections: list[dict[str, Any]] = []
    graph_nodes: dict[str, dict[str, Any]] = {}
    graph_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for rank, hit in enumerate(hits, start=1):
        index = load_repo_document_index(root, doc_id=hit["doc"])
        node = index.tree.get(hit["id"])
        if node is None:
            continue
        content = _repo_context_content(
            index,
            section_id=node.id,
            level=level,
            fallback=node.raw_text,
        )[:max_section_chars]
        relationships = _section_relationships(index, node.id, k=related_k)
        context_sections.append(
            {
                "rank": rank,
                "doc": hit["doc"],
                "source": hit["source"],
                "id": node.id,
                "title": node.title,
                "path": list(node.path),
                "anchor": index.anchor(node.id),
                "level": level,
                "content": content,
                "hit": hit,
                "relationships": relationships,
            }
        )
        _add_repo_doc_graph_node(graph_nodes, hit["doc"], source=hit["source"])
        _add_repo_section_graph_node(graph_nodes, hit["doc"], index, node.id)
        _add_repo_graph_edge(
            graph_edges,
            seen_edges,
            source=_repo_doc_node_id(hit["doc"]),
            target=_repo_section_node_id(hit["doc"], node.id),
            kind="contains",
            relation=None,
            confidence=1.0,
        )
        for related in relationships:
            _add_repo_section_graph_node(graph_nodes, hit["doc"], index, related["id"])
            _add_repo_graph_edge(
                graph_edges,
                seen_edges,
                source=_repo_section_node_id(hit["doc"], node.id),
                target=_repo_section_node_id(hit["doc"], related["id"]),
                kind=related["kind"],
                relation=related.get("relation"),
                confidence=float(related.get("confidence", 1.0)),
            )

    payload: dict[str, Any] = {
        "query": query,
        "hits": hits,
        "context_sections": context_sections,
        "relationship_map": {
            "nodes": list(graph_nodes.values()),
            "edges": graph_edges,
        },
        "stale_documents": search["data"].get("stale_documents", []),
        "skipped_documents": search["data"]["skipped_documents"],
        "codegraph_bridge": {
            "status": "not_invoked",
            "note": (
                "Cairn does not parse source code. Pair this context with the "
                "CodeGraph MCP server for symbol callers, callees, and code impact."
            ),
        },
    }
    return {
        "tokens_returned": estimate_tokens_of_payload(payload),
        "data": payload,
    }


async def repo_graph(
    root: Path,
    *,
    doc: str | None = None,
    max_sections: int = 120,
    max_entities: int = 40,
    include_entities: bool = True,
    include_xrefs: bool = True,
) -> dict[str, Any]:
    """Return a repo-level documentation relationship map."""
    if max_sections < 1 or max_sections > 500:
        msg = f"max_sections must be in [1, 500]; got {max_sections}"
        raise ToolError(msg, details={"max_sections": max_sections})
    if max_entities < 0 or max_entities > 200:
        msg = f"max_entities must be in [0, 200]; got {max_entities}"
        raise ToolError(msg, details={"max_entities": max_entities})

    status = repo_status(root)
    candidates = [
        item
        for item in status.documents
        if item.state in {"indexed", "stale"} and (doc is None or item.id == doc)
    ]
    if doc is not None and not candidates:
        msg = f"repo document is not indexed: {doc!r}"
        raise IndexNotFoundError(msg, details={"doc": doc})

    graph = _build_repo_graph_payload(
        root,
        candidates,
        max_sections=max_sections,
        max_entities=max_entities if include_entities else 0,
        include_xrefs=include_xrefs,
    )
    payload: dict[str, Any] = {
        "root": str(status.root),
        "doc": doc,
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "stats": graph["stats"],
        "skipped_documents": graph["skipped_documents"],
        "codegraph_bridge": {
            "status": "external",
            "note": (
                "This graph covers repository documentation only. Do not use Cairn "
                "as a source-code graph; connect CodeGraph for AST symbols and code edges."
            ),
        },
    }
    return {
        "tokens_returned": estimate_tokens_of_payload(payload),
        "data": payload,
    }


async def repo_impact(
    root: Path,
    *,
    doc: str,
    id: str | None = None,
    max_results: int = 24,
) -> dict[str, Any]:
    """Estimate documentation surfaces affected by a document or section change."""
    if max_results < 1 or max_results > 100:
        msg = f"max_results must be in [1, 100]; got {max_results}"
        raise ToolError(msg, details={"max_results": max_results})
    status = repo_status(root)
    doc_status = next((item for item in status.documents if item.id == doc), None)
    if doc_status is None or doc_status.state == "missing":
        msg = f"repo document is not indexed: {doc!r}"
        raise IndexNotFoundError(msg, details={"doc": doc})

    index = DocumentIndex.load(root / doc_status.doc_dir)
    if id is None:
        payload = _repo_document_impact_payload(
            root,
            status=status,
            doc_status=doc_status,
            index=index,
            max_results=max_results,
        )
    else:
        payload = _repo_section_impact_payload(
            root,
            status=status,
            doc_status=doc_status,
            index=index,
            section_id=id,
            max_results=max_results,
        )
    return {
        "tokens_returned": estimate_tokens_of_payload(payload),
        "data": payload,
    }


def _repo_context_content(
    index: DocumentIndex,
    *,
    section_id: str,
    level: Literal["gist", "synopsis", "full"],
    fallback: str,
) -> str:
    if level == "full":
        return fallback
    summary = index.summaries.get(section_id)
    if summary is None:
        return fallback
    if level == "gist":
        return summary.gist
    return summary.synopsis


def _section_relationships(
    index: DocumentIndex,
    section_id: str,
    *,
    k: int,
) -> list[dict[str, Any]]:
    if k <= 0:
        return []
    node = index.tree.require(section_id)
    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None, str | None]] = set()

    def add(
        target_id: str,
        *,
        kind: str,
        relation: str | None,
        confidence: float,
        direction: str | None = None,
    ) -> None:
        key = (target_id, kind, relation, direction)
        if key in seen:
            return
        seen.add(key)
        target = index.tree.get(target_id)
        relationships.append(
            {
                "id": target_id,
                "title": target.title if target is not None else target_id,
                "kind": kind,
                "relation": relation,
                "direction": direction,
                "confidence": round(float(confidence), 4),
                "anchor": index.anchor(target_id),
            }
        )

    if node.parent is not None:
        add(node.parent, kind="parent", relation=None, confidence=1.0)
    for child_id in node.children:
        add(child_id, kind="child", relation=None, confidence=1.0)
    if index.xrefs is not None:
        for ref in index.xrefs.outgoing_from(section_id):
            add(
                ref.dst,
                kind="xref",
                relation=ref.kind,
                confidence=ref.confidence,
                direction="outgoing",
            )
        for ref in index.xrefs.incoming_to(section_id):
            add(
                ref.src,
                kind="xref",
                relation=ref.kind,
                confidence=ref.confidence,
                direction="incoming",
            )
    relationships.sort(
        key=lambda item: (
            -float(item["confidence"]),
            str(item["kind"]),
            str(item["id"]),
            str(item.get("direction") or ""),
        )
    )
    return relationships[:k]


def _build_repo_graph_payload(
    root: Path,
    candidates: Collection[RepoDocumentStatus],
    *,
    max_sections: int,
    max_entities: int,
    include_xrefs: bool,
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    skipped: list[dict[str, str]] = []
    selected_sections: dict[str, set[str]] = defaultdict(set)
    entity_mentions: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    total_sections = 0
    truncated = False

    for doc in candidates:
        _add_repo_doc_graph_node(nodes, doc.id, source=doc.source, state=doc.state)
        try:
            index = DocumentIndex.load(root / doc.doc_dir)
        except Exception as exc:
            skipped.append({"doc": doc.id, "reason": str(exc)})
            continue

        for section in index.tree:
            total_sections += 1
            if _repo_section_count(nodes) >= max_sections:
                truncated = True
                continue
            selected_sections[doc.id].add(section.id)
            _add_repo_section_graph_node(nodes, doc.id, index, section.id)

        selected = selected_sections[doc.id]
        for node in index.tree:
            if node.id not in selected:
                continue
            source = (
                _repo_section_node_id(doc.id, node.parent)
                if node.parent in selected
                else _repo_doc_node_id(doc.id)
            )
            _add_repo_graph_edge(
                edges,
                seen_edges,
                source=source,
                target=_repo_section_node_id(doc.id, node.id),
                kind="contains",
                relation=None,
                confidence=1.0,
            )

        if include_xrefs and index.xrefs is not None:
            for ref in index.xrefs:
                if ref.src in selected and ref.dst in selected:
                    _add_repo_graph_edge(
                        edges,
                        seen_edges,
                        source=_repo_section_node_id(doc.id, ref.src),
                        target=_repo_section_node_id(doc.id, ref.dst),
                        kind="xref",
                        relation=ref.kind,
                        confidence=ref.confidence,
                    )

        if max_entities > 0 and index.entities is not None:
            for entity in index.entities:
                key = (entity.kind, entity.canonical)
                for mention in entity.mentions:
                    if mention.section_id in selected:
                        entity_mentions[key].add((doc.id, mention.section_id))

    for (kind, canonical), mentions in sorted(
        entity_mentions.items(),
        key=lambda item: (-len(item[1]), item[0][0], item[0][1].lower()),
    )[:max_entities]:
        entity_id = _repo_entity_node_id(kind, canonical)
        nodes[entity_id] = {
            "id": entity_id,
            "kind": "entity",
            "entity_kind": kind,
            "label": canonical,
            "mentions": len(mentions),
        }
        for doc_id, section_id in sorted(mentions):
            _add_repo_graph_edge(
                edges,
                seen_edges,
                source=_repo_section_node_id(doc_id, section_id),
                target=entity_id,
                kind="mentions",
                relation=kind,
                confidence=1.0,
            )

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "documents": sum(1 for node in nodes.values() if node["kind"] == "document"),
            "sections": sum(1 for node in nodes.values() if node["kind"] == "section"),
            "entities": sum(1 for node in nodes.values() if node["kind"] == "entity"),
            "edges": len(edges),
            "total_sections": total_sections,
            "truncated": truncated,
        },
        "skipped_documents": skipped,
    }


def _repo_document_impact_payload(
    root: Path,
    *,
    status: RepoStatus,
    doc_status: RepoDocumentStatus,
    index: DocumentIndex,
    max_results: int,
) -> dict[str, Any]:
    sections = [
        _impact_section_ref(doc_status.id, index, section.id, kind="contains")
        for section in list(index.tree)[:max_results]
    ]
    related_documents = _related_documents_by_entities(
        root,
        status=status,
        doc_id=doc_status.id,
        max_results=max_results,
    )
    return {
        "scope": "document",
        "doc": doc_status.id,
        "source": doc_status.source,
        "state": doc_status.state,
        "section_count": len(index.tree),
        "derived_artifacts": _repo_derived_artifacts(doc_status.id),
        "affected_surfaces": _repo_affected_surfaces(),
        "sections": sections,
        "related_documents": related_documents,
        "notes": [
            "Changing this source can make the document index stale.",
            (
                "Repo search, repo_context, repo_graph, inspectors, and MCP "
                "drilldown read derived artifacts."
            ),
        ],
    }


def _repo_section_impact_payload(
    root: Path,
    *,
    status: RepoStatus,
    doc_status: RepoDocumentStatus,
    index: DocumentIndex,
    section_id: str,
    max_results: int,
) -> dict[str, Any]:
    node = index.tree.require(section_id)
    affected = _section_relationships(index, section_id, k=max_results)
    shared = _shared_entity_section_refs(
        root,
        status=status,
        doc_id=doc_status.id,
        section_id=section_id,
        max_results=max_results,
    )
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in affected:
        key = (doc_status.id, item["id"], item["kind"])
        if key in seen:
            continue
        seen.add(key)
        merged.append({"doc": doc_status.id, **item})
    for item in shared:
        key = (item["doc"], item["id"], item["kind"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    merged = merged[:max_results]
    documents = sorted({item["doc"] for item in merged} | {doc_status.id})
    return {
        "scope": "section",
        "doc": doc_status.id,
        "source": doc_status.source,
        "id": node.id,
        "title": node.title,
        "path": list(node.path),
        "anchor": index.anchor(node.id),
        "derived_artifacts": [
            f".cairn/documents/{doc_status.id}/tree.json",
            f".cairn/documents/{doc_status.id}/summaries.json",
            f".cairn/documents/{doc_status.id}/vectors.lance",
            f".cairn/documents/{doc_status.id}/entities.json",
            f".cairn/documents/{doc_status.id}/refs.json",
            "repo search cache",
            "repo inspectors",
        ],
        "affected_surfaces": _repo_affected_surfaces(),
        "sections": merged,
        "documents": documents,
        "notes": [
            "Impact is documentation-graph impact, not source-code symbol impact.",
            "Use the CodeGraph MCP server for callers, callees, and code symbol impact.",
        ],
    }


def _related_documents_by_entities(
    root: Path,
    *,
    status: RepoStatus,
    doc_id: str,
    max_results: int,
) -> list[dict[str, Any]]:
    target_keys: set[tuple[str, str]] = set()
    for item in status.documents:
        if item.id != doc_id or item.state not in {"indexed", "stale"}:
            continue
        try:
            index = DocumentIndex.load(root / item.doc_dir)
        except Exception:
            continue
        if index.entities is not None:
            target_keys.update(
                (entity.kind, entity.canonical) for entity in index.entities
            )
        break
    if not target_keys:
        return []

    related: Counter[str] = Counter()
    for item in status.documents:
        if item.id == doc_id or item.state not in {"indexed", "stale"}:
            continue
        try:
            index = DocumentIndex.load(root / item.doc_dir)
        except Exception:
            continue
        if index.entities is None:
            continue
        keys = {(entity.kind, entity.canonical) for entity in index.entities}
        related[item.id] += len(target_keys & keys)
    rows = [
        {"doc": doc, "shared_entities": count}
        for doc, count in related.most_common(max_results)
        if count > 0
    ]
    return rows


def _shared_entity_section_refs(
    root: Path,
    *,
    status: RepoStatus,
    doc_id: str,
    section_id: str,
    max_results: int,
) -> list[dict[str, Any]]:
    target_entities: set[tuple[str, str]] = set()
    refs: list[dict[str, Any]] = []
    for item in status.documents:
        if item.state not in {"indexed", "stale"}:
            continue
        try:
            index = DocumentIndex.load(root / item.doc_dir)
        except Exception:
            continue
        if index.entities is None:
            continue
        if item.id == doc_id:
            for entity in index.entities:
                if any(mention.section_id == section_id for mention in entity.mentions):
                    target_entities.add((entity.kind, entity.canonical))
            break
    if not target_entities:
        return []
    for item in status.documents:
        if item.state not in {"indexed", "stale"}:
            continue
        try:
            index = DocumentIndex.load(root / item.doc_dir)
        except Exception:
            continue
        if index.entities is None:
            continue
        for entity in index.entities:
            key = (entity.kind, entity.canonical)
            if key not in target_entities:
                continue
            for mention in entity.mentions:
                if item.id == doc_id and mention.section_id == section_id:
                    continue
                if index.tree.get(mention.section_id) is None:
                    continue
                ref = _impact_section_ref(
                    item.id,
                    index,
                    mention.section_id,
                    kind="shared_entity",
                    relation=f"{entity.kind}:{entity.canonical}",
                    confidence=0.18,
                )
                refs.append(ref)
                if len(refs) >= max_results:
                    return refs
    return refs


def _repo_derived_artifacts(doc_id: str) -> list[str]:
    prefix = f".cairn/documents/{doc_id}"
    return [
        ".cairn/manifest.json",
        f"{prefix}/manifest.json",
        f"{prefix}/tree.json",
        f"{prefix}/summaries.json",
        f"{prefix}/vectors.lance",
        f"{prefix}/entities.json",
        f"{prefix}/refs.json",
    ]


def _repo_affected_surfaces() -> list[str]:
    return [
        "list_documents",
        "search_documents",
        "repo_context",
        "repo_graph",
        "repo_impact",
        "outline/get_section/expand/read_range with doc",
        "find_mentions/get_related with doc",
        "generated inspector HTML",
    ]


def _impact_section_ref(
    doc_id: str,
    index: DocumentIndex,
    section_id: str,
    *,
    kind: str,
    relation: str | None = None,
    confidence: float = 1.0,
) -> dict[str, Any]:
    node = index.tree.require(section_id)
    return {
        "doc": doc_id,
        "id": node.id,
        "title": node.title,
        "kind": kind,
        "relation": relation,
        "confidence": round(float(confidence), 4),
        "anchor": index.anchor(node.id),
        "path": list(node.path),
    }


def _add_repo_doc_graph_node(
    nodes: dict[str, dict[str, Any]],
    doc_id: str,
    *,
    source: str,
    state: str | None = None,
) -> None:
    node_id = _repo_doc_node_id(doc_id)
    nodes.setdefault(
        node_id,
        {
            "id": node_id,
            "kind": "document",
            "doc": doc_id,
            "label": doc_id,
            "source": source,
            **({"state": state} if state is not None else {}),
        },
    )


def _add_repo_section_graph_node(
    nodes: dict[str, dict[str, Any]],
    doc_id: str,
    index: DocumentIndex,
    section_id: str,
) -> None:
    node = index.tree.get(section_id)
    if node is None:
        return
    node_id = _repo_section_node_id(doc_id, section_id)
    nodes.setdefault(
        node_id,
        {
            "id": node_id,
            "kind": "section",
            "doc": doc_id,
            "section_id": section_id,
            "label": node.title,
            "level": node.level,
            "path": list(node.path),
            "anchor": index.anchor(section_id),
        },
    )


def _add_repo_graph_edge(
    edges: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    *,
    source: str,
    target: str,
    kind: str,
    relation: str | None,
    confidence: float,
) -> None:
    edge_kind = kind if relation is None else f"{kind}:{relation}"
    key = (source, target, edge_kind)
    if key in seen:
        return
    seen.add(key)
    edges.append(
        {
            "source": source,
            "target": target,
            "kind": kind,
            "relation": relation,
            "confidence": round(float(confidence), 4),
        }
    )


def _repo_doc_node_id(doc_id: str) -> str:
    return f"doc:{doc_id}"


def _repo_section_node_id(doc_id: str, section_id: str) -> str:
    return f"section:{doc_id}:{section_id}"


def _repo_entity_node_id(kind: str, canonical: str) -> str:
    slug = slugify(canonical) or _normalize_search_text(canonical).replace(" ", "-")
    return f"entity:{kind}:{slug}"


def _repo_section_count(nodes: dict[str, dict[str, Any]]) -> int:
    return sum(1 for node in nodes.values() if node["kind"] == "section")


def _normalize_search_text(text: str) -> str:
    normalized = text.lower().replace("/", " ").replace("-", " ").replace("_", " ")
    return " ".join(re.findall(r"[a-z0-9][a-z0-9]*", normalized))


def _repo_search_candidates(
    root: Path,
    config: RepoConfig,
) -> tuple[RepoDocumentStatus, ...]:
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


def repo_status(root: Path, *, config: RepoConfig | None = None) -> RepoStatus:
    """Compute indexed/stale/missing status for configured repo docs."""
    cfg = config or load_repo_config(root)
    docs = discover_documents(root, cfg)
    previous = {
        doc.id: doc for doc in (_read_repo_manifest_status(root) or ())
    }
    statuses: list[RepoDocumentStatus] = [
        _document_status(root, doc, previous=previous.get(doc.id)) for doc in docs
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


def _document_status(
    root: Path,
    doc: DiscoveredDocument,
    *,
    previous: RepoDocumentStatus | None = None,
) -> RepoDocumentStatus:
    manifest_path = doc.out_dir / "manifest.json"
    try:
        source_file_hash = _file_hash(doc.source)
    except OSError as exc:
        return RepoDocumentStatus(
            id=doc.id,
            source=doc.relative_source,
            doc_dir=_relative_posix(root, doc.out_dir),
            state="error",
            error=str(exc),
        )
    source_hash: str | None = None
    if not manifest_path.exists():
        try:
            parsed = parser_for_path(doc.source).parse(doc.source, doc_id=doc.id)
            source_hash = parsed.source_hash
        except Exception as exc:
            return RepoDocumentStatus(
                id=doc.id,
                source=doc.relative_source,
                doc_dir=_relative_posix(root, doc.out_dir),
                state="error",
                source_file_hash=source_file_hash,
                error=str(exc),
            )
        return RepoDocumentStatus(
            id=doc.id,
            source=doc.relative_source,
            doc_dir=_relative_posix(root, doc.out_dir),
            state="missing",
            source_hash=source_hash,
            source_file_hash=source_file_hash,
        )

    try:
        manifest = read_manifest(doc.out_dir)
    except Exception as exc:
        return RepoDocumentStatus(
            id=doc.id,
            source=doc.relative_source,
            doc_dir=_relative_posix(root, doc.out_dir),
            state="error",
            source_file_hash=source_file_hash,
            error=str(exc),
        )

    previous_indexed_file_hash = (
        previous.indexed_source_file_hash if previous is not None else None
    )
    if (
        previous is not None
        and previous.indexed_hash == manifest.source_hash
        and previous_indexed_file_hash is not None
    ):
        state: DocState = (
            "indexed" if previous_indexed_file_hash == source_file_hash else "stale"
        )
        return RepoDocumentStatus(
            id=doc.id,
            source=doc.relative_source,
            doc_dir=_relative_posix(root, doc.out_dir),
            state=state,
            section_count=previous.section_count,
            source_hash=(
                manifest.source_hash if state == "indexed" else previous.source_hash
            ),
            indexed_hash=manifest.source_hash,
            source_file_hash=source_file_hash,
            indexed_source_file_hash=previous_indexed_file_hash,
            indexed_at=manifest.indexed_at,
        )

    try:
        parsed = parser_for_path(doc.source).parse(doc.source, doc_id=doc.id)
        source_hash = parsed.source_hash
        index = DocumentIndex.load(doc.out_dir)
    except Exception as exc:
        return RepoDocumentStatus(
            id=doc.id,
            source=doc.relative_source,
            doc_dir=_relative_posix(root, doc.out_dir),
            state="error",
            source_file_hash=source_file_hash,
            error=str(exc),
        )

    state = "indexed" if manifest.source_hash == source_hash else "stale"

    return RepoDocumentStatus(
        id=doc.id,
        source=doc.relative_source,
        doc_dir=_relative_posix(root, doc.out_dir),
        state=state,
        section_count=len(index.tree),
        source_hash=source_hash,
        indexed_hash=manifest.source_hash,
        source_file_hash=source_file_hash,
        indexed_source_file_hash=(
            source_file_hash
            if state == "indexed"
            else (
                previous.indexed_source_file_hash
                if previous is not None
                else None
            )
        ),
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
            manifest_source = Path(manifest.source_path)
            source_path = (
                manifest_source
                if manifest_source.is_absolute()
                else root / manifest_source
            )
            out.append(
                RepoDocumentStatus(
                    id=child.name,
                    source=manifest.source_path,
                    doc_dir=_relative_posix(root, child),
                    state="orphaned",
                    section_count=len(index.tree),
                    indexed_hash=manifest.source_hash,
                    indexed_source_file_hash=(
                        _file_hash(source_path)
                        if source_path.exists()
                        else None
                    ),
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
        "preferred_locales = ["
        + ", ".join(_toml_string(item) for item in config.preferred_locales)
        + "]",
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


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
