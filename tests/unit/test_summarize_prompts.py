"""Tests for cairn.summarize.prompts."""

from __future__ import annotations

import pytest

from cairn.summarize.base import SummaryLevel
from cairn.summarize.prompts import (
    SYSTEM_PROMPT,
    WORD_BUDGETS,
    enforce_word_budget,
    user_prompt,
)


class TestWordBudgets:
    def test_all_levels_have_budgets(self) -> None:
        for level in SummaryLevel:
            assert level in WORD_BUDGETS
            assert WORD_BUDGETS[level] > 0

    def test_budgets_monotonically_increase(self) -> None:
        assert WORD_BUDGETS[SummaryLevel.GIST] < WORD_BUDGETS[SummaryLevel.SYNOPSIS]
        assert WORD_BUDGETS[SummaryLevel.SYNOPSIS] < WORD_BUDGETS[SummaryLevel.DIGEST]


class TestUserPrompt:
    def test_includes_title_and_body(self) -> None:
        out = user_prompt("My Title", "Body text here.", SummaryLevel.GIST)
        assert "My Title" in out
        assert "Body text here." in out

    def test_mentions_word_budget_for_level(self) -> None:
        for level in SummaryLevel:
            out = user_prompt("t", "b", level)
            assert str(WORD_BUDGETS[level]) in out

    def test_empty_body_has_placeholder(self) -> None:
        out = user_prompt("t", "", SummaryLevel.SYNOPSIS)
        assert "empty section body" in out

    def test_system_prompt_forbids_preamble(self) -> None:
        assert "preamble" in SYSTEM_PROMPT.lower() or "This section" in SYSTEM_PROMPT


class TestEnforceWordBudget:
    def test_under_budget_returns_unchanged(self) -> None:
        text = "short text"
        out = enforce_word_budget(text, SummaryLevel.GIST)
        assert out == text

    def test_at_budget_returns_unchanged(self) -> None:
        text = " ".join(["w"] * WORD_BUDGETS[SummaryLevel.GIST])
        out = enforce_word_budget(text, SummaryLevel.GIST)
        assert out == text

    def test_over_budget_truncates_with_ellipsis(self) -> None:
        budget = WORD_BUDGETS[SummaryLevel.GIST]
        text = " ".join(["w"] * (budget + 5))
        out = enforce_word_budget(text, SummaryLevel.GIST)
        assert out.endswith("…")
        # Re-count the truncated portion (the ellipsis is attached to the last word)
        assert len(out.split()) == budget

    @pytest.mark.parametrize("level", list(SummaryLevel))
    def test_truncation_respects_level(self, level: SummaryLevel) -> None:
        text = " ".join(["w"] * 1000)
        out = enforce_word_budget(text, level)
        assert len(out.split()) == WORD_BUDGETS[level]
