"""Tests for cairn.bench.judge.LLMJudge.

HTTP traffic is mocked with respx — no real network.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from cairn.bench.judge import LLMJudge
from cairn.core.errors import IndexBuildError


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


@pytest.fixture
def judge() -> LLMJudge:
    return LLMJudge(
        base_url="http://test.local/v1",
        model="test-judge",
        api_key="sk-test",
        timeout=5.0,
    )


class TestAnswer:
    @respx.mock
    async def test_returns_assistant_content(self, judge: LLMJudge) -> None:
        route = respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, json=_completion("The answer is widgets.")
            )
        )
        out = await judge.answer("What is the answer?", "Context says widgets.")
        assert out == "The answer is widgets."
        assert route.called

    @respx.mock
    async def test_auth_header_when_api_key_set(self, judge: LLMJudge) -> None:
        route = respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_completion("ok"))
        )
        await judge.answer("q", "ctx")
        assert route.calls.last.request.headers["Authorization"] == "Bearer sk-test"


class TestJudge:
    @respx.mock
    async def test_yes_first_line_marks_correct(self, judge: LLMJudge) -> None:
        respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, json=_completion("YES\nIt's right.")
            )
        )
        ok, raw = await judge.judge("q", "ref", "ans")
        assert ok is True
        assert raw.startswith("YES")

    @respx.mock
    async def test_no_first_line_marks_incorrect(self, judge: LLMJudge) -> None:
        respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_completion("No, wrong."))
        )
        ok, _ = await judge.judge("q", "ref", "ans")
        assert ok is False

    @respx.mock
    async def test_case_insensitive_yes(self, judge: LLMJudge) -> None:
        respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_completion("yes that's right"))
        )
        ok, _ = await judge.judge("q", "ref", "ans")
        assert ok is True


class TestErrors:
    @respx.mock
    async def test_http_error_raises_index_build_error(
        self, judge: LLMJudge
    ) -> None:
        respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(503, text="overloaded")
        )
        with pytest.raises(IndexBuildError) as exc:
            await judge.answer("q", "ctx")
        assert exc.value.details["status"] == 503

    @respx.mock
    async def test_malformed_response_raises(self, judge: LLMJudge) -> None:
        respx.post("http://test.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"unexpected": "shape"})
        )
        with pytest.raises(IndexBuildError):
            await judge.answer("q", "ctx")
