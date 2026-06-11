"""Markdown parser — Markdown source → canonical Document AST.

Preserves heading hierarchy, generates stable hierarchical slug-based section
IDs, computes byte spans, and emits ``raw_text`` that excludes descendant
section bodies (per ARCHITECTURE.md §2.2).

Front-matter (YAML, TOML) is parsed and discarded. Content preceding the first
heading is discarded; if a document has no headings, an empty section list is
returned (callers may choose to treat this as a parse error).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

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
        sections = _build_sections(headings, text_bytes, line_offsets)

        return Document(
            id=derived_doc_id,
            source_path=source_path,
            source_hash=hashlib.sha256(text_bytes).hexdigest(),
            sections=tuple(sections),
            indexed_at=datetime.now(UTC),
            cairn_version=__version__,
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
            )
        )

    return sections


def _line_to_byte(line_offsets: list[int], line: int, total_bytes: int) -> int:
    """Resolve a 0-indexed line number to its starting byte offset."""
    if line >= len(line_offsets):
        return total_bytes
    if line < 0:
        return 0
    return line_offsets[line]
