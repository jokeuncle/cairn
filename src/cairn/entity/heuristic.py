"""HeuristicExtractor — regex-based, no model needed.

Covers two of the four ``EntityKind`` values:

- **code**: identifiers inside fenced code blocks and inline ``` `code` ```
  spans. Filters out common language keywords (Python, JS) and identifiers
  shorter than three characters.
- **defined**: text inside ``**bold**`` markdown markers that looks like a
  term (no sentence-level punctuation, ≤ 80 chars).

Span coordinates are offsets within the *section's* ``raw_text``. The
:class:`cairn.index.entities.EntityBuilder` preserves this convention end
to end.

LLM-based extraction for ``term`` and ``proper`` kinds is the v0.2.1
follow-up; this v0.2.0 extractor is fully offline.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Final

from cairn.core.types import Document, Span
from cairn.entity.base import ExtractionHit

_FENCED_CODE = re.compile(r"```[^\n]*\n(.*?)\n```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# Common stopwords that show up in code blocks but carry no entity meaning.
# Conservative: only drops obvious language keywords + built-in names.
_CODE_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        # Python keywords / builtins
        "and", "as", "assert", "async", "await", "break", "class", "continue",
        "def", "del", "elif", "else", "except", "finally", "for", "from",
        "global", "if", "import", "in", "is", "lambda", "nonlocal", "not",
        "or", "pass", "raise", "return", "try", "while", "with", "yield",
        "True", "False", "None", "self", "cls",
        "int", "str", "float", "bool", "list", "dict", "tuple", "set",
        "type", "any", "all", "len", "range", "print",
        # JS/TS keywords
        "const", "let", "var", "function", "this", "new", "throw", "void",
        "typeof", "instanceof", "switch", "case", "default", "extends",
        # Common short words that masquerade as identifiers
        "the", "that", "into",
    }
)

# Maximum length of a "defined" entity in characters.
_DEFINED_MAX_LEN: Final = 80

# Tokens that disqualify a bold span from being a defined entity.
_SENTENCE_MARKERS: Final = frozenset({".", ",", ";", ":", "!", "?"})


class HeuristicExtractor:
    """Regex-based entity extractor."""

    name = "heuristic:regex-v1"

    async def extract(self, document: Document) -> Iterable[ExtractionHit]:
        hits: list[ExtractionHit] = []
        for section in document.sections:
            for hit in _scan_section(section.id, section.raw_text):
                hits.append(hit)
        return hits


def _scan_section(section_id: str, text: str) -> Iterator[ExtractionHit]:
    yield from _scan_code(section_id, text)
    yield from _scan_defined(section_id, text)


def _scan_code(section_id: str, text: str) -> Iterator[ExtractionHit]:
    # Fenced code blocks.
    for fence in _FENCED_CODE.finditer(text):
        body = fence.group(1)
        body_offset = fence.start(1)
        for ident in _IDENTIFIER.finditer(body):
            name = ident.group()
            if name in _CODE_STOPWORDS:
                continue
            yield ExtractionHit(
                section_id=section_id,
                canonical=name,
                surface_form=name,
                kind="code",
                span=Span(
                    start=body_offset + ident.start(),
                    end=body_offset + ident.end(),
                ),
            )

    # Inline code spans. Skip those that fall inside a fenced block by
    # checking offsets against fence ranges.
    fence_ranges = [
        (m.start(), m.end()) for m in _FENCED_CODE.finditer(text)
    ]
    for inline in _INLINE_CODE.finditer(text):
        if _inside_any(inline.start(), fence_ranges):
            continue
        inner = inline.group(1)
        inner_offset = inline.start(1)
        # Only emit if the entire inline body looks like an identifier list.
        # Skip prose-y `things like this`.
        if " " in inner.strip() and len(inner.split()) > 1:
            # Multi-word inline code → typically not a single identifier.
            # Still scan for identifiers but treat them as separate hits.
            pass
        for ident in _IDENTIFIER.finditer(inner):
            name = ident.group()
            if name in _CODE_STOPWORDS:
                continue
            yield ExtractionHit(
                section_id=section_id,
                canonical=name,
                surface_form=name,
                kind="code",
                span=Span(
                    start=inner_offset + ident.start(),
                    end=inner_offset + ident.end(),
                ),
            )


def _scan_defined(section_id: str, text: str) -> Iterator[ExtractionHit]:
    for bold in _BOLD.finditer(text):
        inner_raw = bold.group(1)
        inner = inner_raw.strip()
        if not inner or len(inner) > _DEFINED_MAX_LEN:
            continue
        if any(marker in inner for marker in _SENTENCE_MARKERS):
            continue
        yield ExtractionHit(
            section_id=section_id,
            canonical=inner,
            surface_form=inner,
            kind="defined",
            span=Span(start=bold.start(1), end=bold.end(1)),
        )


def _inside_any(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in ranges)
