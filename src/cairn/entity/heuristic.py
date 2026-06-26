"""HeuristicExtractor — regex-based, two-pass, no model needed.

The extractor runs in two passes (see ADR-0003):

**Pass 1 — vocabulary.** Collect candidate entities from precision-gated
signals:

- **code**: identifiers inside fenced ```` ``` ```` blocks and inline `` `code` ``
  spans. Filters language keywords and identifiers shorter than three chars.
- **defined**: terms inside ``**bold**`` markers (≤ 80 chars, no sentence
  punctuation) *plus* definitional section headings — a ``title`` that reads as
  a term rather than a structural section name.
- **proper**: multi-word Title-Case sequences in prose (e.g. ``Auth Service``),
  with leading function words trimmed.

**Pass 2 — mentions.** For every section, scan its ``raw_text`` for whole-word
occurrences of each vocabulary term and emit one :class:`ExtractionHit` per
occurrence. Spans are offsets within the section's ``raw_text``; headings feed
the vocabulary but never become mentions because ``raw_text`` excludes the
heading line. This is what lets ``find_mentions`` return *every* section where a
term occurs, not just the one site that defined it.

LLM-based extraction for richer ``term``/``proper`` recall and canonicalization
is the opt-in follow-up (ROADMAP v0.2.1); this extractor stays fully offline and
deterministic so the no-API-key path keeps working (CLAUDE.md P4).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Final

from cairn.core.types import Document, EntityKind, Span
from cairn.entity.base import ExtractionHit

_FENCED_CODE = re.compile(r"```[^\n]*\n(.*?)\n```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
# A run of two or more Title-Case tokens on one line (proper-noun candidate).
_PROPER_SEQUENCE = re.compile(r"[A-Z][A-Za-z0-9]+(?:[ \t]+[A-Z][A-Za-z0-9]+)+")

# Common stopwords that show up in code blocks but carry no entity meaning.
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

# Generic structural section names that are not domain terms (lowercased).
_HEADING_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "overview", "introduction", "intro", "summary", "abstract", "scope",
        "motivation", "background", "context", "decision", "consequences",
        "alternatives considered", "open questions", "goals", "non-goals",
        "usage", "example", "examples", "getting started", "quick start",
        "installation", "configuration", "inputs", "input", "output",
        "outputs", "parameters", "returns", "semantics", "errors", "error",
        "status", "notes", "note", "see also", "references", "reference",
        "api", "changelog", "contributing", "license", "faq", "glossary",
        "steps", "verification", "prerequisites", "requirements", "results",
        "discussion", "methodology", "conclusion", "appendix", "definitions",
        "table of contents", "contents", "related", "links",
    }
)

# Lowercase connectors permitted inside a Title-Case heading/phrase.
_TITLE_CONNECTORS: Final[frozenset[str]] = frozenset(
    {"of", "the", "a", "an", "and", "or", "to", "for", "in", "on", "with", "by"}
)

# Title-Case function words trimmed from the front of a proper-noun candidate
# (typically the capitalized first word of a sentence).
_PROPER_LEADING_STOP: Final[frozenset[str]] = frozenset(
    {
        "The", "A", "An", "This", "That", "These", "Those", "It", "Its",
        "We", "You", "They", "He", "She", "If", "When", "While", "Then",
        "Per", "See", "Use", "For", "And", "But", "Or", "Nor", "So", "As",
        "At", "By", "In", "On", "Of", "To", "From", "With", "Each", "Every",
        "All", "Any", "Some", "No", "Not", "Here", "There", "Where", "Why",
        "How", "What", "Which", "Who", "Because", "Internal",
    }
)

# Maximum length of a "defined" entity in characters.
_DEFINED_MAX_LEN: Final = 80
# Maximum words in a definitional heading or proper-noun phrase.
_HEADING_MAX_WORDS: Final = 6
# Minimum length of a single-token vocabulary term.
_MIN_TERM_LEN: Final = 3
# Tokens that disqualify a bold span or heading from being a term.
_SENTENCE_MARKERS: Final = frozenset({".", ",", ";", ":", "!", "?"})

# Priority used when the same surface text is signalled by multiple rules.
_KIND_PRIORITY: Final[dict[EntityKind, int]] = {
    "code": 3,
    "defined": 2,
    "proper": 1,
    "term": 0,
}


@dataclass(frozen=True, slots=True)
class _Term:
    """One vocabulary entry: its canonical display form and match policy."""

    canonical: str
    kind: EntityKind
    case_sensitive: bool


class HeuristicExtractor:
    """Two-pass regex entity extractor (vocabulary, then mention scan)."""

    name = "heuristic:regex-v2"

    async def extract(self, document: Document) -> Iterable[ExtractionHit]:
        vocab = _build_vocabulary(document)
        if not vocab:
            return []
        matcher = _Matcher(vocab)
        hits: list[ExtractionHit] = []
        for section in document.sections:
            text = section.raw_text
            hits.extend(matcher.scan(section.id, text, _code_ranges(text)))
        return hits


# ---------------------------------------------------------------------------
# Pass 1 — vocabulary
# ---------------------------------------------------------------------------


def _build_vocabulary(document: Document) -> dict[str, _Term]:
    """Collect candidate terms, keyed by normalized match form.

    Single-token terms match case-sensitively; multi-word terms match
    case-insensitively. On a key collision the higher-priority kind wins.
    """
    vocab: dict[str, _Term] = {}
    for section in document.sections:
        text = section.raw_text
        fence_ranges = [(m.start(), m.end()) for m in _FENCED_CODE.finditer(text)]
        for name in _scan_code_terms(text, fence_ranges):
            _add_term(vocab, name, "code")
        for name in _scan_bold_terms(text):
            _add_term(vocab, name, "defined")
        for name in _scan_proper_terms(text, fence_ranges):
            _add_term(vocab, name, "proper")
        heading = _heading_term(section.title)
        if heading is not None:
            _add_term(vocab, heading, "defined")
    return vocab


def _add_term(vocab: dict[str, _Term], name: str, kind: EntityKind) -> None:
    name = name.strip()
    if not name:
        return
    multi_word = bool(re.search(r"\s", name))
    case_sensitive = not multi_word
    key = name if case_sensitive else _normalize(name)
    existing = vocab.get(key)
    if existing is not None and _KIND_PRIORITY[existing.kind] >= _KIND_PRIORITY[kind]:
        return
    vocab[key] = _Term(canonical=name, kind=kind, case_sensitive=case_sensitive)


def _scan_code_terms(text: str, fence_ranges: list[tuple[int, int]]) -> Iterator[str]:
    for fence in _FENCED_CODE.finditer(text):
        for ident in _IDENTIFIER.finditer(fence.group(1)):
            name = ident.group()
            if name not in _CODE_STOPWORDS:
                yield name
    for inline in _INLINE_CODE.finditer(text):
        if _inside_any(inline.start(), fence_ranges):
            continue
        for ident in _IDENTIFIER.finditer(inline.group(1)):
            name = ident.group()
            if name not in _CODE_STOPWORDS:
                yield name


def _scan_bold_terms(text: str) -> Iterator[str]:
    for bold in _BOLD.finditer(text):
        inner = bold.group(1).strip()
        if not inner or len(inner) > _DEFINED_MAX_LEN:
            continue
        if any(marker in inner for marker in _SENTENCE_MARKERS):
            continue
        yield inner


def _scan_proper_terms(text: str, fence_ranges: list[tuple[int, int]]) -> Iterator[str]:
    for match in _PROPER_SEQUENCE.finditer(text):
        if _inside_any(match.start(), fence_ranges):
            continue
        trimmed = _trim_leading_stopwords(match.group().split())
        if len(trimmed) < 2:
            continue
        if all(_normalize(tok) in _TITLE_CONNECTORS for tok in trimmed):
            continue
        yield " ".join(trimmed)


def _trim_leading_stopwords(tokens: list[str]) -> list[str]:
    start = 0
    while start < len(tokens) and tokens[start] in _PROPER_LEADING_STOP:
        start += 1
    return tokens[start:]


def _heading_term(title: str) -> str | None:
    term = title.strip()
    if not term:
        return None
    if any(marker in term for marker in _SENTENCE_MARKERS):
        return None
    words = term.split()
    if not 1 <= len(words) <= _HEADING_MAX_WORDS:
        return None
    if _normalize(term) in _HEADING_STOPWORDS:
        return None
    if len(words) == 1:
        word = words[0]
        if len(word) < _MIN_TERM_LEN or not word[0].isupper():
            return None
        return term
    if not all(w[0].isupper() or w.lower() in _TITLE_CONNECTORS for w in words):
        return None
    return term


# ---------------------------------------------------------------------------
# Pass 2 — mention scan
# ---------------------------------------------------------------------------


class _Matcher:
    """Compiled whole-word matcher over a document's vocabulary.

    A single case-insensitive alternation (longest surface first) finds
    non-overlapping candidates; case-sensitive terms are confirmed by an exact
    post-check so one scan serves both policies without double-counting.
    """

    def __init__(self, vocab: dict[str, _Term]) -> None:
        # Several terms can share a normalized key (e.g. code `tenant` and the
        # heading-defined `Tenant`); keep all candidates and disambiguate by
        # case policy at match time.
        self._lookup: dict[str, list[_Term]] = {}
        for term in vocab.values():
            self._lookup.setdefault(_normalize(term.canonical), []).append(term)
        surfaces = sorted(
            (term.canonical for term in vocab.values()),
            key=len,
            reverse=True,
        )
        alternation = "|".join(_phrase_pattern(s) for s in surfaces)
        self._pattern = re.compile(
            rf"(?<![A-Za-z0-9_])(?:{alternation})(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )

    def scan(
        self,
        section_id: str,
        text: str,
        code_ranges: list[tuple[int, int]],
    ) -> Iterator[ExtractionHit]:
        for match in self._pattern.finditer(text):
            matched = match.group()
            term = self._resolve(matched)
            if term is None:
                continue
            # `code` mentions are code occurrences, not prose words: a code
            # identifier (e.g. `index`) counts only where it appears inside a
            # code span, never as an English word in the surrounding prose.
            if term.kind == "code" and not _inside_any(match.start(), code_ranges):
                continue
            yield ExtractionHit(
                section_id=section_id,
                canonical=term.canonical,
                surface_form=matched,
                kind=term.kind,
                span=Span(start=match.start(), end=match.end()),
            )

    def _resolve(self, matched: str) -> _Term | None:
        """Pick the term for a matched substring by case policy.

        Prefer a case-sensitive term whose canonical matches exactly; otherwise
        fall back to a case-insensitive term sharing the normalized form.
        """
        candidates = self._lookup.get(_normalize(matched))
        if not candidates:
            return None
        fallback: _Term | None = None
        for term in candidates:
            if term.case_sensitive:
                if matched == term.canonical:
                    return term
            elif fallback is None:
                fallback = term
        return fallback


def _phrase_pattern(surface: str) -> str:
    """Escape a surface form, allowing flexible whitespace between words."""
    return r"\s+".join(re.escape(part) for part in surface.split())


def _normalize(text: str) -> str:
    """Lowercase and collapse internal whitespace for case-insensitive keys."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _code_ranges(text: str) -> list[tuple[int, int]]:
    """Inner ranges of fenced and inline code spans within ``text``."""
    fences = [(m.start(), m.end()) for m in _FENCED_CODE.finditer(text)]
    ranges = [(m.start(1), m.end(1)) for m in _FENCED_CODE.finditer(text)]
    for inline in _INLINE_CODE.finditer(text):
        if not _inside_any(inline.start(), fences):
            ranges.append((inline.start(1), inline.end(1)))
    return ranges


def _inside_any(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in ranges)
