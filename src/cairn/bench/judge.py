"""LLM-as-judge: optional QA accuracy dimension for cairn-bench.

For each question + retrieved context the judge:

1. Asks an LLM to answer the question using only the provided context.
2. Asks the same LLM to evaluate whether that answer matches the
   reference answer the suite author supplied.

Both calls go through an OpenAI-compatible ``/v1/chat/completions``
endpoint, so the judge runs against Ollama (default), OpenAI, vLLM, etc.

The judge is **optional**: when no ``LLMJudge`` is configured on the
:class:`cairn.bench.runner.BenchRunner`, QA accuracy is simply not
reported. Recall and token cost still come out either way.
"""

from __future__ import annotations

from typing import Any

import httpx

from cairn.core.errors import IndexBuildError

_ANSWER_SYSTEM = (
    "You answer questions strictly from the provided context. "
    'If the context is insufficient, reply with "I don\'t know."'
)

_JUDGE_SYSTEM = (
    "You evaluate whether an AI assistant's answer is correct given a "
    "reference answer. Reply with YES or NO on the first line, then one "
    "sentence of justification."
)


class LLMJudge:
    """Generates answers from retrieved context and judges them against a reference."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3.2:3b",
        api_key: str | None = None,
        timeout: float = 60.0,
        temperature: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.name = f"openai-compat:{model}"

    async def answer(self, question: str, context: str) -> str:
        """Produce an answer to ``question`` using only ``context``."""
        prompt = (
            "Context:\n"
            f"{context.strip() or '(no context provided)'}\n\n"
            f"Question: {question}\n\nAnswer:"
        )
        return await self._chat(
            [
                {"role": "system", "content": _ANSWER_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )

    async def judge(
        self,
        question: str,
        reference: str,
        answer: str,
    ) -> tuple[bool, str]:
        """Return ``(is_correct, raw_response)`` for one (question, answer) pair."""
        prompt = (
            f"Question: {question}\n\n"
            f"Reference answer: {reference}\n\n"
            f"Assistant's answer: {answer}\n\n"
            "Is the assistant's answer correct?"
        )
        raw = await self._chat(
            [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )
        first_line = raw.strip().split("\n", 1)[0].strip().upper()
        is_correct = first_line.startswith("YES")
        return is_correct, raw

    async def _chat(self, messages: list[dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": messages,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                msg = (
                    f"judge endpoint returned HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
                raise IndexBuildError(
                    msg,
                    details={
                        "status": response.status_code,
                        "model": self.model,
                        "base_url": self.base_url,
                    },
                )
            data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            msg = "judge response did not match OpenAI chat-completions shape"
            raise IndexBuildError(msg, details={"response": data}) from exc
