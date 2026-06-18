"""Tests for cairn.embed.doubao.DoubaoVisionEmbedder."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from cairn.core.errors import IndexBuildError
from cairn.embed.doubao import DoubaoVisionEmbedder


@pytest.fixture
def client() -> DoubaoVisionEmbedder:
    return DoubaoVisionEmbedder(
        base_url="http://test.local/api/v3",
        model="doubao-embedding-vision-test",
        dim=4,
        api_key="sk-test",
        timeout=5.0,
        max_retries=0,
    )


def _response(vector: list[float]) -> dict[str, Any]:
    return {
        "object": "list",
        "data": {"object": "embedding", "embedding": vector},
        "model": "doubao-embedding-vision-test",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


class TestConfig:
    def test_name_includes_model(self, client: DoubaoVisionEmbedder) -> None:
        assert client.name == "doubao-vision:doubao-embedding-vision-test"

    def test_base_url_trailing_slash_stripped(self) -> None:
        c = DoubaoVisionEmbedder(base_url="http://x/api/v3/", dim=4)
        assert c.base_url == "http://x/api/v3"

    def test_zero_dim_rejected(self) -> None:
        with pytest.raises(ValueError):
            DoubaoVisionEmbedder(dim=0)

    def test_negative_retries_rejected(self) -> None:
        with pytest.raises(ValueError):
            DoubaoVisionEmbedder(max_retries=-1)


class TestHappyPath:
    async def test_empty_input_short_circuits(
        self, client: DoubaoVisionEmbedder
    ) -> None:
        with respx.mock:
            route = respx.post(
                "http://test.local/api/v3/embeddings/multimodal"
            ).mock(return_value=httpx.Response(200, json=_response([])))
            out = await client.embed([])
            assert out == []
            assert not route.called

    @respx.mock
    async def test_returns_vectors_in_input_order(
        self, client: DoubaoVisionEmbedder
    ) -> None:
        route = respx.post(
            "http://test.local/api/v3/embeddings/multimodal"
        ).mock(
            side_effect=[
                httpx.Response(200, json=_response([1.0, 0.0, 0.0, 0.0])),
                httpx.Response(200, json=_response([0.0, 1.0, 0.0, 0.0])),
            ]
        )

        out = await client.embed(["a", "b"])

        assert out == [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
        assert route.call_count == 2
        first_payload = route.calls[0].request.content.decode()
        second_payload = route.calls[1].request.content.decode()
        assert '"text":"a"' in first_payload
        assert '"text":"b"' in second_payload

    @respx.mock
    async def test_authorization_header_when_api_key_set(
        self, client: DoubaoVisionEmbedder
    ) -> None:
        route = respx.post(
            "http://test.local/api/v3/embeddings/multimodal"
        ).mock(
            return_value=httpx.Response(
                200, json=_response([1.0, 0.0, 0.0, 0.0])
            )
        )

        await client.embed(["a"])

        assert route.calls.last.request.headers["Authorization"] == "Bearer sk-test"


class TestErrors:
    @respx.mock
    async def test_http_error_raises(
        self, client: DoubaoVisionEmbedder
    ) -> None:
        respx.post("http://test.local/api/v3/embeddings/multimodal").mock(
            return_value=httpx.Response(400, text="bad model")
        )

        with pytest.raises(IndexBuildError) as exc:
            await client.embed(["a"])

        assert exc.value.details["status"] == 400
        assert exc.value.details["index"] == 0

    @respx.mock
    async def test_transport_error_raises(
        self, client: DoubaoVisionEmbedder
    ) -> None:
        respx.post("http://test.local/api/v3/embeddings/multimodal").mock(
            side_effect=httpx.ReadTimeout("slow")
        )

        with pytest.raises(IndexBuildError) as exc:
            await client.embed(["a"])

        assert exc.value.details["error_type"] == "ReadTimeout"
        assert exc.value.details["index"] == 0

    @respx.mock
    async def test_transport_error_retried_then_succeeds(self) -> None:
        c = DoubaoVisionEmbedder(
            base_url="http://test.local/api/v3",
            model="doubao-embedding-vision-test",
            dim=4,
            max_retries=1,
            retry_base_delay=0.0,
        )
        route = respx.post(
            "http://test.local/api/v3/embeddings/multimodal"
        ).mock(
            side_effect=[
                httpx.ReadTimeout("slow"),
                httpx.Response(200, json=_response([1.0, 0.0, 0.0, 0.0])),
            ]
        )

        assert await c.embed(["a"]) == [[1.0, 0.0, 0.0, 0.0]]
        assert route.call_count == 2

    @respx.mock
    async def test_malformed_response_raises(
        self, client: DoubaoVisionEmbedder
    ) -> None:
        respx.post("http://test.local/api/v3/embeddings/multimodal").mock(
            return_value=httpx.Response(200, json={"unexpected": "shape"})
        )

        with pytest.raises(IndexBuildError):
            await client.embed(["a"])

    @respx.mock
    async def test_dim_mismatch_raises(
        self, client: DoubaoVisionEmbedder
    ) -> None:
        respx.post("http://test.local/api/v3/embeddings/multimodal").mock(
            return_value=httpx.Response(200, json=_response([1.0, 0.0]))
        )

        with pytest.raises(IndexBuildError) as exc:
            await client.embed(["a"])

        assert "dim" in exc.value.message.lower()
