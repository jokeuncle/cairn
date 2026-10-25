"""Run bounded real tool-using agents; preserve every attempt, without grading hints.

Example: --server '["python", "scripts/eval_document_server.py", "--mode", "bm25", ...]'
The server argv is JSON, never a shell command. See benchmarks/repo-quality/README.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_case(args: argparse.Namespace, case: dict[str, Any]) -> None:
    output = args.out / f"{case['id']}.json"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite an attempt: {output}")
    messages: list[dict[str, Any]] = []
    record: dict[str, Any] = {
        "case_id": case["id"],
        "task": case["task"],
        "arm": args.arm,
        "model": args.model,
        "seed": args.seed,
        "temperature": 0,
        "max_output_tokens": args.max_output,
        "tool_rounds": args.rounds,
        "tool_budget": args.calls,
        "server_argv": args.server,
        "rounds": [],
    }

    def save() -> None:
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    started = time.perf_counter()
    calls_used = 0
    save()
    selected_repo = None
    if "--repo" in args.server:
        selected_repo = Path(args.server[args.server.index("--repo") + 1]).resolve()
    params = StdioServerParameters(
        command=args.server[0], args=args.server[1:], env=dict(os.environ)
    )
    try:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            init = await session.initialize()
            listing = await session.list_tools()
            names = {
                "repo_context",
                "search_documents",
                "get_section",
                "get_related",
                "outline",
            }
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
                for tool in listing.tools
                if tool.name in names
            ]
            instructions = (
                "You are a documentation-assisted engineering agent. "
                "Use the supplied tools and source evidence to fulfill every task requirement. "
                "Read exact source sections for names, values and conditions. "
                "An excerpt is not exhaustive. Search again for uncovered requirements. "
                "Do not claim executable correctness without executing code; no execution "
                "tool is available in this protocol. "
                "Do not send requests, deploy or edit files. "
                f"Work within {args.rounds} tool rounds and {args.calls} tool attempts. "
                "Use k<=3 for search and k<=5 for related sections. "
                "Return complete requested code/configuration and source citations. "
                "Clearly mark any requirement you cannot verify.\n\n" + (init.instructions or "")
            )
            record["instructions"] = instructions
            record["tool_schemas"] = tools
            messages.extend(
                [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": case["task"]},
                ]
            )
            async with httpx.AsyncClient(timeout=args.timeout) as client:
                for turn in range(args.rounds + 1):
                    request: dict[str, Any] = {
                        "model": args.model,
                        "messages": messages,
                        "temperature": 0,
                        "seed": args.seed,
                        "max_tokens": args.max_output,
                    }
                    if turn < args.rounds and calls_used < args.calls:
                        request["tools"] = tools
                    else:
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Tool budget exhausted. Give the final deliverable now, "
                                    "explicitly marking unverified requirements."
                                ),
                            }
                        )
                    response = await client.post(
                        args.base_url.rstrip("/") + "/chat/completions", json=request
                    )
                    if not response.is_success:
                        record["http_error"] = {
                            "status": response.status_code,
                            "body": response.text[:2000],
                        }
                    response.raise_for_status()
                    choice = response.json()["choices"][0]
                    message = choice["message"]
                    messages.append(message)
                    step: dict[str, Any] = {
                        "message": message,
                        "finish_reason": choice.get("finish_reason"),
                        "usage": response.json().get("usage", {}),
                        "calls": [],
                    }
                    record["rounds"].append(step)
                    save()
                    calls = message.get("tool_calls", [])
                    if not calls:
                        record["answer"] = message.get("content", "")
                        record["finish_reason"] = choice.get("finish_reason")
                        break
                    for call in calls:
                        name = call["function"]["name"]
                        arguments: Any = None
                        if calls_used >= args.calls or turn == args.rounds:
                            payload = {"ok": False, "error": "Tool budget exhausted"}
                            raw = json.dumps(payload)
                        else:
                            calls_used += 1
                            try:
                                arguments = json.loads(call["function"]["arguments"])
                                if name not in names or not isinstance(arguments, dict):
                                    raise ValueError("Unknown tool or invalid arguments")
                                if (
                                    selected_repo is not None
                                    and arguments.get("projectPath")
                                    and Path(arguments["projectPath"]).resolve() != selected_repo
                                ):
                                    raise ValueError("Only the task repository is available")
                                reply = await session.call_tool(name, arguments)
                                raw = "\n".join(
                                    item.text for item in reply.content if item.type == "text"
                                )
                                try:
                                    payload = json.loads(raw)
                                except json.JSONDecodeError:
                                    payload = {"text": raw}
                            except (ValueError, TypeError) as exc:
                                payload = {"ok": False, "error": str(exc)}
                                raw = json.dumps(payload)
                        step["calls"].append({"tool": name, "args": arguments, "result": payload})
                        messages.append(
                            {"role": "tool", "tool_call_id": call["id"], "content": raw}
                        )
                        save()
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        record["tool_attempts"] = calls_used
        record["elapsed_seconds"] = time.perf_counter() - started
        record["total_reported_prompt_tokens"] = sum(
            step["usage"].get("prompt_tokens", 0) for step in record["rounds"]
        )
        record["total_reported_completion_tokens"] = sum(
            step["usage"].get("completion_tokens", 0) for step in record["rounds"]
        )
        save()
    print(
        f"{args.arm} {case['id']}: {len(record['rounds'])} rounds, "
        f"{calls_used} calls, finish={record.get('finish_reason')}",
        flush=True,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--case-id")
    parser.add_argument("--server", type=json.loads, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18081/v1")
    parser.add_argument("--model", default="Qwen3-4B-Instruct-2507-Q4_K_M")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rounds", type=int, default=16)
    parser.add_argument("--calls", type=int, default=24)
    parser.add_argument("--max-output", type=int, default=1800)
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    if (
        not isinstance(args.server, list)
        or not args.server
        or not all(isinstance(item, str) for item in args.server)
    ):
        parser.error("--server must be a nonempty JSON string array")
    if min(args.rounds, args.calls, args.max_output, args.timeout) <= 0:
        parser.error("Budgets and timeout must be positive")
    args.out.mkdir(parents=True, exist_ok=True)
    for case in json.loads(args.cases.read_text(encoding="utf-8")):
        if args.case_id and case["id"] != args.case_id:
            continue
        await run_case(args, case)


if __name__ == "__main__":
    asyncio.run(main())
