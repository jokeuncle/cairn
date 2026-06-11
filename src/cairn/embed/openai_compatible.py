"""OpenAI-compatible HTTP embedder.

Works with any endpoint that implements the OpenAI ``/v1/embeddings``
contract: OpenAI itself, Ollama (``http://localhost:11434/v1``), vLLM,
Together, Anyscale, etc.

Default configuration points at a local Ollama instance running the
``nomic-embed-text`` model (768 dims) — chosen for the same reason as the
summarizer default: zero API keys, mature stack, runs on a laptop.
"""

from __future__ import annotations

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
    ) -> None:
        if dim < 1:
            msg = f"dim must be >= 1; got {dim}"
            raise ValueError(msg)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self.api_key = api_key
        self.timeout = timeout
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
            response = await client.post(
                f"{self.base_url}/embeddings",
                json=payload,
                headers=headers,
            )
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
                    },
                )
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
