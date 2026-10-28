"""Runtime provider factories shared by CLI commands and evaluation scripts."""

from __future__ import annotations

from cairn.core.config import load_embed_config, load_llm_config
from cairn.embed.base import Embedder
from cairn.embed.doubao import DoubaoVisionEmbedder
from cairn.embed.fake import FakeEmbedder
from cairn.embed.openai_compatible import OpenAICompatibleEmbedder
from cairn.embed.task_prefix import TaskPrefixEmbedder
from cairn.embed.windowed import WindowedEmbedder
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
    embedder: Embedder
    if cfg.provider == "doubao-vision":
        embedder = DoubaoVisionEmbedder(
            base_url=cfg.base_url,
            model=cfg.model,
            dim=cfg.dim,
            api_key=cfg.api_key,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
            concurrency=cfg.concurrency,
        )
    else:
        embedder = OpenAICompatibleEmbedder(
            base_url=cfg.base_url,
            model=cfg.model,
            dim=cfg.dim,
            api_key=cfg.api_key,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
        )
    if cfg.document_prefix or cfg.query_prefix:
        embedder = TaskPrefixEmbedder(
            embedder, document_prefix=cfg.document_prefix, query_prefix=cfg.query_prefix
        )
    if cfg.provider == "windowed-openai-compatible":
        return WindowedEmbedder(embedder)
    return embedder
