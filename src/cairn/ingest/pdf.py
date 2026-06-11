"""PDF parser (pymupdf baseline).

Two extraction paths:

1. **Outline-based** (preferred). When the PDF carries an outline /
   bookmarks (``doc.get_toc()``), use it directly: each entry becomes a
   ``SectionNode`` with the same hierarchical slug convention as the
   Markdown parser.
2. **Heuristic fallback**. When no outline exists, look at text spans
   with their font sizes; treat blocks whose size exceeds 1.3x the
   median block size as level-1 headings (no nesting). The fallback is
   honest about its limits — for serious PDFs you'll want to add a
   table-of-contents (``pdftk update_info`` or any PDF editor) before
   indexing.

Spans use the same convention as ``MarkdownParser``: byte offsets into a
canonicalized full-document text built by concatenating per-page text
with ``\\n\\n`` separators. ``source_path`` is preserved for traceability.
"""

from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fitz
from slugify import slugify

from cairn import __version__
from cairn.core.errors import ParseError
from cairn.core.types import Document, SectionNode, Span


class PdfParser:
    """pymupdf-backed PDF parser."""

    name = "pdf"
    extensions: tuple[str, ...] = (".pdf",)

    def parse(
        self,
        source: Path | bytes | str,
        *,
        doc_id: str | None = None,
    ) -> Document:
        source_path, resolved_doc_id, doc = self._open(source, doc_id)

        try:
            pages_text, page_offsets, full_text = _extract_text(doc)
            toc = doc.get_toc(simple=False) or doc.get_toc() or []
            if toc:
                sections = _sections_from_outline(toc, pages_text, page_offsets, full_text)
            else:
                sections = _sections_from_heuristic(doc, pages_text, page_offsets, full_text)
        finally:
            doc.close()

        text_bytes = full_text.encode("utf-8")
        return Document(
            id=resolved_doc_id,
            source_path=source_path,
            source_hash=hashlib.sha256(text_bytes).hexdigest(),
            sections=tuple(sections),
            indexed_at=datetime.now(UTC),
            cairn_version=__version__,
        )

    @staticmethod
    def _open(
        source: Path | bytes | str,
        doc_id: str | None,
    ) -> tuple[Path, str, Any]:
        if isinstance(source, Path):
            try:
                doc = fitz.open(str(source))
            except Exception as exc:  # pymupdf raises a variety of errors
                msg = f"could not open PDF: {source}"
                raise ParseError(msg, details={"path": str(source)}) from exc
            resolved_id = doc_id or _slug_or_raise(source.stem, ctx="filename stem")
            return source, resolved_id, doc

        if doc_id is None:
            msg = "doc_id is required when source is not a path"
            raise ParseError(msg)

        if isinstance(source, str):
            source = source.encode("utf-8")
        try:
            doc = fitz.open(stream=source, filetype="pdf")
        except Exception as exc:
            msg = "could not open PDF from bytes"
            raise ParseError(msg) from exc
        return Path(f"<in-memory:{doc_id}>"), doc_id, doc


# ---------------------------------------------------------------------------
# Text + offsets
# ---------------------------------------------------------------------------


def _extract_text(doc: Any) -> tuple[list[str], list[int], str]:
    """Return per-page text, per-page byte offset, and the concatenated text."""
    pages: list[str] = [page.get_text("text") or "" for page in doc]
    full_text = "\n\n".join(pages)
    offsets: list[int] = []
    running = 0
    for i, page_text in enumerate(pages):
        offsets.append(running)
        running += len(page_text.encode("utf-8"))
        if i < len(pages) - 1:
            running += len(b"\n\n")
    return pages, offsets, full_text


# ---------------------------------------------------------------------------
# Outline-based section building
# ---------------------------------------------------------------------------


def _sections_from_outline(
    toc: list[Any],
    pages_text: list[str],
    page_offsets: list[int],
    full_text: str,
) -> list[SectionNode]:
    """Build sections from a PDF outline.

    ``toc`` is the output of ``doc.get_toc(simple=False)`` — each row is
    ``[level, title, page, dest_dict]`` (1-indexed page). The ``simple``
    variant drops the dest dict but is otherwise identical.
    """
    entries = _normalize_toc(toc)
    if not entries:
        return []

    n_pages = len(pages_text)
    total_bytes = len(full_text.encode("utf-8"))

    # For each entry, compute the byte offset where its page starts.
    territory_start_byte: list[int] = []
    for entry in entries:
        page = max(0, min(entry["page"] - 1, n_pages - 1))
        territory_start_byte.append(page_offsets[page])

    # Territory end: where the next entry at the same-or-shallower level begins.
    territory_end_byte: list[int] = []
    for i, entry in enumerate(entries):
        end = total_bytes
        for j in range(i + 1, len(entries)):
            if entries[j]["level"] <= entry["level"]:
                end = territory_start_byte[j]
                break
        territory_end_byte.append(end)

    # Hierarchical slug IDs + parent/child links — same convention as Markdown.
    metadata: list[tuple[str, str, int, str | None, tuple[str, ...]]] = []
    stack: list[tuple[int, str, str]] = []
    sibling_counts: dict[tuple[str, str], int] = defaultdict(int)

    for entry in entries:
        level = entry["level"]
        title = entry["title"]
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_id = stack[-1][1] if stack else None
        slug = _safe_slug(title)
        key = (parent_id or "", slug)
        sibling_counts[key] += 1
        count = sibling_counts[key]
        unique_slug = slug if count == 1 else f"{slug}-{count}"
        section_id = f"{parent_id}/{unique_slug}" if parent_id else unique_slug
        path = (*(t for _, _, t in stack), title)
        metadata.append((section_id, title, level, parent_id, path))
        stack.append((level, section_id, title))

    children_map: dict[str, list[str]] = defaultdict(list)
    for sid, _t, _l, parent_id, _p in metadata:
        if parent_id is not None:
            children_map[parent_id].append(sid)

    sections: list[SectionNode] = []
    for idx in range(len(entries)):
        section_id, title, level, parent_id, path = metadata[idx]
        span_start = territory_start_byte[idx]
        span_end = territory_end_byte[idx]
        # raw_text excludes descendant bodies: stop at the next ANY-level entry.
        raw_end = span_end
        if idx + 1 < len(entries):
            raw_end = min(raw_end, territory_start_byte[idx + 1])
        text_bytes = full_text.encode("utf-8")
        raw_text = text_bytes[span_start:raw_end].decode("utf-8", errors="replace")

        sections.append(
            SectionNode(
                id=section_id,
                title=title,
                level=min(6, max(1, level)),
                parent=parent_id,
                children=tuple(children_map.get(section_id, ())),
                span=Span(start=span_start, end=span_end),
                path=path,
                raw_text=raw_text,
            )
        )
    return sections


