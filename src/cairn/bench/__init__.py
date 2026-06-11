"""cairn-bench — evaluate Cairn against a naive vector-RAG baseline.

A small framework for measuring retrieval recall and token cost on
hand-curated question sets. The shipped starter dataset is small;
production-grade evaluation requires more curation than fits in this
codebase. The framework is the contribution; the dataset is a template.
"""

from cairn.bench.dataset import (
    BenchDocument,
    BenchQuestion,
    BenchSuite,
    load_suite,
)
from cairn.bench.judge import LLMJudge
from cairn.bench.metrics import recall_at_k
from cairn.bench.report import (
    BenchSummary,
    QuestionResult,
    format_markdown_report,
    write_json_report,
)
from cairn.bench.runner import BenchRunner

__all__ = [
    "BenchDocument",
    "BenchQuestion",
    "BenchRunner",
    "BenchSuite",
    "BenchSummary",
    "LLMJudge",
    "QuestionResult",
    "format_markdown_report",
    "load_suite",
    "recall_at_k",
    "write_json_report",
]
