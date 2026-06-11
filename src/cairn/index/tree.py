"""Tree sub-index — persistence and queries for the structural backbone.

`TreeBuilder` writes a deterministic ``tree.json`` from a parsed
:class:`Document`. `Tree` loads and queries it.

The tree is the primary navigation structure (ARCHITECTURE.md §2.1). All other
sub-indexes key into the ``section_id`` namespace it defines.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from cairn.core.errors import IndexBuildError, IndexNotFoundError
from cairn.core.types import Document, SectionNode, Span

TREE_FILENAME: Final = "tree.json"
TREE_FORMAT_VERSION: Final = 1


class TreeBuilder:
    """Writes the structural tree of a Document to ``tree.json``."""

    def build(self, document: Document, *, out_dir: Path) -> Path:
        """Serialize ``document.sections`` into ``out_dir/tree.json``.

        Args:
            document: The parsed document. Its `sections` must form a valid
                forest (every non-root section's `parent` exists; every
                referenced `child` exists).
            out_dir: Directory to write into. Created if it does not exist.

        Returns:
            The path to the written ``tree.json``.
        """
        self._validate_tree(document)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / TREE_FILENAME

        payload: dict[str, Any] = {
            "format_version": TREE_FORMAT_VERSION,
            "doc_id": document.id,
            "source_path": str(document.source_path),
            "source_hash": document.source_hash,
            "indexed_at": document.indexed_at.isoformat(),
            "cairn_version": document.cairn_version,
            "sections": [_section_to_dict(s) for s in document.sections],
        }

        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=False)
            fh.write("\n")
        return path

    @staticmethod
    def _validate_tree(document: Document) -> None:
        seen_ids: set[str] = set()
        for section in document.sections:
            if section.id in seen_ids:
                msg = f"duplicate section id in document: {section.id!r}"
                raise IndexBuildError(msg, details={"section_id": section.id})
            seen_ids.add(section.id)

        for section in document.sections:
            if section.parent is not None and section.parent not in seen_ids:
                msg = (
                    f"section {section.id!r} references unknown parent "
                    f"{section.parent!r}"
                )
                raise IndexBuildError(
                    msg,
                    details={"section_id": section.id, "parent": section.parent},
                )
            for child in section.children:
                if child not in seen_ids:
                    msg = (
                        f"section {section.id!r} references unknown child "
                        f"{child!r}"
                    )
                    raise IndexBuildError(
                        msg,
                        details={"section_id": section.id, "child": child},
                    )


class Tree:
    """Loaded tree index. Read-only queries against the structural backbone."""

    def __init__(
        self,
        sections: tuple[SectionNode, ...],
        *,
        doc_id: str,
        source_hash: str,
        indexed_at: datetime,
    ) -> None:
        self._sections = sections
        self._by_id: dict[str, SectionNode] = {s.id: s for s in sections}
        self._roots: tuple[SectionNode, ...] = tuple(
            s for s in sections if s.parent is None
        )
        self.doc_id = doc_id
        self.source_hash = source_hash
        self.indexed_at = indexed_at

    # -- construction --------------------------------------------------------

    @classmethod
    def load(cls, doc_dir: Path) -> Tree:
        """Load ``tree.json`` from a document directory."""
        path = doc_dir / TREE_FILENAME
        if not path.exists():
            msg = f"tree.json not found in {doc_dir}"
            raise IndexNotFoundError(msg, details={"path": str(path)})

        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        format_version = payload.get("format_version")
        if format_version != TREE_FORMAT_VERSION:
            msg = (
                f"unsupported tree format version: {format_version!r} "
                f"(expected {TREE_FORMAT_VERSION})"
            )
            raise IndexNotFoundError(msg, details={"path": str(path)})

        sections = tuple(_section_from_dict(d) for d in payload["sections"])
        return cls(
            sections,
            doc_id=payload["doc_id"],
            source_hash=payload["source_hash"],
            indexed_at=datetime.fromisoformat(payload["indexed_at"]),
        )

    # -- queries -------------------------------------------------------------

    def get(self, section_id: str) -> SectionNode | None:
        """Look up a section by id. Returns ``None`` if absent."""
        return self._by_id.get(section_id)

    def require(self, section_id: str) -> SectionNode:
        """Look up a section by id, raising :class:`IndexNotFoundError`."""
        node = self.get(section_id)
        if node is None:
            msg = f"section not found: {section_id!r}"
            raise IndexNotFoundError(msg, details={"section_id": section_id})
        return node

    def __contains__(self, section_id: object) -> bool:
        return isinstance(section_id, str) and section_id in self._by_id

    def __len__(self) -> int:
        return len(self._sections)

    def __iter__(self) -> Iterator[SectionNode]:
        """Yield every section in document order."""
        return iter(self._sections)

    def roots(self) -> tuple[SectionNode, ...]:
        """Top-level sections (those with `parent is None`)."""
        return self._roots

    def children_of(self, section_id: str) -> tuple[SectionNode, ...]:
        """Direct children of a section, in document order."""
        node = self.require(section_id)
        return tuple(self._by_id[cid] for cid in node.children)

    def descendants_of(self, section_id: str) -> Iterator[SectionNode]:
        """Depth-first traversal of a section's descendants (excluding self)."""
        node = self.require(section_id)
        stack: list[str] = list(reversed(node.children))
        while stack:
            current_id = stack.pop()
            current = self._by_id[current_id]
            yield current
            stack.extend(reversed(current.children))

    def ancestors_of(self, section_id: str) -> Iterator[SectionNode]:
        """Walk parents from the section up to the root (excluding self)."""
        node = self.require(section_id)
        current = node.parent
        while current is not None:
            parent_node = self._by_id[current]
            yield parent_node
            current = parent_node.parent

    def outline(
        self,
        *,
        depth: int = 2,
        focus: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return a nested outline suitable for the ``outline`` MCP tool.

        Each node has: ``id``, ``title``, ``level``, ``children`` (recursively),
        plus ``truncated: True`` when descendants exist beyond ``depth``.
        Summaries are **not** attached here — that is the MCP tool's job after
        joining with the Summaries sub-index.
        """
        if depth < 1 or depth > 6:
            msg = f"depth must be in [1, 6]; got {depth}"
            raise IndexNotFoundError(msg)

        if focus is None:
            roots = self._roots
            base_level = 0
        else:
            focused = self.require(focus)
            roots = (focused,)
            base_level = focused.level - 1

        return [self._outline_node(s, depth, base_level) for s in roots]

    def _outline_node(
        self,
        node: SectionNode,
        depth: int,
        base_level: int,
    ) -> dict[str, Any]:
        remaining = depth - (node.level - base_level)
        children_payload: list[dict[str, Any]] = []
        truncated = False
        if remaining > 0 and node.children:
            for child_id in node.children:
                child = self._by_id[child_id]
                children_payload.append(self._outline_node(child, depth, base_level))
        elif node.children:
            truncated = True

        payload: dict[str, Any] = {
            "id": node.id,
            "title": node.title,
            "level": node.level,
            "children": children_payload,
        }
        if truncated:
            payload["truncated"] = True
        return payload


# ---------------------------------------------------------------------------
# (de)serialization
# ---------------------------------------------------------------------------


def _section_to_dict(s: SectionNode) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "level": s.level,
        "parent": s.parent,
        "children": list(s.children),
        "span": {"start": s.span.start, "end": s.span.end},
        "path": list(s.path),
        "raw_text": s.raw_text,
    }


def _section_from_dict(d: dict[str, Any]) -> SectionNode:
    span = d["span"]
    return SectionNode(
        id=d["id"],
        title=d["title"],
        level=d["level"],
        parent=d["parent"],
        children=tuple(d["children"]),
        span=Span(start=span["start"], end=span["end"]),
        path=tuple(d["path"]),
        raw_text=d["raw_text"],
    )
