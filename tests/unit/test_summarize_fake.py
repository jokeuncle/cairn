"""Tests for cairn.summarize.fake.FakeSummarizer."""

from __future__ import annotations

import pytest

from cairn.summarize.base import SummaryLevel
from cairn.summarize.fake import FakeSummarizer


@pytest.fixture
def fake() -> FakeSummarizer:
    return FakeSummarizer()


class TestFakeSummarizer:
    async def test_name_is_stable(self, fake: FakeSummarizer) -> None:
        assert fake.name == "fake:words"

    async def test_short_body_returned_verbatim_at_synopsis(
        self, fake: FakeSummarizer
    ) -> None:
        body = "one two three four"
        out = await fake.summarize(title="T", body=body, level=SummaryLevel.SYNOPSIS)
        assert out == body

    async def test_truncates_long_body(self, fake: FakeSummarizer) -> None:
        body = " ".join(["w"] * 100)
        out = await fake.summarize(title="T", body=body, level=SummaryLevel.GIST)
        assert out.endswith("…")
        assert len(out.split()) == FakeSummarizer._BUDGETS[SummaryLevel.GIST]

    async def test_empty_body_falls_back_to_title(self, fake: FakeSummarizer) -> None:
        out = await fake.summarize(title="Hello", body="", level=SummaryLevel.GIST)
        assert out == "Hello."

    async def test_deterministic(self, fake: FakeSummarizer) -> None:
        body = "Determinism check. " * 20
        a = await fake.summarize(title="T", body=body, level=SummaryLevel.SYNOPSIS)
        b = await fake.summarize(title="T", body=body, level=SummaryLevel.SYNOPSIS)
        assert a == b

    @pytest.mark.parametrize("level", list(SummaryLevel))
    async def test_each_level_caps_words(
        self, fake: FakeSummarizer, level: SummaryLevel
    ) -> None:
        body = " ".join(["w"] * 1000)
        out = await fake.summarize(title="T", body=body, level=level)
        word_count = len(out.replace("…", "").split())
        assert word_count <= FakeSummarizer._BUDGETS[level]
