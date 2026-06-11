"""Tests for cairn.summarize.openai_compatible.

HTTP traffic is mocked with respx — no real network.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from cairn.core.errors import IndexBuildError
from cairn.summarize.base import SummaryLevel
from cairn.summarize.openai_compatible import OpenAICompatibleSummarizer


@pytest.fixture
def client() -> OpenAICompatibleSummarizer:
    return OpenAICompatibleSummarizer(
        base_url="http://test.local/v1",
        model="test-model",
        api_key="sk-test",
        timeout=5.0,
    )


def _completion(content: str) -> dict[str, Any]:
    return {
        "id": "cmpl-x",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


class TestNameAndConfig:
    def test_name_includes_model(self, client: OpenAICompatibleSummarizer) -> None:
        assert client.name == "openai-compat:test-model"

    def test_base_url_trailing_slash_stripped(self) -> None:
        s = OpenAICompatibleSummarizer(base_url="http://x/v1/")
        assert s.base_url == "http://x/v1"


class TestHappyPath:
    @respx.mock
    async def test_returns_completion_content(
        self, client: OpenAICompatibleSummarizer
    ) -> None:
        route = respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_completion("hello world"))
        )
        out = await client.summarize(
            title="T", body="body", level=SummaryLevel.GIST
        )
        assert out == "hello world"
        assert route.called

    @respx.mock
    async def test_authorization_header_when_api_key_set(
        self, client: OpenAICompatibleSummarizer
    ) -> None:
        route = respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_completion("ok"))
        )
        await client.summarize(title="T", body="b", level=SummaryLevel.GIST)
        sent = route.calls.last.request
        assert sent.headers["Authorization"] == "Bearer sk-test"

    @respx.mock
    async def test_no_authorization_header_when_api_key_unset(self) -> None:
        s = OpenAICompatibleSummarizer(
            base_url="http://test.local/v1", model="m", api_key=None
        )
        route = respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_completion("ok"))
        )
        await s.summarize(title="T", body="b", level=SummaryLevel.GIST)
        sent = route.calls.last.request
        assert "Authorization" not in sent.headers

    @respx.mock
    async def test_output_truncated_to_word_budget(
        self, client: OpenAICompatibleSummarizer
    ) -> None:
        oversized = " ".join(["w"] * 200)
        respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_completion(oversized))
        )
        out = await client.summarize(
            title="T", body="body", level=SummaryLevel.GIST
        )
        assert out.endswith("…")


class TestErrors:
    @respx.mock
    async def test_http_error_raises_index_build_error(
        self, client: OpenAICompatibleSummarizer
    ) -> None:
        respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(IndexBuildError) as exc:
            await client.summarize(
                title="T", body="b", level=SummaryLevel.GIST
            )
        assert exc.value.details["status"] == 500

    @respx.mock
    async def test_malformed_response_raises(
        self, client: OpenAICompatibleSummarizer
    ) -> None:
        respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"unexpected": "shape"})
        )
        with pytest.raises(IndexBuildError):
            await client.summarize(
                title="T", body="b", level=SummaryLevel.GIST
            )
