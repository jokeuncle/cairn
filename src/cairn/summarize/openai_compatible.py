"""OpenAI-compatible HTTP summarizer.

Works with any endpoint that implements the OpenAI ``/v1/chat/completions``
contract: OpenAI itself, Ollama (``http://localhost:11434/v1``), vLLM,
Together, Anyscale, etc.

This is the **default** summarizer for production indexing in v0.1. It must
remain usable without proprietary credentials (point it at a local Ollama
instance) — per CLAUDE.md P4 "local-first must always work".
"""

from __future__ import annotations

from typing import Any

import httpx

from cairn.core.errors import IndexBuildError
from cairn.summarize.base import SummaryLevel
from cairn.summarize.prompts import SYSTEM_PROMPT, enforce_word_budget, user_prompt


class OpenAICompatibleSummarizer:
    """OpenAI-compatible chat-completions client."""

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

    async def summarize(
        self,
        *,
        title: str,
        body: str,
        level: SummaryLevel,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(title, body, level)},
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                msg = (
                    f"summarizer endpoint returned HTTP {response.status_code}: "
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
            text = str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            msg = "summarizer response did not match OpenAI chat-completions shape"
            raise IndexBuildError(msg, details={"response": data}) from exc

        return enforce_word_budget(text, level)
