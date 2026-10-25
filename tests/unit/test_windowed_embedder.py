"""Overflow handling must preserve text, ordering and short-input semantics."""

from math import hypot

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pytest import MonkeyPatch

from cairn.core.errors import IndexBuildError
from cairn.embed.windowed import WindowedEmbedder, utf8_windows
from cairn.providers import make_embedder


class RecordingEmbedder:
    name = "recording:model"
    dim = 2

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.0, 2.0] if "TAIL" in text else [3.0, 0.0] for text in texts]


@given(st.text(), st.integers(min_value=4, max_value=256))
def test_utf8_windows_roundtrip_and_bound(text: str, budget: int) -> None:
    windows = utf8_windows(text, budget)
    assert "".join(windows) == text
    assert all(len(window.encode("utf-8")) <= budget for window in windows)


async def test_pool_includes_tail_and_preserves_order_and_short_inputs() -> None:
    delegate = RecordingEmbedder()
    embedder = WindowedEmbedder(delegate, max_input_bytes=8, batch_size=2)
    result = await embedder.embed(["short", "A" * 16 + "TAIL", ""])
    assert result[0] == result[2] == [3.0, 0.0]
    assert result[1][0] > 0 and result[1][1] > 0
    assert hypot(*result[1]) == pytest.approx(1)
    assert all(len(batch) <= 2 for batch in delegate.calls)
    assert (
        "".join(text for batch in delegate.calls for text in batch) == "short" + "A" * 16 + "TAIL"
    )
    before = len(delegate.calls)
    assert await embedder.embed([]) == []
    assert len(delegate.calls) == before
    assert embedder.name != WindowedEmbedder(delegate, max_input_bytes=16).name


async def test_invalid_provider_output_is_rejected() -> None:
    class Broken(RecordingEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[float("nan"), 1.0] for _ in texts]

    with pytest.raises(IndexBuildError, match="invalid vector"):
        await WindowedEmbedder(Broken()).embed(["text"])
    with pytest.raises(ValueError):
        WindowedEmbedder(RecordingEmbedder(), max_input_bytes=3)


def test_windowed_provider_is_explicit_and_default_is_unchanged(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("CAIRN_EMBED_PROVIDER", "windowed-openai-compatible")
    assert isinstance(make_embedder(False), WindowedEmbedder)
    monkeypatch.setenv("CAIRN_EMBED_PROVIDER", "openai-compatible")
    assert not isinstance(make_embedder(False), WindowedEmbedder)
