"""Tests for cairn.summarize.cache.SummaryCache."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.summarize.cache import SummaryCache


@pytest.fixture
def cache(tmp_path: Path) -> SummaryCache:
    return SummaryCache(tmp_path / "llm")


class TestCacheKey:
    def test_key_is_deterministic(self) -> None:
        a = SummaryCache.key(model="m", level="gist", section_hash="abc")
        b = SummaryCache.key(model="m", level="gist", section_hash="abc")
        assert a == b

    def test_key_changes_with_model(self) -> None:
        a = SummaryCache.key(model="m1", level="gist", section_hash="abc")
        b = SummaryCache.key(model="m2", level="gist", section_hash="abc")
        assert a != b

    def test_key_changes_with_level(self) -> None:
        a = SummaryCache.key(model="m", level="gist", section_hash="abc")
        b = SummaryCache.key(model="m", level="synopsis", section_hash="abc")
        assert a != b

    def test_key_changes_with_section_hash(self) -> None:
        a = SummaryCache.key(model="m", level="gist", section_hash="abc")
        b = SummaryCache.key(model="m", level="gist", section_hash="xyz")
        assert a != b

    def test_key_resists_field_separator_collision(self) -> None:
        # If we naively concatenated without separators, these would collide.
        a = SummaryCache.key(model="ab", level="cgist", section_hash="abc")
        b = SummaryCache.key(model="abc", level="gist", section_hash="abc")
        assert a != b


class TestCacheGetPut:
    def test_get_returns_none_for_missing(self, cache: SummaryCache) -> None:
        assert cache.get("nope") is None

    def test_put_then_get(self, cache: SummaryCache) -> None:
        cache.put("abc123", "the summary")
        assert cache.get("abc123") == "the summary"

    def test_put_overwrites(self, cache: SummaryCache) -> None:
        cache.put("abc123", "one")
        cache.put("abc123", "two")
        assert cache.get("abc123") == "two"

    def test_unicode_preserved(self, cache: SummaryCache) -> None:
        # Deliberate test of non-ASCII round-tripping; ambiguous-char checks
        # don't apply here.
        text = "概览：一段中文摘要 with mixed scripts ✓"  # noqa: RUF001
        cache.put("k", text)
        assert cache.get("k") == text


class TestCacheClear:
    def test_clear_removes_everything(self, cache: SummaryCache) -> None:
        cache.put("a", "1")
        cache.put("b", "2")
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_clear_on_empty_is_noop(self, cache: SummaryCache) -> None:
        # No file/dir created yet; clear should not raise.
        cache.clear()
