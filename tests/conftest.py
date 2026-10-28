"""Shared pytest fixtures for the Cairn test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture
def simple_md() -> str:
    return (FIXTURE_DIR / "simple.md").read_text(encoding="utf-8")


@pytest.fixture
def nested_md() -> str:
    return (FIXTURE_DIR / "nested.md").read_text(encoding="utf-8")


@pytest.fixture
def empty_md() -> str:
    return (FIXTURE_DIR / "empty.md").read_text(encoding="utf-8")


@pytest.fixture
def no_headings_md() -> str:
    return (FIXTURE_DIR / "no_headings.md").read_text(encoding="utf-8")


@pytest.fixture
def with_frontmatter_md() -> str:
    return (FIXTURE_DIR / "with_frontmatter.md").read_text(encoding="utf-8")
