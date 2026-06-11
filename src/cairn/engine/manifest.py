"""Top-level document manifest.

Per ARCHITECTURE.md §5, a document directory holds one ``manifest.json`` that
records source provenance, sub-index file pointers, builder versions, and
the model identifiers that produced each artifact. The manifest is the
contract: any file it references must exist; orphans are reapable.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from cairn.core.errors import IndexNotFoundError

MANIFEST_FILENAME: Final = "manifest.json"
MANIFEST_FORMAT_VERSION: Final = 1


class SubIndexEntry(BaseModel):
    """One sub-index pointer in the top-level manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="path relative to the document directory")
    builder_version: int = Field(ge=1)
    # Optional fields that describe what produced this artifact.
    model: str | None = None
    embedder: str | None = None
    extractor: str | None = None
    dim: int | None = None
    levels: list[str] | None = None


class Manifest(BaseModel):
    """Top-level document manifest — the contract for everything else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: int
    doc_id: str
    cairn_version: str
    source_path: str
    source_hash: str
    indexed_at: datetime
    subindexes: dict[str, SubIndexEntry]


def write_manifest(out_dir: Path, manifest: Manifest) -> Path:
    """Write ``manifest.json`` into ``out_dir`` deterministically."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MANIFEST_FILENAME

    payload: dict[str, Any] = manifest.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


def read_manifest(doc_dir: Path) -> Manifest:
    """Load and validate ``manifest.json`` from ``doc_dir``."""
    path = doc_dir / MANIFEST_FILENAME
    if not path.exists():
        msg = f"manifest.json not found in {doc_dir}"
        raise IndexNotFoundError(msg, details={"path": str(path)})

    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    version = payload.get("format_version")
    if version != MANIFEST_FORMAT_VERSION:
        msg = (
            f"unsupported manifest format version: {version!r} "
            f"(expected {MANIFEST_FORMAT_VERSION})"
        )
        raise IndexNotFoundError(msg, details={"path": str(path)})

    return Manifest.model_validate(payload)
