"""Bench dataset format — Pydantic models + TOML loader.

A suite lives in a single TOML file (loaded via stdlib ``tomllib``). The
shape::

    name = "Cairn Architecture v0.2.2"

    [[documents]]
    id = "architecture"
    source = "ARCHITECTURE.md"

    [[documents.questions]]
    id = "vector-store"
    question = "What is the default vector store?"
    expected_anchors = ["2-5-vectors-v-semantic-overlay", "7-tech-stack"]
    tags = ["definition", "tech-stack"]

``expected_anchors`` use substring matching against retrieved section_ids
so authors can use short suffixes instead of full hierarchical slugs.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cairn.core.errors import ConfigError


class BenchQuestion(BaseModel):
    """One bench question with ground-truth retrieval targets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    question: str
    expected_anchors: tuple[str, ...] = Field(
        default=(),
        description=(
            "Substrings to match against retrieved section_ids. "
            "Empty tuple = no recall computed for this question."
        ),
    )
    tags: tuple[str, ...] = ()
    reference: str | None = Field(
        default=None,
        description="Optional free-form reference answer for LLM-judged QA.",
    )


class BenchDocument(BaseModel):
    """One source document and the questions asked of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: Path = Field(
        description="Path to the source document, relative to the suite file."
    )
    questions: tuple[BenchQuestion, ...]


class BenchSuite(BaseModel):
    """A complete benchmark suite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    documents: tuple[BenchDocument, ...]


def load_suite(path: Path) -> BenchSuite:
    """Parse a TOML bench file. Source paths are resolved relative to it."""
    if not path.exists():
        msg = f"bench suite not found: {path}"
        raise ConfigError(msg, details={"path": str(path)})

    with path.open("rb") as fh:
        payload = tomllib.load(fh)

    suite_dir = path.parent
    documents_in = payload.get("documents", [])
    documents: list[BenchDocument] = []
    for doc in documents_in:
        questions_in = doc.get("questions", [])
        questions = [
            BenchQuestion(
                id=q["id"],
                question=q["question"],
                expected_anchors=tuple(q.get("expected_anchors", ())),
                tags=tuple(q.get("tags", ())),
                reference=q.get("reference"),
            )
            for q in questions_in
        ]
        documents.append(
            BenchDocument(
                id=doc["id"],
                source=(suite_dir / doc["source"]).resolve(),
                questions=tuple(questions),
            )
        )

    return BenchSuite(
        name=payload.get("name", path.stem),
        documents=tuple(documents),
    )
