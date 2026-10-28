"""OpenAI-compatible HTTP embedder.

Works with any endpoint that implements the OpenAI ``/v1/embeddings``
contract: OpenAI itself, Ollama (``http://localhost:11434/v1``), vLLM,
Together, Anyscale, etc.

Default configuration points at a local Ollama instance running the
``nomic-embed-text`` model (768 dims) — chosen for the same reason as the
summarizer default: zero API keys, mature stack, runs on a laptop.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from cairn.core.errors import IndexBuildError


class OpenAICompatibleEmbedder:
    """OpenAI-compatible embeddings client."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434/v1",
        model: str = "nomic-embed-text",
        dim: int = 768,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        retry_base_delay: float = 0.5,
    ) -> None:
        if dim < 1:
            msg = f"dim must be >= 1; got {dim}"
            raise ValueError(msg)
        if max_retries < 0:
            msg = f"max_retries must be >= 0; got {max_retries}"
            raise ValueError(msg)
        if retry_base_delay < 0:
            msg = f"retry_base_delay must be >= 0; got {retry_base_delay}"
            raise ValueError(msg)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.name = f"openai-compat:{model}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._post_with_retries(client, payload, headers)
            data = response.json()

        try:
            vectors = [list(item["embedding"]) for item in data["data"]]
        except (KeyError, TypeError, IndexError) as exc:
            msg = "embedder response did not match OpenAI embeddings shape"
            raise IndexBuildError(msg, details={"response": data}) from exc

        if len(vectors) != len(texts):
            msg = (
                f"embedder returned {len(vectors)} vectors for "
                f"{len(texts)} inputs"
            )
            raise IndexBuildError(msg)
        for i, vec in enumerate(vectors):
            if len(vec) != self.dim:
                msg = (
                    f"embedder returned dim={len(vec)} but client expects "
                    f"dim={self.dim} (model {self.model!r}, index {i})"
                )
                raise IndexBuildError(msg)

        return vectors

    async def _post_with_retries(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        last_exc: httpx.HTTPError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                msg = f"embedder request failed: {exc}"
                raise IndexBuildError(
                    msg,
                    details={
                        "model": self.model,
                        "base_url": self.base_url,
                        "error_type": type(exc).__name__,
                        "attempts": attempt + 1,
                    },
                ) from exc

            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                await self._sleep_before_retry(attempt)
                continue
            if response.status_code >= 400:
                msg = (
                    f"embedder endpoint returned HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
                raise IndexBuildError(
                    msg,
                    details={
                        "status": response.status_code,
                        "model": self.model,
                        "base_url": self.base_url,
                        "attempts": attempt + 1,
                    },
                )
            return response

        msg = "embedder request failed without a response"
        raise IndexBuildError(
            msg,
            details={
                "model": self.model,
                "base_url": self.base_url,
                "error_type": type(last_exc).__name__ if last_exc else None,
            },
        )

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_base_delay == 0:
            return
        await asyncio.sleep(self.retry_base_delay * (2**attempt))
