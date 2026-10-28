"""Verify reviewed benchmark Python independently of the agent's own tests.

Execution is explicit and for audited code only. The network guard prevents
accidental requests; this script is not a security sandbox for untrusted code.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import contextlib
import hashlib
import inspect
import io
import json
import socket
import sys
import types
from pathlib import Path
from typing import Any


def python_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if current is None and line.strip() in ("```python", "```py"):
            current = []
        elif current is not None and line.strip() == "```":
            blocks.append("\n".join(current) + "\n")
            current = None
        elif current is not None:
            current.append(line)
    return blocks


async def verify_httpx(module: Any, case_id: str) -> dict[str, Any]:
    import httpx

    value = module.build_client()
    value = await value if inspect.isawaitable(value) else value
    client = value[0] if isinstance(value, tuple) else value
    if not isinstance(client, httpx.AsyncClient):
        raise TypeError("build_client must return an AsyncClient (optionally as first tuple item)")
    auth_case = case_id == "httpx-shared-auth-client"
    expected = (30, 30, 30, 2) if auth_case else (60, 10, 10, 10)
    limits = (20, 4, 10) if auth_case else (10, 5, 5)
    checks: dict[str, Any] = {}
    try:
        actual = tuple(getattr(client.timeout, key) for key in ("connect", "read", "write", "pool"))
        pool = client._transport._pool
        checks.update(
            timeouts=actual == expected,
            actual_timeouts=actual,
            trust_env=client.trust_env is False,
            pool_limits=(
                pool._max_connections,
                pool._max_keepalive_connections,
                pool._keepalive_expiry,
            )
            == limits,
        )
        if not auth_case:
            checks["http2"] = pool._http2 is True
        request = httpx.Request("GET", "https://example.invalid/")
        if auth_case:
            authenticated = next(client.auth.auth_flow(request))
            checks["basic_auth"] = authenticated.headers.get("Authorization") == (
                "Basic YWxpY2U6ZXhhbXBsZS1zZWNyZXQ="
            )
            request_hooks = client.event_hooks.get("request", [])
            checks["async_request_hook"] = bool(request_hooks)
            for hook in request_hooks:
                outcome = hook(request)
                checks["async_request_hook"] &= inspect.isawaitable(outcome)
                if inspect.isawaitable(outcome):
                    await outcome
            checks["audit_header"] = request.headers.get("X-Audit") == "yes"
        response = httpx.Response(200, request=request, stream=httpx.ByteStream(b'{"ok":true}'))
        original = response.aread
        reads = 0

        async def tracked_read() -> bytes:
            nonlocal reads
            reads += 1
            return await original()

        response.aread = tracked_read
        hooks = client.event_hooks.get("response", [])
        checks["async_response_hook"] = bool(hooks)
        for hook in hooks:
            outcome = hook(response)
            checks["async_response_hook"] &= inspect.isawaitable(outcome)
            if inspect.isawaitable(outcome):
                await outcome
        checks["body_read_awaited"] = reads > 0
    finally:
        await client.aclose()
    checks["closed"] = client.is_closed
    return checks


def verify_starlette(module: Any, case_id: str) -> dict[str, Any]:
    import httpx
    from starlette.testclient import TestClient

    created: list[httpx.AsyncClient] = []
    original = httpx.AsyncClient

    class TrackedClient(original):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            created.append(self)

    for name, value in tuple(vars(module).items()):
        if value is original:
            setattr(module, name, TrackedClient)
    httpx.AsyncClient = TrackedClient
    try:
        app = module.make_app()
        with TestClient(app) as client:
            if case_id == "starlette-shared-lifespan-state":
                first = client.get("/record/first")
                second = client.get("/record/second")
                one, two = first.json(), second.json()
                if isinstance(one, dict):
                    one = one.get("events")
                if isinstance(two, dict):
                    two = two.get("events")
                endpoint_ok = (
                    first.status_code == second.status_code == 200
                    and one == ["first"]
                    and two == ["first", "second"]
                )
            else:
                endpoint_ok = client.get("/health").status_code == 200
            checks = {
                "endpoint": endpoint_ok,
                "single_client": len(created) == 1,
                "open_inside_lifespan": bool(created) and not created[0].is_closed,
                "client_shared_in_state": bool(created)
                and any(value is created[0] for value in client.app_state.values()),
            }
        checks["closed_on_shutdown"] = bool(created) and all(item.is_closed for item in created)
        return checks
    finally:
        httpx.AsyncClient = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument(
        "--case-id",
        required=True,
        choices=(
            "httpx-service-client",
            "httpx-shared-auth-client",
            "starlette-lifecycle-service",
            "starlette-shared-lifespan-state",
        ),
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--extra-dependencies", type=Path)
    parser.add_argument("--run-audited-code", action="store_true")
    args = parser.parse_args()
    if args.extra_dependencies:
        sys.path.insert(0, str(args.extra_dependencies.resolve()))
    text = args.answer.read_text(encoding="utf-8")
    if args.answer.suffix == ".json":
        text = json.loads(text).get("answer", "")
    blocks = python_blocks(text)
    result: dict[str, Any] = {
        "case_id": args.case_id,
        "answer": str(args.answer),
        "answer_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "python_blocks": len(blocks),
        "runtime_attempted": False,
        "manual_source_and_deliverable_review_required": True,
    }
    output = io.StringIO()
    try:
        if not blocks:
            raise ValueError("No complete Python block")
        interface = "build_client" if args.case_id.startswith("httpx") else "make_app"
        # Grade the complete implementation. Supplementary usage fragments may
        # contain top-level await and are not standalone program deliverables.
        primary = next((block for block in blocks if f"def {interface}(" in block), blocks[0])
        tree = ast.parse(primary)
        result["compiled"] = True
        result["required_interface_declared"] = any(
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == interface
            for node in tree.body
        )
        if args.run_audited_code:
            allowed = {
                "__future__",
                "httpx",
                "starlette",
                "contextlib",
                "typing",
                "asyncio",
                "anyio",
                "collections",
                "dataclasses",
                "datetime",
                "json",
                "pytest",
                "logging",
                "ssl",
                "unittest",
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(
                    item.name.split(".")[0] not in allowed for item in node.names
                ):
                    raise ValueError("Unreviewed import")
                if isinstance(node, ast.ImportFrom) and (
                    not node.module or node.module.split(".")[0] not in allowed
                ):
                    raise ValueError("Unreviewed import")

            def no_network(*a: Any, **kw: Any) -> Any:
                raise RuntimeError("Outbound network disabled by acceptance verifier")

            socket.socket.connect = no_network
            socket.create_connection = no_network
            module = types.ModuleType("agent_generated")
            sys.modules[module.__name__] = module
            result["runtime_attempted"] = True
            with contextlib.redirect_stdout(output):
                exec(compile(primary, "<audited-agent-code>", "exec"), module.__dict__)
                if args.case_id.startswith("httpx"):
                    checks = asyncio.run(verify_httpx(module, args.case_id))
                else:
                    checks = verify_starlette(module, args.case_id)
            result["runtime_checks"] = checks
            result["runtime_constraints_passed"] = all(
                value for key, value in checks.items() if key != "actual_timeouts"
            )
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        result["runtime_constraints_passed"] = False
    result["generated_stdout"] = output.getvalue()[-3000:]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
