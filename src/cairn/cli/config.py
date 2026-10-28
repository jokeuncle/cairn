"""Backward-compatible re-export of :mod:`cairn.core.config`.

Configuration moved to ``cairn.core.config`` so non-CLI layers (e.g.
:mod:`cairn.providers`) can import it without depending on the CLI package
(CLAUDE.md P6). Import from ``cairn.core.config`` in new code.
"""

from __future__ import annotations

from cairn.core.config import (
    EmbedConfig,
    EmbedProvider,
    IndexConfig,
    LLMConfig,
    load_embed_config,
    load_index_config,
    load_llm_config,
)

__all__ = [
    "EmbedConfig",
    "EmbedProvider",
    "IndexConfig",
    "LLMConfig",
    "load_embed_config",
    "load_index_config",
    "load_llm_config",
]
