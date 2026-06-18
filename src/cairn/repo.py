"""Repository-level documentation indexing workflow.

This module powers the CodeGraph-like UX for project documents:
``cairn init -y``, ``cairn sync``, ``cairn status``, and repo-scoped MCP
serving. It keeps repository state in ``.cairn/`` and stores one normal Cairn
document index per discovered source file under ``.cairn/documents/<doc_id>/``.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Collection, Iterable
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

    status = repo_status(root, config=config)
    candidates = [doc for doc in status.documents if doc.state in {"indexed", "stale"}]
    hits_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    skipped: list[dict[str, str]] = []
    per_doc_k = min(32, max(k, 3))

    for doc in candidates:
        try:
            index = DocumentIndex.load(root / doc.doc_dir)
            if len(query_vec) != index.vectors.dim:
                skipped.append(
                    {
                        "doc": doc.id,
                        "reason": (
                            f"query embedding dim {len(query_vec)} != "
                            f"index dim {index.vectors.dim}"
                        ),
                    }
                )
                continue
            doc_hits = await index.vectors.search(query_vec, k=per_doc_k)
        except Exception as exc:
            skipped.append({"doc": doc.id, "reason": str(exc)})
            continue

        for hit in doc_hits:
            node = index.tree.get(hit.id)
            if node is None:
                continue
            summary = index.summaries.get(hit.id)
            result = _repo_hit_payload(
                query=query,
                include_set=include_set,
                doc_id=doc.id,
                source=doc.source,
                index=index,
                section_id=hit.id,
                title=node.title,
                body=node.raw_text,
                synopsis=summary.synopsis if summary is not None else "",
                vector_score=hit.score,
            )
            _merge_repo_hit(hits_by_key, result)

        for node in index.tree:
            summary = index.summaries.get(node.id)
            lexical_score = _lexical_score(
                query,
                doc_id=doc.id,
                source=doc.source,
                title=node.title,
                body=node.raw_text,
                synopsis=summary.synopsis if summary is not None else "",
            )
            if lexical_score <= 0:
                continue
            result = _repo_hit_payload(
                query=query,
                include_set=include_set,
                doc_id=doc.id,
                source=doc.source,
                index=index,
                section_id=node.id,
                title=node.title,
                body=node.raw_text,
                synopsis=summary.synopsis if summary is not None else "",
                vector_score=0.0,
            )
            _merge_repo_hit(hits_by_key, result)

    hits = list(hits_by_key.values())
    hits.sort(key=lambda item: float(item["score"]), reverse=True)
    selected = _diversify_repo_hits(
        hits,
        limit=k,
        sections_per_doc=effective_sections_per_doc,
    )
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
    if lexical_score <= 0:
        combined_score = vector_score * 0.25
    else:
        combined_score = min(1.0, (vector_score * 0.45) + (lexical_score * 0.55))
    result: dict[str, Any] = {
        "doc": doc_id,
        "source": source,
        "id": section_id,
        "title": title,
        "score": combined_score,
        "vector_score": vector_score,
        "lexical_score": lexical_score,
        "anchor": index.anchor(section_id),
    }
    if "synopsis" in include_set and synopsis:
        result["synopsis"] = synopsis
    if "head" in include_set:
        result["head"] = body[:200]
    if "evidence" in include_set:
        result["evidence"] = _evidence_snippet(body, query)
    return result


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
    terms = _repo_query_terms(query)
    if not terms:
        return 0.0
    haystacks = (
        doc_id.lower().replace("-", " "),
        source.lower().replace("/", " ").replace("-", " "),
        title.lower(),
        synopsis.lower(),
        body[:2000].lower(),
    )
    weighted = 0.0
    max_score = len(terms) * 6.0 + max(0, len(terms) - 1) * 2.0
    for term in terms:
        if term in haystacks[0]:
            weighted += 1.0
        if term in haystacks[1]:
            weighted += 1.0
        if term in haystacks[2]:
            weighted += 2.0
        if term in haystacks[3]:
            weighted += 1.0
        if term in haystacks[4]:
            weighted += 1.0
    combined = _normalize_search_text(" ".join(haystacks))
    for size in range(min(4, len(terms)), 1, -1):
        for start in range(0, len(terms) - size + 1):
            phrase = " ".join(terms[start : start + size])
            if phrase in combined:
                weighted += float(size)
    for phrase in _command_phrases(query):
        if phrase in combined:
            weighted += 4.0
    return min(1.0, weighted / max_score)


def _repo_query_terms(query: str) -> list[str]:
    generic = {
        "about",
        "does",
        "from",
        "how",
        "into",
        "using",
        "what",
        "when",
        "where",
        "which",
        "with",
    }
    terms = [term for term in _query_terms(query) if term not in generic]
    seen = set(terms)
    short_code_terms = {"ai", "api", "ci", "cd", "db", "go", "js", "mcp", "py", "ts", "ui", "uv"}
    for word in re.findall(r"[A-Za-z0-9_][A-Za-z0-9_-]*", query.lower()):
        if word in short_code_terms and word not in seen:
            seen.add(word)
            terms.append(word)
    return terms


def _normalize_search_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9_][a-z0-9_-]*", text.lower()))


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
    codeish = {
        "api",
        "auth",
        "cli",
        "compose",
        "docker",
        "git",
        "http",
        "mcp",
        "pip",
        "pytest",
        "sdk",
        "uv",
        "uvx",
    }
    phrases: list[str] = []
    seen: set[str] = set()
    for size in range(min(4, len(tokens)), 1, -1):
        for start in range(0, len(tokens) - size + 1):
            window = tokens[start : start + size]
            if any(token in generic for token in window):
                continue
            if not any(token in codeish or len(token) <= 4 for token in window):
                continue
            phrase = " ".join(window)
            if phrase not in seen:
                seen.add(phrase)
                phrases.append(phrase)
    return phrases


def _diversify_repo_hits(
    hits: list[dict[str, Any]],
    *,
    limit: int,
    sections_per_doc: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for hit in hits:
        doc_id = str(hit["doc"])
        if counts.get(doc_id, 0) >= sections_per_doc:
            continue
        selected.append(hit)
        counts[doc_id] = counts.get(doc_id, 0) + 1
        if len(selected) >= limit:
            break
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
