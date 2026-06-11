"""CLI configuration — environment variables with Ollama defaults.

Per CLAUDE.md P4 ("local-first must always work"), the defaults target a
local Ollama instance and require no API key.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict


class LLMConfig(BaseModel):
    """Summarizer endpoint configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3.2:3b"
    api_key: str | None = None


class EmbedConfig(BaseModel):
    """Embedder endpoint configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = "http://localhost:11434/v1"
    model: str = "nomic-embed-text"
    dim: int = 768
    api_key: str | None = None


def load_llm_config() -> LLMConfig:
    """Read summarizer config from ``CAIRN_LLM_*`` environment variables."""
    return LLMConfig(
        base_url=os.environ.get("CAIRN_LLM_BASE_URL", "http://localhost:11434/v1"),
        model=os.environ.get("CAIRN_LLM_MODEL", "llama3.2:3b"),
        api_key=os.environ.get("CAIRN_LLM_API_KEY") or None,
    )


def load_embed_config() -> EmbedConfig:
    """Read embedder config from ``CAIRN_EMBED_*`` environment variables."""
    return EmbedConfig(
        base_url=os.environ.get(
            "CAIRN_EMBED_BASE_URL", "http://localhost:11434/v1"
        ),
        model=os.environ.get("CAIRN_EMBED_MODEL", "nomic-embed-text"),
        dim=int(os.environ.get("CAIRN_EMBED_DIM", "768")),
        api_key=os.environ.get("CAIRN_EMBED_API_KEY") or None,
    )
