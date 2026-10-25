"""Evaluate an already indexed repository using frozen, source-grounded questions.

This measures required-fact coverage, not semantic answer correctness. Optional
QA never receives the reference markers. Review saved answers before making
quality claims. See benchmarks/repo-quality/README.md for the full protocol.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from cairn.core.config import load_llm_config
from cairn.embed.base import Embedder
from cairn.providers import make_embedder
from cairn.repo import repo_context

ROOT = Path(__file__).resolve().parents[1]


class QueryPrefixEmbedder:
    """Apply an explicit provider task prefix for a query-only evaluation."""

    def __init__(self, delegate: Embedder, prefix: str) -> None:
        self.delegate = delegate
        self.prefix = prefix
        self.name = delegate.name
        self.dim = delegate.dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.delegate.embed([self.prefix + text for text in texts])


def evidence_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for section in payload["data"]["context_sections"]:
        # Headings are source evidence: configuration/API names often live in
        # titles and are deliberately excluded from SectionNode.raw_text.
        parts.append(f"Source: {section['source']}\n# {section['title']}")
        excerpt = section.get("evidence", section.get("hit", {}).get("evidence", {}))
        for text in (section["content"], excerpt.get("text", "")):
            if text and text not in parts:
                parts.append(text)
    return "\n\n".join(parts)


def marker_checks(text: str, question: dict[str, Any]) -> list[bool]:
    return [
        any(term.casefold() in text.casefold() for term in group) for group in question["facts"]
    ]


async def evaluate(args: argparse.Namespace) -> None:
    dataset = json.loads(args.cases.read_text(encoding="utf-8"))[args.corpus]
    questions = dataset["cases"][: args.limit] if args.limit else dataset["cases"]
    embedder = QueryPrefixEmbedder(make_embedder(args.fake), args.query_prefix)
    cfg = load_llm_config()
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(args.repo), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    records: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "corpus": args.corpus,
        "repository": str(args.repo.resolve()),
        "reference_revision": dataset["revision"],
        "actual_revision": revision,
        "revision_matches_reference": revision == dataset["revision"],
        "case_file_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "embedder": embedder.name,
        "query_prefix": args.query_prefix,
        "fake": args.fake,
        "qa_model": cfg.model if args.qa else None,
        "metric": "Literal required-fact screening; review answers for semantic correctness.",
        "records": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        for index, question in enumerate(questions):
            started = time.perf_counter()
            payload = await repo_context(args.repo, embedder=embedder, query=question["q"])
            evidence = evidence_text(payload)
            record: dict[str, Any] = {
                "id": question["id"],
                "question": question["q"],
                "retrieval_seconds": time.perf_counter() - started,
                "payload": payload,
                "evidence_checks": marker_checks(evidence, question),
            }
            records.append(record)
            save()
            if args.qa and index % dataset.get("qa_stride", 1) == 0:
                response = await client.post(
                    f"{cfg.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json={
                        "model": cfg.model,
                        "temperature": 0,
                        "seed": 42,
                        "max_tokens": 200,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Answer ONLY from the supplied documentation evidence. "
                                    "If absent say INSUFFICIENT EVIDENCE. Be concise and include "
                                    "exact configuration names and requested values. "
                                    "Do not use prior knowledge."
                                ),
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"Question: {question['q']}\n\n"
                                    f"Documentation evidence:\n{evidence}"
                                ),
                            },
                        ],
                    },
                )
                response.raise_for_status()
                data = response.json()
                record["answer"] = data["choices"][0]["message"]["content"]
                record["answer_checks"] = marker_checks(record["answer"], question)
                record["usage"] = data.get("usage")
            save()
            print(f"{question['id']}: evidence={all(record['evidence_checks'])}", flush=True)
    report["summary"] = {
        "retrieval_questions": len(records),
        "evidence_marker_complete": sum(all(row["evidence_checks"]) for row in records),
        "qa_questions": sum("answer" in row for row in records),
        "answer_marker_complete": sum(
            all(row["answer_checks"]) for row in records if "answer_checks" in row
        ),
    }
    save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="An already synced repository")
    parser.add_argument("--corpus", choices=("httpx", "starlette", "mkdocs"), required=True)
    parser.add_argument("--cases", type=Path, default=ROOT / "benchmarks/repo-quality/cases.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--query-prefix", default="", help="Explicit embedding task prefix")
    parser.add_argument("--limit", type=int, help="Limit cases for a smoke check")
    parser.add_argument("--fake", action="store_true", help="Offline smoke only; no quality claim")
    parser.add_argument("--qa", action="store_true", help="Answer with configured CAIRN_LLM_*")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.fake and args.qa:
        parser.error("--fake is for retrieval smoke only; remove it for real QA")
    asyncio.run(evaluate(args))


if __name__ == "__main__":
    main()
