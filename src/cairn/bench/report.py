"""Bench result types + JSON / markdown report writers."""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

System = Literal["cairn", "naive"]


class SystemResult(BaseModel):
    """One system's result for one question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system: System
    section_ids: tuple[str, ...]
    recall_at_k: float = Field(ge=0.0, le=1.0)
    tokens_returned: int = Field(ge=0)


class QuestionResult(BaseModel):
    """A question's results across both systems."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    question_id: str
    question: str
    expected_anchors: tuple[str, ...]
    tags: tuple[str, ...]
    cairn: SystemResult
    naive: SystemResult


class BenchSummary(BaseModel):
    """Full bench output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suite_name: str
    k: int
    questions: tuple[QuestionResult, ...]

    def cairn_mean_recall(self) -> float:
        return _mean(q.cairn.recall_at_k for q in self.questions)

    def naive_mean_recall(self) -> float:
        return _mean(q.naive.recall_at_k for q in self.questions)

    def cairn_mean_tokens(self) -> float:
        return _mean(float(q.cairn.tokens_returned) for q in self.questions)

    def naive_mean_tokens(self) -> float:
        return _mean(float(q.naive.tokens_returned) for q in self.questions)


def _mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.mean(materialized) if materialized else 0.0


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------


def write_json_report(summary: BenchSummary, path: Path) -> Path:
    """Write a deterministic JSON report next to the bench's working dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "suite": summary.suite_name,
        "k": summary.k,
        "summary": {
            "cairn_mean_recall_at_k": summary.cairn_mean_recall(),
            "naive_mean_recall_at_k": summary.naive_mean_recall(),
            "cairn_mean_tokens": summary.cairn_mean_tokens(),
            "naive_mean_tokens": summary.naive_mean_tokens(),
        },
        "questions": [q.model_dump(mode="json") for q in summary.questions],
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


def format_markdown_report(summary: BenchSummary) -> str:
    """Render a human-readable comparison table."""
    n = len(summary.questions)
    cairn_recall = summary.cairn_mean_recall()
    naive_recall = summary.naive_mean_recall()
    cairn_tokens = summary.cairn_mean_tokens()
    naive_tokens = summary.naive_mean_tokens()

    token_ratio = (
        cairn_tokens / naive_tokens if naive_tokens > 0 else float("nan")
    )

    lines: list[str] = []
    lines.append(f"# {summary.suite_name}")
    lines.append("")
    lines.append(f"Questions: **{n}** · k = **{summary.k}**")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append("| metric | naive vector RAG | Cairn |")
    lines.append("|---|---:|---:|")
    lines.append(
        f"| mean recall@{summary.k} | {naive_recall:.2%} | **{cairn_recall:.2%}** |"
    )
    lines.append(
        f"| mean tokens returned | {naive_tokens:,.0f} | **{cairn_tokens:,.0f}** "
        f"({token_ratio:.1%} of naive) |"
    )
    lines.append("")

    lines.append("## Per-question")
    lines.append("")
    lines.append("| question | recall (cairn) | recall (naive) | tokens (cairn / naive) |")
    lines.append("|---|---:|---:|---:|")
    for q in summary.questions:
        lines.append(
            f"| `{q.question_id}` {_truncate(q.question, 60)} "
            f"| {q.cairn.recall_at_k:.0%} "
            f"| {q.naive.recall_at_k:.0%} "
            f"| {q.cairn.tokens_returned} / {q.naive.tokens_returned} |"
        )

    return "\n".join(lines) + "\n"


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"
