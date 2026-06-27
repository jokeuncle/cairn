"""Local HTTP client for operating Cairn repository knowledge indexes."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import BaseServer
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from cairn import __version__
from cairn.cli.app import (
    McpClient,
    _default_mcp_config_path,
    _format_mcp_config,
    _mcp_server_args,
    _write_mcp_config,
)
from cairn.cli.config import load_embed_config, load_index_config, load_llm_config
from cairn.core.errors import CairnError
from cairn.providers import make_embedder, make_summarizer
from cairn.repo import (
    RepoStatus,
    config_path,
    find_repo_root,
    load_repo_config,
    repo_context,
    repo_graph,
    repo_status,
    sync_repo,
    write_default_config,
)

STATIC_DIR = Path(__file__).with_name("static")
CLIENTS: tuple[McpClient, ...] = ("codex", "claude", "cursor", "goose")


class ClientHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying Cairn client runtime settings."""

    repo_root: Path
    use_fake: bool

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        repo_root: Path,
        use_fake: bool,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.repo_root = repo_root
        self.use_fake = use_fake


def serve_client(
    *,
    repo: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    fake: bool = True,
    open_browser: bool = True,
) -> None:
    """Serve the local Cairn web client until interrupted."""
    root = _resolve_start_root(repo)
    server = ClientHTTPServer(
        (host, port),
        ClientRequestHandler,
        repo_root=root,
        use_fake=fake,
    )
    bound_host = str(server.server_address[0])
    bound_port = int(server.server_address[1])
    url = f"http://{bound_host}:{bound_port}/"
    print(f"Cairn client: {url}")
    print(f"repository: {root}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCairn client stopped.")
    finally:
        server.server_close()


def _resolve_start_root(repo: Path | None) -> Path:
    start = (repo or Path.cwd()).expanduser().resolve()
    try:
        return find_repo_root(start)
    except Exception:
        return start


def client_snapshot(root: Path, *, fake: bool) -> dict[str, Any]:
    """Return the current repository state for the local client."""
    cfg_path = config_path(root)
    configured = cfg_path.exists()
    payload: dict[str, Any] = {
        "version": __version__,
        "repo": {
            "root": str(root),
            "configured": configured,
            "config_path": str(cfg_path),
        },
        "config": None,
        "status": None,
        "doctor": _doctor_payload(root, fake=fake, status_obj=None),
        "publish": _publish_payload(root, fake=fake, fixed_repo=configured),
    }
    if not configured:
        return payload

    cfg = load_repo_config(root)
    status_obj = repo_status(root, config=cfg)
    payload["config"] = {
        "documents_dir": cfg.documents_dir,
        "include": list(cfg.include),
        "exclude": list(cfg.exclude),
        "primary_doc": cfg.primary_doc,
        "enable_markitdown": cfg.enable_markitdown,
        "search_sections_per_doc": cfg.search_sections_per_doc,
        "preferred_locales": list(cfg.preferred_locales),
    }
    payload["status"] = _status_payload(status_obj)
    payload["doctor"] = _doctor_payload(root, fake=fake, status_obj=status_obj)
    return payload


def mcp_config_payload(
    root: Path,
    *,
    client: McpClient,
    fake: bool,
    fixed_repo: bool,
    command: str = "docsgraph",
) -> dict[str, Any]:
    """Return an MCP config preview for a target AI client."""
    args = _mcp_server_args(repo=root if fixed_repo else None)
    if fake:
        args.append("--fake")
    target = _default_mcp_config_path(client)
    return {
        "client": client,
        "target": str(target),
        "command": command,
        "args": args,
        "fixed_repo": fixed_repo,
        "config": _format_mcp_config(client, command=command, args=args),
    }


def _publish_payload(root: Path, *, fake: bool, fixed_repo: bool) -> dict[str, Any]:
    return {
        "clients": [
            mcp_config_payload(root, client=client, fake=fake, fixed_repo=fixed_repo)
            for client in CLIENTS
        ]
    }


