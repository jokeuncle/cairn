"""Tests for CLI environment configuration."""

from __future__ import annotations

from pytest import MonkeyPatch

from cairn.cli.config import load_embed_config, load_index_config


class TestEmbedConfig:
    def test_default_embed_config_targets_ollama(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CAIRN_EMBED_PROVIDER", raising=False)
        monkeypatch.delenv("CAIRN_EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("CAIRN_EMBED_MODEL", raising=False)
        monkeypatch.delenv("CAIRN_EMBED_DIM", raising=False)
        monkeypatch.delenv("CAIRN_EMBED_API_KEY", raising=False)

        cfg = load_embed_config()

        assert cfg.provider == "openai-compatible"
        assert cfg.base_url == "http://localhost:11434/v1"
        assert cfg.model == "nomic-embed-text"
        assert cfg.dim == 768
        assert cfg.api_key is None
        assert cfg.timeout == 60.0
        assert cfg.max_retries == 2
        assert cfg.concurrency == 8

    def test_doubao_vision_defaults(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("CAIRN_EMBED_PROVIDER", "doubao-vision")
        monkeypatch.delenv("CAIRN_EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("CAIRN_EMBED_MODEL", raising=False)
        monkeypatch.delenv("CAIRN_EMBED_DIM", raising=False)
        monkeypatch.setenv("CAIRN_EMBED_API_KEY", "sk-test")

        cfg = load_embed_config()

        assert cfg.provider == "doubao-vision"
        assert cfg.base_url == "https://ark.cn-beijing.volces.com/api/v3"
        assert cfg.model == "doubao-embedding-vision-251215"
        assert cfg.dim == 2048
        assert cfg.api_key == "sk-test"
        assert cfg.timeout == 60.0
        assert cfg.max_retries == 2
        assert cfg.concurrency == 8

    def test_env_overrides_doubao_vision_defaults(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CAIRN_EMBED_PROVIDER", "doubao-vision")
        monkeypatch.setenv("CAIRN_EMBED_BASE_URL", "https://example.test/api/v3")
        monkeypatch.setenv("CAIRN_EMBED_MODEL", "custom-vision")
        monkeypatch.setenv("CAIRN_EMBED_DIM", "1024")
        monkeypatch.setenv("CAIRN_EMBED_TIMEOUT", "120.5")
        monkeypatch.setenv("CAIRN_EMBED_MAX_RETRIES", "4")
        monkeypatch.setenv("CAIRN_EMBED_CONCURRENCY", "7")

        cfg = load_embed_config()

        assert cfg.provider == "doubao-vision"
        assert cfg.base_url == "https://example.test/api/v3"
        assert cfg.model == "custom-vision"
        assert cfg.dim == 1024
        assert cfg.timeout == 120.5
        assert cfg.max_retries == 4
        assert cfg.concurrency == 7


class TestIndexConfig:
    def test_summary_batch_size_override(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("CAIRN_SUMMARY_CONCURRENCY", "6")
        monkeypatch.setenv("CAIRN_SUMMARY_BATCH_SIZE", "5")
        monkeypatch.setenv("CAIRN_EMBED_BATCH_SIZE", "17")

        cfg = load_index_config()

        assert cfg.summary_concurrency == 6
        assert cfg.summary_batch_size == 5
        assert cfg.embed_batch_size == 17
