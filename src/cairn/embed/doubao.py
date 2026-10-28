"""Volcengine/Doubao embedding adapters."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from cairn.core.errors import IndexBuildError


class DoubaoVisionEmbedder:
    """Client for Doubao's multimodal embedding endpoint.

    ``doubao-embedding-vision-*`` models do not use the OpenAI-compatible
    ``/embeddings`` wire shape. They are served at
    ``/embeddings/multimodal`` and return ``{"data": {"embedding": ...}}``
    for a single multimodal input. Cairn's embedder protocol expects one
    vector per text, so this adapter issues one request per input text and
    runs up to ``concurrency`` of them in flight at once (order preserved).
    """

    def __init__(
        self,
        *,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "doubao-embedding-vision-251215",
        dim: int = 2048,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        retry_base_delay: float = 0.5,
        concurrency: int = 8,
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
        if concurrency < 1:
            msg = f"concurrency must be >= 1; got {concurrency}"
            raise ValueError(msg)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.concurrency = concurrency
        self.name = f"doubao-vision:{model}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed each text through Doubao's multimodal vectorization API.

        Requests run concurrently (bounded by ``concurrency``); results are
        returned in input order regardless of completion order.
        """
        if not texts:
            return []

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        semaphore = asyncio.Semaphore(self.concurrency)

        async with httpx.AsyncClient(timeout=self.timeout) as client:

            async def embed_one(index: int, text: str) -> list[float]:
                payload: dict[str, Any] = {
                    "model": self.model,
                    "input": [{"type": "text", "text": text}],
                }
                async with semaphore:
                    response = await self._post_with_retries(
                        client, payload, headers, index=index
                    )
                vector = _extract_vector(response.json(), index=index)
                if len(vector) != self.dim:
                    msg = (
                        f"doubao vision embedder returned dim={len(vector)} "
                        f"but client expects dim={self.dim} "
                        f"(model {self.model!r}, index {index})"
                    )
                    raise IndexBuildError(msg)
                return vector

            tasks = [
                asyncio.ensure_future(embed_one(index, text))
                for index, text in enumerate(texts)
            ]
            try:
                vectors: list[list[float]] = await asyncio.gather(*tasks)
            except BaseException:
                # Cancel siblings still in flight before the AsyncClient closes.
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            return vectors

    async def _post_with_retries(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        headers: dict[str, str],
        *,
        index: int,
    ) -> httpx.Response:
        last_exc: httpx.HTTPError | None = None
        url = f"{self.base_url}/embeddings/multimodal"
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                msg = f"doubao vision embedder request failed: {exc}"
                raise IndexBuildError(
                    msg,
                    details={
                        "model": self.model,
                        "base_url": self.base_url,
                        "index": index,
                        "error_type": type(exc).__name__,
                        "attempts": attempt + 1,
                    },
                ) from exc

            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                await self._sleep_before_retry(attempt)
                continue
            if response.status_code >= 400:
                msg = (
                    f"doubao vision embedder endpoint returned HTTP "
                    f"{response.status_code}: {response.text[:200]}"
                )
                raise IndexBuildError(
                    msg,
                    details={
                        "status": response.status_code,
                        "model": self.model,
                        "base_url": self.base_url,
                        "index": index,
                        "attempts": attempt + 1,
                    },
                )
            return response

        msg = "doubao vision embedder request failed without a response"
        raise IndexBuildError(
            msg,
            details={
                "model": self.model,
                "base_url": self.base_url,
                "index": index,
                "error_type": type(last_exc).__name__ if last_exc else None,
            },
        )

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_base_delay == 0:
            return
        await asyncio.sleep(self.retry_base_delay * (2**attempt))


def _extract_vector(data: dict[str, Any], *, index: int) -> list[float]:
    """Read the dense vector from Doubao's multimodal response shape."""
    try:
        embedding = data["data"]["embedding"]
    except (KeyError, TypeError) as exc:
        msg = "doubao vision embedder response did not match expected shape"
        raise IndexBuildError(msg, details={"response": data, "index": index}) from exc

    if not isinstance(embedding, list):
        msg = "doubao vision embedder embedding is not a list"
        raise IndexBuildError(msg, details={"response": data, "index": index})

    try:
        return [float(value) for value in embedding]
    except (TypeError, ValueError) as exc:
        msg = "doubao vision embedder embedding contains non-numeric values"
        raise IndexBuildError(msg, details={"response": data, "index": index}) from exc
