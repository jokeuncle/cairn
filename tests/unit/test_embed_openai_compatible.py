"""Tests for cairn.embed.openai_compatible.OpenAICompatibleEmbedder."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from cairn.core.errors import IndexBuildError
from cairn.embed.openai_compatible import OpenAICompatibleEmbedder


@pytest.fixture
def client() -> OpenAICompatibleEmbedder:
    return OpenAICompatibleEmbedder(
        base_url="http://test.local/v1",
        model="test-embed",
        dim=4,
        api_key="sk-test",
        timeout=5.0,
        max_retries=0,
    )


def _response(vectors: list[list[float]]) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": v}
            for i, v in enumerate(vectors)
        ],
        "model": "test-embed",
    }


class TestConfig:
    def test_name_includes_model(self, client: OpenAICompatibleEmbedder) -> None:
        assert client.name == "openai-compat:test-embed"

    def test_base_url_trailing_slash_stripped(self) -> None:
        c = OpenAICompatibleEmbedder(base_url="http://x/v1/", dim=4)
        assert c.base_url == "http://x/v1"

    def test_zero_dim_rejected(self) -> None:
        with pytest.raises(ValueError):
            OpenAICompatibleEmbedder(dim=0)

    def test_negative_retries_rejected(self) -> None:
        with pytest.raises(ValueError):
            OpenAICompatibleEmbedder(max_retries=-1)


class TestHappyPath:
    async def test_empty_input_short_circuits(
        self, client: OpenAICompatibleEmbedder
    ) -> None:
        with respx.mock:
            route = respx.post("http://test.local/v1/embeddings").mock(
                return_value=httpx.Response(200, json=_response([]))
            )
            out = await client.embed([])
            assert out == []
            assert not route.called  # no HTTP call when input is empty

    @respx.mock
    async def test_returns_vectors_in_order(
        self, client: OpenAICompatibleEmbedder
    ) -> None:
        respx.post("http://test.local/v1/embeddings").mock(
            return_value=httpx.Response(
                200,
                json=_response([[1.0, 0, 0, 0], [0, 1.0, 0, 0]]),
            )
        )
        out = await client.embed(["a", "b"])
        assert out == [[1.0, 0, 0, 0], [0, 1.0, 0, 0]]

    @respx.mock
    async def test_authorization_header_when_api_key_set(
        self, client: OpenAICompatibleEmbedder
    ) -> None:
        route = respx.post("http://test.local/v1/embeddings").mock(
            return_value=httpx.Response(200, json=_response([[1.0, 0, 0, 0]]))
        )
        await client.embed(["a"])
        assert route.calls.last.request.headers["Authorization"] == "Bearer sk-test"


class TestErrors:
    @respx.mock
    async def test_http_error_raises(
        self, client: OpenAICompatibleEmbedder
    ) -> None:
        respx.post("http://test.local/v1/embeddings").mock(
            return_value=httpx.Response(503, text="overloaded")
        )
        with pytest.raises(IndexBuildError) as exc:
            await client.embed(["a"])
        assert exc.value.details["status"] == 503

    @respx.mock
    async def test_transport_error_raises(
        self, client: OpenAICompatibleEmbedder
    ) -> None:
        respx.post("http://test.local/v1/embeddings").mock(
            side_effect=httpx.ReadTimeout("slow")
        )
        with pytest.raises(IndexBuildError) as exc:
            await client.embed(["a"])
        assert exc.value.details["error_type"] == "ReadTimeout"

    @respx.mock
    async def test_transport_error_retried_then_succeeds(self) -> None:
        c = OpenAICompatibleEmbedder(
            base_url="http://test.local/v1",
            model="test-embed",
            dim=4,
            max_retries=1,
            retry_base_delay=0.0,
        )
        route = respx.post("http://test.local/v1/embeddings").mock(
            side_effect=[
                httpx.ReadTimeout("slow"),
                httpx.Response(200, json=_response([[1.0, 0, 0, 0]])),
            ]
        )
        assert await c.embed(["a"]) == [[1.0, 0, 0, 0]]
        assert route.call_count == 2

    @respx.mock
    async def test_malformed_response_raises(
        self, client: OpenAICompatibleEmbedder
    ) -> None:
        respx.post("http://test.local/v1/embeddings").mock(
            return_value=httpx.Response(200, json={"unexpected": "shape"})
        )
        with pytest.raises(IndexBuildError):
            await client.embed(["a"])

    @respx.mock
    async def test_count_mismatch_raises(
        self, client: OpenAICompatibleEmbedder
    ) -> None:
        # Two inputs, one embedding → error.
        respx.post("http://test.local/v1/embeddings").mock(
            return_value=httpx.Response(
                200, json=_response([[1.0, 0, 0, 0]])
            )
        )
        with pytest.raises(IndexBuildError):
            await client.embed(["a", "b"])

    @respx.mock
    async def test_dim_mismatch_raises(
        self, client: OpenAICompatibleEmbedder
    ) -> None:
        # Client declares dim=4 but response has dim=2.
        respx.post("http://test.local/v1/embeddings").mock(
            return_value=httpx.Response(200, json=_response([[1.0, 0]]))
        )
        with pytest.raises(IndexBuildError) as exc:
            await client.embed(["a"])
        assert "dim" in exc.value.message.lower()
