"""Runtime provider factories shared by CLI commands and evaluation scripts."""

from __future__ import annotations

from cairn.core.config import load_embed_config, load_llm_config
from cairn.embed.base import Embedder
from cairn.embed.doubao import DoubaoVisionEmbedder
from cairn.embed.fake import FakeEmbedder
from cairn.embed.openai_compatible import OpenAICompatibleEmbedder
from cairn.summarize.base import Summarizer
from cairn.summarize.fake import FakeSummarizer
from cairn.summarize.openai_compatible import OpenAICompatibleSummarizer


def make_summarizer(use_fake: bool) -> Summarizer:
    """Build the configured summarizer without exposing any secret values."""
    if use_fake:
        return FakeSummarizer()
    cfg = load_llm_config()
    return OpenAICompatibleSummarizer(
        base_url=cfg.base_url,
        model=cfg.model,
        api_key=cfg.api_key,
        timeout=cfg.timeout,
        max_retries=cfg.max_retries,
    )


def make_embedder(use_fake: bool) -> Embedder:
    """Build the configured embedder without exposing any secret values."""
    if use_fake:
        return FakeEmbedder(dim=64)
    cfg = load_embed_config()
    if cfg.provider == "doubao-vision":
        return DoubaoVisionEmbedder(
            base_url=cfg.base_url,
            model=cfg.model,
            dim=cfg.dim,
            api_key=cfg.api_key,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
        )
    return OpenAICompatibleEmbedder(
        base_url=cfg.base_url,
        model=cfg.model,
        dim=cfg.dim,
        api_key=cfg.api_key,
        timeout=cfg.timeout,
        max_retries=cfg.max_retries,
    )
