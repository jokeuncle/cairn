"""Unit tests for cairn.ingest.markdown."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cairn.core.errors import ParseError
from cairn.ingest.markdown import MarkdownParser


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


# -- Source dispatch --------------------------------------------------------


class TestSourceDispatch:
    def test_parse_from_path(self, parser: MarkdownParser, fixture_dir: Path) -> None:
        doc = parser.parse(fixture_dir / "simple.md")
        assert doc.id == "simple"
        assert doc.source_path == fixture_dir / "simple.md"

    def test_parse_from_text_requires_doc_id(self, parser: MarkdownParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("# hi", doc_id=None)

    def test_parse_from_text_with_doc_id(self, parser: MarkdownParser) -> None:
        doc = parser.parse("# hi", doc_id="hi")
        assert doc.id == "hi"
        assert len(doc.sections) == 1

    def test_parse_from_bytes(self, parser: MarkdownParser) -> None:
        doc = parser.parse(b"# hi", doc_id="hi")
        assert len(doc.sections) == 1

    def test_source_hash_is_sha256_of_bytes(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        expected = hashlib.sha256(simple_md.encode("utf-8")).hexdigest()
        assert doc.source_hash == expected


# -- Section building -------------------------------------------------------


class TestSectionStructure:
    def test_simple_document_section_count(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        # H1 Intro + H2 Quickstart + H2 Config + H1 Reference + H2 API = 5
        assert len(doc.sections) == 5

    def test_simple_document_ids_are_hierarchical(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        ids = [s.id for s in doc.sections]
        assert ids == [
            "introduction",
            "introduction/quickstart",
            "introduction/configuration",
            "reference",
            "reference/api",
        ]

    def test_section_levels(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        levels = [s.level for s in doc.sections]
        assert levels == [1, 2, 2, 1, 2]

    def test_section_parent_child_links(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        by_id = {s.id: s for s in doc.sections}

        assert by_id["introduction"].parent is None
        assert by_id["introduction"].children == (
            "introduction/quickstart",
            "introduction/configuration",
        )
        assert by_id["introduction/quickstart"].parent == "introduction"
        assert by_id["introduction/quickstart"].children == ()

        assert by_id["reference"].parent is None
        assert by_id["reference"].children == ("reference/api",)

    def test_section_paths_are_title_breadcrumbs(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        by_id = {s.id: s for s in doc.sections}
        assert by_id["introduction"].path == ("Introduction",)
        assert by_id["introduction/quickstart"].path == (
            "Introduction",
            "Quickstart",
        )
        assert by_id["reference/api"].path == ("Reference", "API")


# -- Slug disambiguation ----------------------------------------------------


class TestSlugDisambiguation:
    def test_duplicate_sibling_titles_get_suffixed(
        self, parser: MarkdownParser, nested_md: str
    ) -> None:
        doc = parser.parse(nested_md, doc_id="nested")
        ids = [s.id for s in doc.sections]
        # Two "Examples" under "Top" → second one gets -2
        assert "top/examples" in ids
        assert "top/examples-2" in ids
        # The "Examples" under "Other" is unique within its parent
        assert "other/examples" in ids
        # Even though "examples" exists under "Top", "Other"'s child is a
        # different sibling group and is NOT suffixed.

    def test_deeper_section_under_disambiguated_parent(
        self, parser: MarkdownParser, nested_md: str
    ) -> None:
        doc = parser.parse(nested_md, doc_id="nested")
        ids = {s.id for s in doc.sections}
        assert "top/examples-2/deep" in ids


# -- Raw text & spans -------------------------------------------------------


class TestRawTextAndSpans:
    def test_raw_text_excludes_child_section_bodies(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        by_id = {s.id: s for s in doc.sections}
        intro_body = by_id["introduction"].raw_text
        assert "This is the intro body" in intro_body
        # The body of the Quickstart child must not leak into Intro's raw_text.
        assert "Install with pip" not in intro_body

    def test_raw_text_of_leaf_section(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        by_id = {s.id: s for s in doc.sections}
        api_text = by_id["reference/api"].raw_text
        assert "All public functions" in api_text

    def test_span_covers_section_territory_including_descendants(
        self, parser: MarkdownParser, simple_md: str
    ) -> None:
        doc = parser.parse(simple_md, doc_id="simple")
        by_id = {s.id: s for s in doc.sections}
        intro = by_id["introduction"]
        quickstart = by_id["introduction/quickstart"]
        config = by_id["introduction/configuration"]
        # Intro's span must contain its children's spans entirely.
        assert intro.span.start <= quickstart.span.start
        assert intro.span.end >= config.span.end


# -- Edge cases -------------------------------------------------------------


class TestEdgeCases:
    def test_empty_document(self, parser: MarkdownParser, empty_md: str) -> None:
        doc = parser.parse(empty_md, doc_id="empty")
        assert doc.sections == ()

    def test_no_headings_yields_no_sections(
        self, parser: MarkdownParser, no_headings_md: str
    ) -> None:
        doc = parser.parse(no_headings_md, doc_id="prose")
        assert doc.sections == ()

    def test_front_matter_is_skipped(
        self, parser: MarkdownParser, with_frontmatter_md: str
    ) -> None:
        doc = parser.parse(with_frontmatter_md, doc_id="fm")
        assert len(doc.sections) == 1
        assert doc.sections[0].title == "After Front Matter"

    def test_inline_markup_stripped_from_title(self, parser: MarkdownParser) -> None:
        text = "# **Bold** and *italic* `code`\n\nBody."
        doc = parser.parse(text, doc_id="t")
        assert doc.sections[0].title == "Bold and italic code"
