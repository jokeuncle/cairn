"""CLI configuration — environment variables with Ollama defaults.

Per CLAUDE.md P4 ("local-first must always work"), the defaults target a
local Ollama instance and require no API key.
"""

from __future__ import annotations

import os
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

EmbedProvider = Literal["openai-compatible", "doubao-vision"]


class LLMConfig(BaseModel):
    """Summarizer endpoint configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3.2:3b"
    api_key: str | None = None
    timeout: float = 60.0
    max_retries: int = 2


class EmbedConfig(BaseModel):
    """Embedder endpoint configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: EmbedProvider = "openai-compatible"
    base_url: str = "http://localhost:11434/v1"
    model: str = "nomic-embed-text"
    dim: int = 768
    api_key: str | None = None
    timeout: float = 60.0
    max_retries: int = 2


class IndexConfig(BaseModel):
    """Index-build performance knobs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary_concurrency: int = 4
    embed_batch_size: int = 32


def load_llm_config() -> LLMConfig:
    """Read summarizer config from ``CAIRN_LLM_*`` environment variables."""
    return LLMConfig(
        base_url=os.environ.get("CAIRN_LLM_BASE_URL", "http://localhost:11434/v1"),
        model=os.environ.get("CAIRN_LLM_MODEL", "llama3.2:3b"),
        api_key=os.environ.get("CAIRN_LLM_API_KEY") or None,
        timeout=_float_env("CAIRN_LLM_TIMEOUT", 60.0),
        max_retries=_int_env("CAIRN_LLM_MAX_RETRIES", 2),
    )


def load_embed_config() -> EmbedConfig:
    """Read embedder config from ``CAIRN_EMBED_*`` environment variables."""
    provider = os.environ.get("CAIRN_EMBED_PROVIDER", "openai-compatible")
    if provider == "doubao-vision":
        default_base_url = "https://ark.cn-beijing.volces.com/api/v3"
        default_model = "doubao-embedding-vision-251215"
        default_dim = "2048"
    else:
        default_base_url = "http://localhost:11434/v1"
        default_model = "nomic-embed-text"
        default_dim = "768"

    return EmbedConfig(
        provider=cast(EmbedProvider, provider),
        base_url=os.environ.get("CAIRN_EMBED_BASE_URL", default_base_url),
        model=os.environ.get("CAIRN_EMBED_MODEL", default_model),
        dim=int(os.environ.get("CAIRN_EMBED_DIM", default_dim)),
        api_key=os.environ.get("CAIRN_EMBED_API_KEY") or None,
        timeout=_float_env("CAIRN_EMBED_TIMEOUT", 60.0),
        max_retries=_int_env("CAIRN_EMBED_MAX_RETRIES", 2),
    )


def load_index_config() -> IndexConfig:
    """Read index-build performance config from environment variables."""
    return IndexConfig(
        summary_concurrency=_int_env("CAIRN_SUMMARY_CONCURRENCY", 4),
        embed_batch_size=_int_env("CAIRN_EMBED_BATCH_SIZE", 32),
    )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)