def _status_payload(status_obj: RepoStatus) -> dict[str, Any]:
    docs = [doc.model_dump(mode="json") for doc in status_obj.documents]
    total = len(status_obj.documents)
    freshness = 100 if total == 0 else round((status_obj.indexed_count / total) * 100)
    readiness = max(
        0,
        min(
            100,
            freshness
            - status_obj.stale_count * 8
            - status_obj.missing_count * 12
            - status_obj.error_count * 18,
        ),
    )
    return {
        "root": str(status_obj.root),
        "primary_doc": status_obj.primary_doc,
        "documents": docs,
        "counts": {
            "total": total,
            "indexed": status_obj.indexed_count,
            "stale": status_obj.stale_count,
            "missing": status_obj.missing_count,
            "errors": status_obj.error_count,
            "orphaned": sum(1 for doc in status_obj.documents if doc.state == "orphaned"),
        },
        "readiness": readiness,
    }


def _doctor_payload(
    root: Path,
    *,
    fake: bool,
    status_obj: RepoStatus | None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    cfg_path = config_path(root)
    checks.append(
        {
            "name": "repo_config",
            "ok": cfg_path.exists(),
            "label": "知识策略",
            "message": str(cfg_path) if cfg_path.exists() else "尚未初始化 .cairn/config.toml",
        }
    )
    if status_obj is None and cfg_path.exists():
        try:
            status_obj = repo_status(root)
        except Exception as exc:
            checks.append(
                {
                    "name": "repo_index",
                    "ok": False,
                    "label": "索引状态",
                    "message": str(exc),
                }
            )
    if status_obj is not None:
        unhealthy = (
            status_obj.stale_count
            + status_obj.missing_count
            + status_obj.error_count
        )
        checks.append(
            {
                "name": "repo_index",
                "ok": status_obj.indexed_count > 0 and unhealthy == 0,
                "label": "索引状态",
                "message": (
                    f"{status_obj.indexed_count} indexed, "
                    f"{status_obj.stale_count} stale, "
                    f"{status_obj.missing_count} missing, "
                    f"{status_obj.error_count} errors"
                ),
            }
        )
        primary_ok = any(
            doc.id == status_obj.primary_doc and doc.state == "indexed"
            for doc in status_obj.documents
        )
        checks.append(
            {
                "name": "primary_doc",
                "ok": primary_ok,
                "label": "默认文档",
                "message": status_obj.primary_doc or "未设置",
            }
        )
    if fake:
        checks.append(
            {
                "name": "local_models",
                "ok": True,
                "label": "离线模式",
                "message": "FakeSummarizer + FakeEmbedder, 可本地演示和回归",
            }
        )
    else:
        llm = load_llm_config()
        embed = load_embed_config()
        checks.append(
            {
                "name": "summarizer",
                "ok": bool(llm.model and llm.base_url),
                "label": "摘要模型",
                "message": f"{llm.model} at {llm.base_url}",
            }
        )
        checks.append(
            {
                "name": "embedder",
                "ok": bool(embed.model and embed.base_url and embed.dim > 0),
                "label": "向量模型",
                "message": f"{embed.provider}:{embed.model} dim={embed.dim}",
            }
        )
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_bounded_int(
    value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def _client_from_value(value: object) -> McpClient:
    if isinstance(value, str) and value in CLIENTS:
        return value
    msg = f"client must be one of {', '.join(CLIENTS)}"
    raise ValueError(msg)


def _api_root(server: ClientHTTPServer, payload: dict[str, Any]) -> Path:
    raw = payload.get("repo")
    if isinstance(raw, str) and raw.strip():
        root = _resolve_start_root(Path(raw))
    else:
        root = server.repo_root
    resolved_root = root.resolve()
    if resolved_root != server.repo_root.resolve():
        msg = "client API is scoped to the repository passed to `docsgraph client`"
        raise ValueError(msg)
    return resolved_root


class ClientRequestHandler(BaseHTTPRequestHandler):
    """Serve static client assets and local Cairn JSON APIs."""

    server: BaseServer

    def log_message(self, message_format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            self._handle_api_post(parsed.path, self._read_json_body())
        except ValueError as exc:
            self._send_json(
                {"ok": False, "error": {"message": str(exc)}},
                HTTPStatus.BAD_REQUEST,
            )

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        server = cast(ClientHTTPServer, self.server)
        try:
            if path == "/api/snapshot":
                root = _api_root(server, {"repo": _first(query, "repo")})
                self._send_json({"ok": True, "data": client_snapshot(root, fake=server.use_fake)})
                return
            if path == "/api/context":
                root = _api_root(server, {"repo": _first(query, "repo")})
                q = _first(query, "query") or ""
                k = _parse_bounded_int(
                    _first(query, "k"),
                    default=5,
                    minimum=1,
                    maximum=8,
                )
                fake = _parse_bool(_first(query, "fake"), default=server.use_fake)
                result = asyncio.run(
                    repo_context(
                        root,
                        embedder=make_embedder(fake),
                        query=q,
                        k=k,
                        related_k=min(4, k),
                        level="synopsis",
                        max_section_chars=1200,
                    )
                )
                self._send_json({"ok": True, "data": result["data"]})
                return
            if path == "/api/graph":
                root = _api_root(server, {"repo": _first(query, "repo")})
                result = asyncio.run(
                    repo_graph(
                        root,
                        doc=_first(query, "doc"),
                        include_entities=True,
                        include_xrefs=True,
                        max_sections=120,
                        max_entities=80,
                    )
                )
                self._send_json({"ok": True, "data": result["data"]})
                return
            if path == "/api/mcp/config":
                root = _api_root(server, {"repo": _first(query, "repo")})
                client = _client_from_value(_first(query, "client") or "codex")
                fake = _parse_bool(_first(query, "fake"), default=server.use_fake)
                fixed = _parse_bool(_first(query, "fixed_repo"), default=True)
                self._send_json(
                    {
                        "ok": True,
                        "data": mcp_config_payload(
                            root,
                            client=client,
                            fake=fake,
                            fixed_repo=fixed,
                        ),
                    }
                )
                return
            self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
        except CairnError as exc:
            self._send_json({"ok": False, "error": exc.to_envelope()}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": {"message": str(exc)}},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _handle_api_post(self, path: str, payload: dict[str, Any]) -> None:
        server = cast(ClientHTTPServer, self.server)
        try:
            root = _api_root(server, payload)
            if path == "/api/init":
                written = write_default_config(
                    root,
                    force=bool(payload.get("force", False)),
                    enable_markitdown=bool(payload.get("markitdown", False)),
                )
                self._send_json(
                    {
                        "ok": True,
                        "data": {
                            "config_path": str(written),
                            "snapshot": client_snapshot(root, fake=server.use_fake),
                        },
                    }
                )
                return
            if path == "/api/sync":
                fake = bool(payload.get("fake", server.use_fake))
                progress: list[str] = []
                results = asyncio.run(
                    sync_repo(
                        root,
                        summarizer=make_summarizer(fake),
                        embedder=make_embedder(fake),
                        index_config=load_index_config(),
                        force=bool(payload.get("force", False)),
                        progress=progress.append,
                    )
                )
                failed = sum(1 for item in results if not item.ok)
                rebuilt = sum(1 for item in results if item.ok and item.rebuilt)
                self._send_json(
                    {
                        "ok": failed == 0,
                        "data": {
                            "summary": {
                                "total": len(results),
                                "rebuilt": rebuilt,
                                "failed": failed,
                                "skipped": len(results) - rebuilt - failed,
                            },
                            "progress": progress,
                            "results": [
                                item.model_dump(mode="json") for item in results
                            ],
                            "snapshot": client_snapshot(root, fake=fake),
                        },
                    },
                    HTTPStatus.OK if failed == 0 else HTTPStatus.BAD_REQUEST,
                )
                return
            if path == "/api/mcp/install":
                client = _client_from_value(payload.get("client", "codex"))
                fake = bool(payload.get("fake", server.use_fake))
                fixed = bool(payload.get("fixed_repo", True))
                config = mcp_config_payload(root, client=client, fake=fake, fixed_repo=fixed)
                target = Path(config["target"])
                _write_mcp_config(
                    client,
                    target,
                    command=str(config["command"]),
                    args=list(config["args"]),
                    force=bool(payload.get("force", False)),
                )
                self._send_json(
                    {
                        "ok": True,
                        "data": {
                            "client": client,
                            "target": str(target),
                            "config": config["config"],
                        },
                    }
                )
                return
            self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
        except CairnError as exc:
            self._send_json({"ok": False, "error": exc.to_envelope()}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": {"message": str(exc)}},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _serve_static(self, request_path: str) -> None:
        rel = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        candidate = (STATIC_DIR / rel).resolve()
        if not str(candidate).startswith(str(STATIC_DIR.resolve())) or not candidate.exists():
            candidate = STATIC_DIR / "index.html"
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            msg = "JSON body must be an object"
            raise ValueError(msg)
        return data

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        return


def _first(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    if not values:
        return None
    return values[0]
