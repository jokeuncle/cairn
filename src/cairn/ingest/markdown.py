"""Markdown parser — Markdown source → canonical Document AST.

Preserves heading hierarchy, generates stable hierarchical slug-based section
IDs, computes byte spans, and emits ``raw_text`` that excludes descendant
section bodies (per ARCHITECTURE.md §2.2).

Front-matter is parsed as document-level metadata and attached only to the
first section as the document entry point. Preambles and headingless prose are
preserved as independent synthetic sections without changing heading IDs.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.front_matter import front_matter_plugin
from slugify import slugify

from cairn import __version__
from cairn.core.errors import ParseError
from cairn.core.types import Document, SectionNode, Span


class MarkdownParser:
    """CommonMark-compliant Markdown parser with front-matter and tables."""

    name = "markdown"
    extensions: tuple[str, ...] = (".md", ".markdown", ".mdown", ".mkd")

    def __init__(self) -> None:
        md = MarkdownIt("commonmark", {"html": False})
        md.use(front_matter_plugin)
        md.enable(["table"])
        self._md = md

    def parse(
        self,
        source: Path | bytes | str,
        *,
        doc_id: str | None = None,
    ) -> Document:
        source_path, text, derived_doc_id = self._resolve_source(source, doc_id)

        text_bytes = text.encode("utf-8")
        line_offsets = _compute_line_offsets(text_bytes)
        tokens = self._md.parse(text)
        headings = _extract_headings(tokens)
        metadata = _frontmatter_metadata(text)
        sections = _build_sections(
            headings,
            text_bytes,
            line_offsets,
            document_metadata=metadata,
        )
        body_start_line = next(
            (token.map[1] for token in tokens if token.type == "front_matter" and token.map),
            0,
        )
        preamble_end_line = headings[0][2] if headings else len(line_offsets) - 1
        start = _line_to_byte(line_offsets, body_start_line, len(text_bytes))
        end = _line_to_byte(line_offsets, preamble_end_line, len(text_bytes))
        preamble = text_bytes[start:end].decode("utf-8")
        if preamble.strip():
            occupied = {node.id for node in sections}
            section_id = "document-introduction"
            suffix = 2
            while section_id in occupied:
                section_id = f"document-introduction-{suffix}"
                suffix += 1
            source_title = derived_doc_id if source_path.name.startswith("<") else source_path.stem
            title = str(metadata.get("title") or source_title)
            if headings:
                title = f"{title} — Introduction"
            sections.insert(
                0,
                SectionNode(
                    id=section_id,
                    title=title,
                    level=1,
                    parent=None,
                    span=Span(start=start, end=end),
                    path=(title,),
                    raw_text=preamble,
                    metadata=dict(metadata),
                ),
            )
            # Document metadata belongs to the entry point only.
            if len(sections) > 1:
                sections[1] = sections[1].model_copy(update={"metadata": {}})

        return Document(
            id=derived_doc_id,
            source_path=source_path,
            source_hash=hashlib.sha256(text_bytes).hexdigest(),
            sections=tuple(sections),
            indexed_at=datetime.now(UTC),
            cairn_version=__version__,
            metadata=metadata,
        )

    @staticmethod
    def _resolve_source(
        source: Path | bytes | str,
        doc_id: str | None,
    ) -> tuple[Path, str, str]:
        if isinstance(source, Path):
            try:
                text = source.read_text(encoding="utf-8")
            except OSError as exc:
                msg = f"could not read source file: {source}"
                raise ParseError(msg, details={"path": str(source)}) from exc
            resolved_id = doc_id or _slug_or_raise(source.stem, ctx="filename stem")
            return source, text, resolved_id

        if doc_id is None:
            msg = "doc_id is required when source is not a path"
            raise ParseError(msg)

        text = source.decode("utf-8") if isinstance(source, bytes) else source
        return Path(f"<in-memory:{doc_id}>"), text, doc_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_line_offsets(text_bytes: bytes) -> list[int]:
    """Return byte offsets where each line begins.

    The list has length ``num_lines + 1``: the final element equals
    ``len(text_bytes)``, acting as a virtual one-past-the-end line start so
    callers can address EOF uniformly.
    """
    offsets = [0]
    for i, byte in enumerate(text_bytes):
        if byte == 0x0A:  # newline
            offsets.append(i + 1)
    offsets.append(len(text_bytes))
    return offsets


def _heading_title(inline_tok: Token) -> str:
    """Extract plain text title from a heading's inline token.

    Concatenates the text content of leaf ``text`` children, dropping markup.
    Falls back to the raw inline content if no children are present.
    """
    if inline_tok.children is None:
        return inline_tok.content
    parts: list[str] = []
    for child in inline_tok.children:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
    return "".join(parts).strip() or inline_tok.content.strip()


def _extract_headings(tokens: list[Token]) -> list[tuple[int, str, int, int]]:
    """Return ``(level, title, line_start, line_end_excl)`` for each heading."""
    headings: list[tuple[int, str, int, int]] = []
    for i, tok in enumerate(tokens):
        if tok.type != "heading_open" or tok.map is None:
            continue
        level = int(tok.tag[1])
        line_start, line_end_excl = tok.map
        # Inline token always follows heading_open.
        if i + 1 >= len(tokens) or tokens[i + 1].type != "inline":
            continue
        title = _heading_title(tokens[i + 1])
        headings.append((level, title, line_start, line_end_excl))
    return headings


def _slug_or_raise(text: str, *, ctx: str) -> str:
    slug = slugify(text)
    if not slug:
        msg = f"could not derive a slug from {ctx}: {text!r}"
        raise ParseError(msg)
    return slug


def _safe_slug(text: str) -> str:
    """Slug that always returns something usable; falls back to ``section``."""
    return slugify(text) or "section"


def _build_sections(
    headings: list[tuple[int, str, int, int]],
    text_bytes: bytes,
    line_offsets: list[int],
    *,
    document_metadata: dict[str, Any] | None = None,
) -> list[SectionNode]:
    """Assemble SectionNode objects from heading metadata."""
    if not headings:
        return []

    n = len(headings)
    total_bytes = len(text_bytes)

    # Territory: end at next heading with level <= current_level (else EOF).
    territory_end_line: list[int] = []
    for i, (level, _, _, _) in enumerate(headings):
        next_terr = len(line_offsets) - 1
        for j in range(i + 1, n):
            if headings[j][0] <= level:
                next_terr = headings[j][2]
                break
        territory_end_line.append(next_terr)

    # Raw text end: next heading at ANY level (else territory end).
    raw_text_end_line: list[int] = []
    for i in range(n):
        if i + 1 < n:
            raw_text_end_line.append(headings[i + 1][2])
        else:
            raw_text_end_line.append(territory_end_line[i])

    # Hierarchical IDs, parents, paths.
    metadata: list[tuple[str, str, int, str | None, tuple[str, ...]]] = []
    stack: list[tuple[int, str, str]] = []  # (level, id, title)
    sibling_counters: dict[tuple[str, str], int] = defaultdict(int)

    for level, title, _line_start, _line_end in headings:
        while stack and stack[-1][0] >= level:
            stack.pop()

        parent_id = stack[-1][1] if stack else None
        slug = _safe_slug(title)
        key = (parent_id or "", slug)
        sibling_counters[key] += 1
        count = sibling_counters[key]
        unique_slug = slug if count == 1 else f"{slug}-{count}"

        section_id = f"{parent_id}/{unique_slug}" if parent_id else unique_slug
        path = (*(t for _, _, t in stack), title)

        metadata.append((section_id, title, level, parent_id, path))
        stack.append((level, section_id, title))

    children_map: dict[str, list[str]] = defaultdict(list)
    for sid, _title, _level, parent_id, _path in metadata:
        if parent_id is not None:
            children_map[parent_id].append(sid)

    sections: list[SectionNode] = []
    for idx, (level, _title_h, _line_start, line_end_excl) in enumerate(headings):
        section_id, title, _lvl, parent_id, path = metadata[idx]

        span_start_line = headings[idx][2]
        span_end_line = territory_end_line[idx]
        span = Span(
            start=_line_to_byte(line_offsets, span_start_line, total_bytes),
            end=_line_to_byte(line_offsets, span_end_line, total_bytes),
        )

        raw_start = _line_to_byte(line_offsets, line_end_excl, total_bytes)
        raw_end = _line_to_byte(line_offsets, raw_text_end_line[idx], total_bytes)
        raw_text = text_bytes[raw_start:raw_end].decode("utf-8")

        sections.append(
            SectionNode(
                id=section_id,
                title=title,
                level=level,
                parent=parent_id,
                children=tuple(children_map.get(section_id, ())),
                span=span,
                path=path,
                raw_text=raw_text,
                metadata=dict(document_metadata or {}) if idx == 0 else {},
            )
        )

    return sections


def _frontmatter_metadata(text: str) -> dict[str, Any]:
    """Extract common Markdown frontmatter fields without adding a YAML dependency."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        return {}

    raw = lines[1:end]
    metadata: dict[str, Any] = {}
    allowed = {"title", "description", "tags", "date", "draft"}
    i = 0
    while i < len(raw):
        line = raw[i]
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            i += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key not in allowed:
            i += 1
            continue
        value = value.strip()
        if key == "tags":
            if value:
                metadata[key] = _parse_tags_value(value)
                i += 1
                continue
            tags: list[str] = []
            i += 1
            while i < len(raw):
                child = raw[i]
                stripped = child.strip()
                if not child.startswith((" ", "\t")) or not stripped.startswith("- "):
                    break
                tag = _strip_scalar(stripped[2:].strip())
                if tag:
                    tags.append(tag)
                i += 1
            metadata[key] = tags
            continue
        if key == "draft":
            metadata[key] = value.lower() == "true"
        else:
            metadata[key] = _strip_scalar(value)
        i += 1
    return metadata


def _parse_tags_value(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [tag for tag in (_strip_scalar(part.strip()) for part in inner.split(",")) if tag]
    scalar = _strip_scalar(value)
    return [scalar] if scalar else []


def _strip_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _line_to_byte(line_offsets: list[int], line: int, total_bytes: int) -> int:
    """Resolve a 0-indexed line number to its starting byte offset."""
    if line >= len(line_offsets):
        return total_bytes
    if line < 0:
        return 0
    return line_offsets[line]
