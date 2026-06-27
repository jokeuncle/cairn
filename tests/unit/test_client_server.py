"""Tests for the local Cairn web client API helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from cairn.client.server import (
    ClientHTTPServer,
    _api_root,
    _parse_bounded_int,
    client_snapshot,
    mcp_config_payload,
)
from cairn.repo import write_default_config


def test_client_snapshot_reports_repo_policy(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n\nLocal knowledge.\n", encoding="utf-8")
    write_default_config(tmp_path, enable_markitdown=True)

    payload = client_snapshot(tmp_path, fake=True)

    assert payload["repo"]["configured"] is True
    assert payload["config"]["enable_markitdown"] is True
    assert payload["status"]["counts"]["total"] == 1
    assert payload["status"]["counts"]["missing"] == 1
    assert payload["doctor"]["checks"][0]["name"] == "repo_config"


def test_client_snapshot_handles_uninitialized_repo(tmp_path: Path) -> None:
    payload = client_snapshot(tmp_path, fake=True)

    assert payload["repo"]["configured"] is False
    assert payload["config"] is None
    assert payload["status"] is None


def test_mcp_config_payload_can_bind_fixed_repo(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n\nLocal knowledge.\n", encoding="utf-8")
    write_default_config(tmp_path)

    payload = mcp_config_payload(
        tmp_path,
        client="codex",
        fake=True,
        fixed_repo=True,
    )

    assert payload["client"] == "codex"
    assert payload["args"] == ["serve", "--repo", str(tmp_path), "--fake"]
    assert "[mcp_servers.cairn]" in payload["config"]


def test_mcp_config_payload_supports_dynamic_workspace(tmp_path: Path) -> None:
    payload = mcp_config_payload(
        tmp_path,
        client="claude",
        fake=False,
        fixed_repo=False,
    )

    assert payload["args"] == ["serve"]
    assert '"mcpServers"' in payload["config"]


def test_api_root_is_scoped_to_launched_repo(tmp_path: Path) -> None:
    write_default_config(tmp_path)
    child = tmp_path / "docs"
    child.mkdir()
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    server = cast(ClientHTTPServer, SimpleNamespace(repo_root=tmp_path.resolve()))

    assert _api_root(server, {"repo": str(child)}) == tmp_path.resolve()
    with pytest.raises(ValueError, match="scoped to the repository"):
        _api_root(server, {"repo": str(outside)})


def test_parse_bounded_int_clamps_expensive_context_requests() -> None:
    assert _parse_bounded_int("200", default=5, minimum=1, maximum=8) == 8
    assert _parse_bounded_int("0", default=5, minimum=1, maximum=8) == 1
    assert _parse_bounded_int("bad", default=5, minimum=1, maximum=8) == 5
