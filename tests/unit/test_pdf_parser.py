"""Tests for cairn.ingest.pdf.PdfParser.

PDFs are generated in-memory via pymupdf so the tests are reproducible
without committing binary fixtures.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from cairn.core.errors import ConfigError, ParseError
from cairn.ingest import parser_for_path
from cairn.ingest.markdown import MarkdownParser
from cairn.ingest.pdf import PdfParser


def _write_pdf_with_outline(path: Path) -> None:
    """Create a small PDF with an explicit table of contents."""
    doc = fitz.open()
    # Three pages, each with a heading and body text.
    p1 = doc.new_page()
    p1.insert_text((50, 60), "Chapter 1: Intro", fontsize=20)
    p1.insert_text((50, 90), "Intro body talks about widgets.", fontsize=12)
    p2 = doc.new_page()
    p2.insert_text((50, 60), "Chapter 2: Setup", fontsize=20)
    p2.insert_text((50, 90), "Setup body explains the install.", fontsize=12)
    p3 = doc.new_page()
    p3.insert_text((50, 60), "2.1 Quick Start", fontsize=16)
    p3.insert_text((50, 90), "Quick start details.", fontsize=12)

    # Outline: [[level, title, page], ...] — 1-indexed pages.
    toc = [
        [1, "Chapter 1: Intro", 1],
        [1, "Chapter 2: Setup", 2],
        [2, "2.1 Quick Start", 3],
    ]
    doc.set_toc(toc)
    doc.save(str(path))
    doc.close()


def _write_pdf_no_outline(path: Path) -> None:
    """Create a PDF with no TOC but distinct heading-sized text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 60), "Big Heading One", fontsize=24)
    page.insert_text((50, 100), "Body body body body body body body.", fontsize=11)
    page.insert_text((50, 160), "Big Heading Two", fontsize=24)
    page.insert_text((50, 200), "More body content here.", fontsize=11)
    doc.save(str(path))
    doc.close()


def _write_empty_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


# -- Outline-based parsing -------------------------------------------------


class TestOutlineParsing:
    def test_extracts_outline_entries_as_sections(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "doc.pdf"
        _write_pdf_with_outline(pdf_path)

        parser = PdfParser()
        doc = parser.parse(pdf_path)
        titles = [s.title for s in doc.sections]
        assert "Chapter 1: Intro" in titles
        assert "Chapter 2: Setup" in titles
        assert "2.1 Quick Start" in titles

    def test_hierarchical_slug_ids(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "doc.pdf"
        _write_pdf_with_outline(pdf_path)

        doc = PdfParser().parse(pdf_path)
        ids = [s.id for s in doc.sections]
        assert "chapter-1-intro" in ids
        # 2.1 sits under Chapter 2: Setup at level 2.
        assert any("/2-1-quick-start" in sid for sid in ids)

    def test_parent_child_links(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "doc.pdf"
        _write_pdf_with_outline(pdf_path)

        doc = PdfParser().parse(pdf_path)
        by_id = {s.id: s for s in doc.sections}
        intro = by_id["chapter-1-intro"]
        setup = by_id["chapter-2-setup"]
        assert intro.parent is None
        assert setup.parent is None
        assert setup.children == ("chapter-2-setup/2-1-quick-start",)

    def test_raw_text_contains_body_chars(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "doc.pdf"
        _write_pdf_with_outline(pdf_path)

        doc = PdfParser().parse(pdf_path)
        by_id = {s.id: s for s in doc.sections}
        # Outline-based extraction may include the heading text itself in the
        # section's raw_text, but at minimum it should contain the body words.
        assert "widgets" in by_id["chapter-1-intro"].raw_text.lower()


# -- Heuristic fallback ----------------------------------------------------


class TestHeuristicFallback:
    def test_finds_headings_by_font_size(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "no_toc.pdf"
        _write_pdf_no_outline(pdf_path)

        doc = PdfParser().parse(pdf_path)
        titles = [s.title for s in doc.sections]
        assert any("Big Heading One" in t for t in titles)
        assert any("Big Heading Two" in t for t in titles)
        assert all(s.level == 1 for s in doc.sections)

    def test_text_only_pdf_falls_back_to_placeholder(self, tmp_path: Path) -> None:
        # A page with only body-sized text and no outline.
        pdf_path = tmp_path / "body_only.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 60), "All body, no headings.", fontsize=11)
        doc.save(str(pdf_path))
        doc.close()

        parsed = PdfParser().parse(pdf_path)
        assert len(parsed.sections) == 1
        assert parsed.sections[0].id == "document"

    def test_empty_pdf_yields_no_sections(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "empty.pdf"
        _write_empty_pdf(pdf_path)

        parsed = PdfParser().parse(pdf_path)
        assert parsed.sections == ()


# -- Sources & dispatch -----------------------------------------------------


class TestSources:
    def test_doc_id_from_filename(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "handbook.pdf"
        _write_pdf_with_outline(pdf_path)
        assert PdfParser().parse(pdf_path).id == "handbook"

    def test_doc_id_override(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "handbook.pdf"
        _write_pdf_with_outline(pdf_path)
        assert PdfParser().parse(pdf_path, doc_id="custom").id == "custom"

    def test_bytes_requires_doc_id(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "x.pdf"
        _write_pdf_with_outline(pdf_path)
        data = pdf_path.read_bytes()
        with pytest.raises(ParseError):
            PdfParser().parse(data)
        # With doc_id it works.
        out = PdfParser().parse(data, doc_id="from-bytes")
        assert out.id == "from-bytes"

    def test_missing_file_raises_parse_error(self, tmp_path: Path) -> None:
        with pytest.raises(ParseError):
            PdfParser().parse(tmp_path / "ghost.pdf")


class TestParserDispatch:
    def test_pdf_dispatch(self, tmp_path: Path) -> None:
        path = tmp_path / "x.pdf"
        path.write_bytes(b"%PDF-1.4\n%fake\n")
        assert isinstance(parser_for_path(path), PdfParser)

    def test_markdown_dispatch(self, tmp_path: Path) -> None:
        path = tmp_path / "x.md"
        assert isinstance(parser_for_path(path), MarkdownParser)

    def test_unknown_extension_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError):
            parser_for_path(tmp_path / "thing.xyz")