def _normalize_toc(toc: list[Any]) -> list[dict[str, Any]]:
    """Flatten pymupdf's TOC into ``[{level, title, page}]`` dicts."""
    out: list[dict[str, Any]] = []
    for row in toc:
        if not row or len(row) < 3:
            continue
        level = int(row[0])
        title = str(row[1]).strip()
        page = int(row[2])
        if not title:
            continue
        out.append({"level": level, "title": title, "page": page})
    return out


# ---------------------------------------------------------------------------
# Heuristic fallback (no outline)
# ---------------------------------------------------------------------------


def _sections_from_heuristic(
    doc: Any,
    pages_text: list[str],
    page_offsets: list[int],
    full_text: str,
) -> list[SectionNode]:
    """Best-effort: take blocks whose font size exceeds 1.3x median as H1.

    The fallback only emits level-1 sections. Authors with no PDF outline
    should add one before indexing serious documents.
    """
    headings: list[tuple[str, int]] = []  # (title, byte_offset)
    block_sizes: list[float] = []

    # First pass: collect typical block font sizes (median = body text).
    for page in doc:
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = float(span.get("size", 0.0))
                    if size > 0 and span.get("text", "").strip():
                        block_sizes.append(size)

    if not block_sizes:
        # Document has no extractable text. Return a single placeholder section.
        return _placeholder_section(full_text)

    median = statistics.median(block_sizes)
    threshold = median * 1.3

    # Second pass: find heading candidates and locate their byte offset.
    text_bytes = full_text.encode("utf-8")
    for page_idx, page in enumerate(doc):
        page_text = pages_text[page_idx]
        page_offset = page_offsets[page_idx]
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                max_size = max(float(s.get("size", 0.0)) for s in spans)
                if max_size < threshold:
                    continue
                title = "".join(s.get("text", "") for s in spans).strip()
                if not title or len(title) > 200:
                    continue
                offset_in_page = page_text.find(title)
                if offset_in_page < 0:
                    continue
                byte_offset = page_offset + len(
                    page_text[:offset_in_page].encode("utf-8")
                )
                headings.append((title, byte_offset))

    if not headings:
        return _placeholder_section(full_text)

    # Deduplicate by title + offset; sort by offset to enforce document order.
    seen: set[tuple[str, int]] = set()
    unique: list[tuple[str, int]] = []
    for title, offset in headings:
        if (title, offset) not in seen:
            seen.add((title, offset))
            unique.append((title, offset))
    unique.sort(key=lambda x: x[1])

    sections: list[SectionNode] = []
    sibling_counts: dict[str, int] = defaultdict(int)
    total_bytes = len(text_bytes)
    for i, (title, byte_offset) in enumerate(unique):
        slug = _safe_slug(title)
        sibling_counts[slug] += 1
        count = sibling_counts[slug]
        section_id = slug if count == 1 else f"{slug}-{count}"
        end = unique[i + 1][1] if i + 1 < len(unique) else total_bytes
        sections.append(
            SectionNode(
                id=section_id,
                title=title,
                level=1,
                parent=None,
                children=(),
                span=Span(start=byte_offset, end=end),
                path=(title,),
                raw_text=text_bytes[byte_offset:end].decode("utf-8", errors="replace"),
            )
        )
    return sections


def _placeholder_section(full_text: str) -> list[SectionNode]:
    """When extraction yields nothing useful, return a single virtual section."""
    text_bytes = full_text.encode("utf-8")
    if not text_bytes:
        return []
    return [
        SectionNode(
            id="document",
            title="Document",
            level=1,
            parent=None,
            children=(),
            span=Span(start=0, end=len(text_bytes)),
            path=("Document",),
            raw_text=full_text,
        )
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_slug(text: str) -> str:
    return slugify(text) or "section"


def _slug_or_raise(text: str, *, ctx: str) -> str:
    slug = slugify(text)
    if not slug:
        msg = f"could not derive a slug from {ctx}: {text!r}"
        raise ParseError(msg)
    return slug
