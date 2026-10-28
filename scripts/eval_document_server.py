"""Reference MCP servers for matched Cairn, section-BM25 and raw-text experiments.

Indexes only the selected frozen source paths. Baselines never load Cairn indexes.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import math
import re
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


def words(text: str) -> list[str]:
    stop = set(
        [
            "a",
            "an",
            "the",
            "is",
            "are",
            "of",
            "in",
            "on",
            "at",
            "to",
            "for",
            "from",
            "how",
            "what",
            "which",
            "does",
            "do",
            "and",
            "or",
            "with",
            "by",
        ]
    )
    return [token for token in re.findall(r"[a-z0-9_]+", text.lower()) if token not in stop]


class Sources:
    def __init__(self, repo: Path, paths: list[str]) -> None:
        self.files = {path: (repo / path).read_text(encoding="utf-8") for path in paths}
        self.sections: list[dict[str, Any]] = []
        markdown = MarkdownIt("commonmark")
        for path, text in self.files.items():
            lines = text.splitlines(keepends=True)
            headings = [
                token.map[0]
                for token in markdown.parse(text)
                if token.type == "heading_open" and token.map
            ]
            starts = sorted({0, *headings})
            for start, end in zip(starts, [*starts[1:], len(lines)], strict=True):
                body = "".join(lines[start:end])
                if body.strip():
                    self.sections.append(
                        {
                            "id": f"{path}#L{start + 1}",
                            "source": path,
                            "line": start + 1,
                            "text": body,
                        }
                    )
        self.by_id = {item["id"]: item for item in self.sections}
        self.counts = [
            collections.Counter(words(item["source"] + " " + item["text"]))
            for item in self.sections
        ]
        self.df = collections.Counter(term for count in self.counts for term in count)
        self.lengths = [sum(count.values()) for count in self.counts]
        self.average = sum(self.lengths) / max(1, len(self.lengths))

    def search(self, query: str, k: int, mode: str) -> list[dict[str, Any]]:
        terms = set(words(query))
        if mode == "bm25":
            scores = [
                sum(
                    math.log(1 + (len(self.counts) - self.df[term] + 0.5) / (self.df[term] + 0.5))
                    * count[term]
                    * 2.5
                    / (count[term] + 1.5 * (0.25 + 0.75 * length / self.average))
                    for term in terms
                    if count[term]
                )
                for count, length in zip(self.counts, self.lengths, strict=True)
            ]
            ranked = sorted(range(len(scores)), key=lambda index: -scores[index])
            return [self.excerpt(self.sections[index]) for index in ranked[:k] if scores[index] > 0]
        # Raw-text baseline: case-insensitive literal query, matching lines plus
        # nearby context in document order. Multiple concepts need separate calls.
        hits = []
        for path, text in self.files.items():
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if query.casefold() in line.casefold():
                    start, end = max(0, index - 2), min(len(lines), index + 4)
                    hits.append(
                        {
                            "id": f"{path}#L{start + 1}",
                            "source": path,
                            "line": index + 1,
                            "text": "\n".join(lines[start:end]),
                        }
                    )
                    if len(hits) >= k:
                        return hits
        return hits

    @staticmethod
    def excerpt(section: dict[str, Any]) -> dict[str, Any]:
        return {**section, "text": section["text"][:1600], "truncated": len(section["text"]) > 1600}

    def read(self, section_id: str) -> dict[str, Any]:
        if section_id in self.by_id:
            item = self.by_id[section_id]
            return {**item, "text": item["text"][:12000], "truncated": len(item["text"]) > 12000}
        path, separator, line = section_id.partition("#L")
        if path not in self.files:
            raise ValueError("Unknown source; use outline for available files and section IDs")
        start = int(line) - 1 if separator else 0
        lines = self.files[path].splitlines()
        if start < 0 or start >= len(lines):
            raise ValueError("Line outside source")
        body = "\n".join(lines[start : start + 120])
        return {
            "source": path,
            "id": section_id,
            "text": body[:12000],
            "truncated": start + 120 < len(lines) or len(body) > 12000,
        }


async def baseline(args: argparse.Namespace, paths: list[str]) -> None:
    source = Sources(args.repo, paths)
    description = (
        "Search documentation sections using BM25. Natural-language queries are accepted."
        if args.mode == "bm25"
        else "Search source text for a case-insensitive literal substring, like grep. "
        "Use a short exact term; separate concepts need separate searches."
    )
    server: Server[Any] = Server(
        "documentation-baseline",
        instructions=(
            "Use search_documents to locate source evidence, get_section to read it, "
            "and outline to list available source files/section IDs. "
            "Excerpts can be incomplete. Cite source paths and lines."
        ),
    )
    schemas = [
        types.Tool(
            name="search_documents",
            description=description,
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "minimum": 1, "maximum": 8, "default": 3},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="get_section",
            description=(
                "Read original source by returned section id (path#Lnumber), or a source "
                "path to read its first 120 lines. Up to 12000 characters per read."
            ),
            inputSchema={
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "level": {"type": "string", "default": "full"},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="outline",
            description="List source files and section IDs; optionally restrict source.",
            inputSchema={
                "type": "object",
                "properties": {"doc": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
    ]

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        return schemas

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        try:
            if name == "search_documents":
                k = arguments.get("k", 3)
                if not isinstance(k, int) or not 1 <= k <= 8:
                    raise ValueError("k must be in [1,8]")
                data: Any = {"hits": source.search(arguments["query"], k, args.mode)}
            elif name == "get_section":
                data = source.read(arguments["id"])
            elif name == "outline":
                data = {
                    "files": list(source.files),
                    "sections": [
                        {"id": item["id"], "title": item["text"].splitlines()[0]}
                        for item in source.sections
                        if not arguments.get("doc") or item["source"] == arguments["doc"]
                    ],
                }
            else:
                raise ValueError("Unknown tool")
            payload = {"ok": True, "data": data}
        except (ValueError, KeyError, TypeError) as exc:
            payload = {"ok": False, "error": str(exc)}
        return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("cairn", "bm25", "raw"), required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "benchmarks/repo-quality/cases.json",
    )
    parser.add_argument("--source-root", type=Path, help="Explicit frozen Cairn src directory")
    parser.add_argument("--embed-url", default="http://127.0.0.1:18082/v1")
    parser.add_argument(
        "--window-bytes", type=int, help="Explicit windowed-embedding adapter budget"
    )
    args = parser.parse_args()
    if args.mode == "cairn":
        if args.source_root:
            import sys

            sys.path.insert(0, str(args.source_root))
        from cairn.embed.openai_compatible import OpenAICompatibleEmbedder
        from cairn.mcp.server import serve_repo_stdio

        class QueryEmbedder(OpenAICompatibleEmbedder):
            async def embed(self, texts: list[str]) -> list[list[float]]:
                return await super().embed(["search_query: " + text for text in texts])

        embedder: Any = QueryEmbedder(
            base_url=args.embed_url, model="nomic-embed-text-v1.5.Q4_K_M", dim=768, timeout=90
        )
        if args.window_bytes is not None:
            from cairn.embed.windowed import WindowedEmbedder

            embedder = WindowedEmbedder(embedder, max_input_bytes=args.window_bytes)
        await serve_repo_stdio(args.repo, embedder=embedder)
    else:
        config = json.loads(args.cases.read_text(encoding="utf-8"))[args.corpus]
        await baseline(args, ["docs/" + path for path in config["docs"]])


if __name__ == "__main__":
    asyncio.run(main())
