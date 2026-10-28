"""Tests for cairn.embed.doubao.DoubaoVisionEmbedder."""

from __future__ import annotations

import asyncio
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

    def test_zero_concurrency_rejected(self) -> None:
        with pytest.raises(ValueError):
            DoubaoVisionEmbedder(concurrency=0)


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
        # Requests run concurrently, so match the response to the request body
        # rather than to arrival order — the contract is input-ordered results.
        vectors = {
            "a": [1.0, 0.0, 0.0, 0.0],
            "b": [0.0, 1.0, 0.0, 0.0],
            "c": [0.0, 0.0, 1.0, 0.0],
        }

        def _by_text(request: httpx.Request) -> httpx.Response:
            body = request.content.decode()
            for text, vector in vectors.items():
                if f'"text":"{text}"' in body:
                    return httpx.Response(200, json=_response(vector))
            return httpx.Response(400, text="unexpected text")

        route = respx.post(
            "http://test.local/api/v3/embeddings/multimodal"
        ).mock(side_effect=_by_text)

        out = await client.embed(["a", "b", "c"])

        assert out == [vectors["a"], vectors["b"], vectors["c"]]
        assert route.call_count == 3

    async def test_embed_runs_requests_concurrently(self) -> None:
        # With concurrency=3, all three requests must be in flight before any
        # response is released — proves embed() is not serial.
        client = DoubaoVisionEmbedder(
            base_url="http://test.local/api/v3",
            dim=4,
            max_retries=0,
            concurrency=3,
        )
        in_flight = 0
        peak = 0
        release = asyncio.Event()

        async def _gate(request: httpx.Request) -> httpx.Response:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await release.wait()
            in_flight -= 1
            return httpx.Response(200, json=_response([1.0, 0.0, 0.0, 0.0]))

        with respx.mock:
            respx.post(
                "http://test.local/api/v3/embeddings/multimodal"
            ).mock(side_effect=_gate)
            task = asyncio.ensure_future(client.embed(["a", "b", "c"]))
            # Let all three coroutines reach the gate, then release them.
            while peak < 3:
                await asyncio.sleep(0)
            release.set()
            out = await task

        assert peak == 3
        assert len(out) == 3

    async def test_concurrency_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            DoubaoVisionEmbedder(dim=4, concurrency=0)

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

    @respx.mock
    async def test_requests_are_concurrent_with_limit(self) -> None:
        active = 0
        max_active = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(200, json=_response([1.0, 0.0, 0.0, 0.0]))

        respx.post("http://test.local/api/v3/embeddings/multimodal").mock(
            side_effect=handler
        )
        c = DoubaoVisionEmbedder(
            base_url="http://test.local/api/v3",
            model="doubao-embedding-vision-test",
            dim=4,
            concurrency=2,
            max_retries=0,
        )

        out = await c.embed(["a", "b", "c", "d"])

        assert len(out) == 4
        assert max_active == 2


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
