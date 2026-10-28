"""Summarization layer — pluggable LLM-backed summarizers + cache.

Used by the index layer (`cairn.index.summaries.SummaryBuilder`) at indexing
time. Never invoked at query time. See ARCHITECTURE.md §2.2.
"""

from cairn.summarize.base import Summarizer, SummaryLevel
from cairn.summarize.cache import SummaryCache
from cairn.summarize.fake import FakeSummarizer
from cairn.summarize.openai_compatible import OpenAICompatibleSummarizer

__all__ = [
    "FakeSummarizer",
    "OpenAICompatibleSummarizer",
    "Summarizer",
    "SummaryCache",
    "SummaryLevel",
]
