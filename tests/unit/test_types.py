"""Unit tests for cairn.core.types."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from cairn.core.types import (
    Document,
    Entity,
    Mention,
    SectionNode,
    Span,
    SummarySet,
    XRef,
)

# -- Span --------------------------------------------------------------------


class TestSpan:
    def test_constructs_valid(self) -> None:
        s = Span(start=10, end=20)
        assert s.start == 10
        assert s.end == 20
        assert len(s) == 10

    def test_zero_length_allowed(self) -> None:
        s = Span(start=5, end=5)
        assert len(s) == 0

    def test_negative_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Span(start=-1, end=10)

    def test_end_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Span(start=10, end=5)

    def test_frozen(self) -> None:
        s = Span(start=0, end=1)
        with pytest.raises(ValidationError):
            s.start = 99  # type: ignore[misc]

    @given(
        start=st.integers(min_value=0, max_value=10_000),
        delta=st.integers(min_value=0, max_value=10_000),
    )
    def test_property_any_valid_pair_accepted(self, start: int, delta: int) -> None:
        s = Span(start=start, end=start + delta)
        assert s.end >= s.start
        assert len(s) == delta


# -- SectionNode -------------------------------------------------------------


class TestSectionNode:
    def _make(self, **overrides: object) -> SectionNode:
        defaults: dict[str, object] = {
            "id": "intro",
            "title": "Introduction",
            "level": 1,
            "parent": None,
            "children": (),
            "span": Span(start=0, end=100),
            "path": ("Introduction",),
            "raw_text": "body",
        }
        defaults.update(overrides)
        return SectionNode(**defaults)  # type: ignore[arg-type]

    def test_constructs_valid(self) -> None:
        node = self._make()
        assert node.id == "intro"
        assert node.level == 1

    def test_id_rejects_leading_slash(self) -> None:
        with pytest.raises(ValidationError):
            self._make(id="/bad")

    def test_id_rejects_trailing_slash(self) -> None:
        with pytest.raises(ValidationError):
            self._make(id="bad/")

    def test_id_rejects_double_slash(self) -> None:
        with pytest.raises(ValidationError):
            self._make(id="a//b")

    def test_level_must_be_in_range(self) -> None:
        with pytest.raises(ValidationError):
            self._make(level=0)
        with pytest.raises(ValidationError):
            self._make(level=7)

    def test_frozen(self) -> None:
        node = self._make()
        with pytest.raises(ValidationError):
            node.title = "Other"  # type: ignore[misc]


# -- Composite types --------------------------------------------------------


def test_summary_set_constructs() -> None:
    s = SummarySet(
        section_id="intro",
        gist="g",
        synopsis="s",
        digest="d",
        model="test-model",
        generated_at=datetime.now(UTC),
    )
    assert s.section_id == "intro"


def test_entity_constructs() -> None:
    e = Entity(
        canonical="useEffect",
        surface_forms=("useEffect", "use_effect"),
        kind="code",
        mentions=(Mention(section_id="hooks", span=Span(start=0, end=9)),),
    )
    assert e.kind == "code"
    assert len(e.mentions) == 1


def test_xref_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        XRef(
            src="a",
            dst="b",
            kind="link",
            confidence=1.5,
            span=Span(start=0, end=1),
        )


def test_document_constructs() -> None:
    doc = Document(
        id="d",
        source_path=Path("/tmp/x.md"),
        source_hash="0" * 64,
        sections=(),
        indexed_at=datetime.now(UTC),
        cairn_version="0.0.1",
    )
    assert doc.id == "d"
    assert doc.sections == ()
