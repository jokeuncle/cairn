"""Tests for cairn.embed.fake.FakeEmbedder."""

from __future__ import annotations

import math

import pytest

from cairn.embed.fake import FakeEmbedder


@pytest.fixture
def fake() -> FakeEmbedder:
    return FakeEmbedder(dim=64)


class TestConfig:
    def test_name_is_stable(self, fake: FakeEmbedder) -> None:
        assert fake.name == "fake:bow-hash"

    def test_dim_persisted(self, fake: FakeEmbedder) -> None:
        assert fake.dim == 64

    def test_zero_dim_rejected(self) -> None:
        with pytest.raises(ValueError):
            FakeEmbedder(dim=0)


class TestEmbed:
    async def test_empty_input_returns_empty(self, fake: FakeEmbedder) -> None:
        assert await fake.embed([]) == []

    async def test_each_output_has_correct_dim(self, fake: FakeEmbedder) -> None:
        vectors = await fake.embed(["hello world", "another text", ""])
        for vec in vectors:
            assert len(vec) == fake.dim

    async def test_deterministic(self, fake: FakeEmbedder) -> None:
        a = await fake.embed(["the quick brown fox"])
        b = await fake.embed(["the quick brown fox"])
        assert a == b

    async def test_distinct_texts_yield_distinct_vectors(
        self, fake: FakeEmbedder
    ) -> None:
        a, b = await fake.embed(["alpha beta", "gamma delta"])
        assert a != b

    async def test_similarity_respects_word_overlap(
        self, fake: FakeEmbedder
    ) -> None:
        # Texts that share words should be more similar than disjoint texts.
        shared, distractor, base = await fake.embed(
            ["hooks useEffect cleanup",
             "totally unrelated quantum dynamics regression",
             "hooks useEffect mount"]
        )
        sim_shared = _cosine(base, shared)
        sim_distractor = _cosine(base, distractor)
        assert sim_shared > sim_distractor

    async def test_empty_string_does_not_yield_zero_vector(
        self, fake: FakeEmbedder
    ) -> None:
        # The fallback "__empty__" token ensures a deterministic non-null vec.
        (vec,) = await fake.embed([""])
        assert any(x != 0.0 for x in vec)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
