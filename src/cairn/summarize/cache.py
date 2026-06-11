"""File-system cache for summarizer outputs.

Keyed by ``sha256(model || level || section_hash)``. Each entry is a single
UTF-8 text file under ``<root>/<first2hex>/<remaining>.txt``. Writes are
atomic: temp-file + rename. Concurrent writers may race; the winner's
content is kept (acceptable because identical inputs should yield identical
outputs from a deterministic summarizer).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


class SummaryCache:
    """Local file-system cache for ``Summarizer`` outputs."""

    def __init__(self, root: Path) -> None:
        self.root = root

    # -- key / path helpers -------------------------------------------------

    @staticmethod
    def key(*, model: str, level: str, section_hash: str) -> str:
        """Compute the cache key for one (model, level, section) tuple."""
        h = hashlib.sha256()
        h.update(model.encode("utf-8"))
        h.update(b"\x00")
        h.update(level.encode("utf-8"))
        h.update(b"\x00")
        h.update(section_hash.encode("utf-8"))
        return h.hexdigest()

    def _path_for(self, key: str) -> Path:
        return self.root / key[:2] / f"{key[2:]}.txt"

    # -- public API ---------------------------------------------------------

    def get(self, key: str) -> str | None:
        """Return the cached summary or ``None`` if absent."""
        path = self._path_for(key)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def put(self, key: str, value: str) -> None:
        """Write a cache entry atomically."""
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(value, encoding="utf-8")
        os.replace(tmp, path)

    def clear(self) -> None:
        """Remove the entire cache directory. Safe if it doesn't exist."""
        if not self.root.exists():
            return
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        if self.root.exists() and self.root.is_dir():
            self.root.rmdir()
