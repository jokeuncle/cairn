"""Tests for cairn.bench.metrics."""

from __future__ import annotations

import pytest

from cairn.bench.metrics import recall_at_k


class TestRecallAtK:
    def test_empty_expected_is_vacuously_one(self) -> None:
        assert recall_at_k(["any"], expected_anchors=[], k=8) == 1.0

    def test_full_match(self) -> None:
        retrieved = ["a/b", "c/d"]
        assert recall_at_k(retrieved, expected_anchors=["a/b"], k=8) == 1.0

    def test_no_match(self) -> None:
        retrieved = ["a/b", "c/d"]
        assert recall_at_k(retrieved, expected_anchors=["z/y"], k=8) == 0.0

    def test_partial_match(self) -> None:
        retrieved = ["a/b", "c/d"]
        result = recall_at_k(
            retrieved, expected_anchors=["a/b", "missing"], k=8
        )
        assert result == 0.5

    def test_substring_match(self) -> None:
        retrieved = ["doc/section/2-5-vectors"]
        result = recall_at_k(
            retrieved, expected_anchors=["2-5-vectors"], k=8
        )
        assert result == 1.0

    def test_k_truncation_drops_match(self) -> None:
        retrieved = ["miss-a", "miss-b", "target"]
        result = recall_at_k(retrieved, expected_anchors=["target"], k=2)
        assert result == 0.0

    @pytest.mark.parametrize("k", [0, -1])
    def test_k_zero_or_negative_returns_zero_for_any_expected(self, k: int) -> None:
        # k<=0 means top-k is empty → no matches possible (when expected is non-empty)
        assert recall_at_k(["target"], expected_anchors=["target"], k=k) == 0.0
